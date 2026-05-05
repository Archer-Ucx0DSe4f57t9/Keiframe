# src/recognizers/white_supply_recognizer.py
# -*- coding: utf-8 -*-
"""
WhiteSupplyRecognizer

用途：
- 识别 StarCraft II 右上角白色人口数字，例如 39/100、12/100、18/90。
- 使用固定 ROI + 白字提取 + 模板滑窗匹配。
- 模板目录：resources/templates/white_supply/{cn,en,common}/
- 模板文件名示例：0_01.png、0_02.png、9_01.png、slash_01.png。

重点：
- 不做连通域切字符，因为 / 可能和前一个数字的横向范围重叠。
- 先找 slash，再按字符中心点分左右数字。
- 同字符候选做 NMS，不同字符候选不互相压制。
- ROI 和模板制作时保持同一套“白字 mask + 放大倍数”逻辑。

可直接测试：
    python -m src.recognizers.white_supply_recognizer "H:/path/to/screenshot.png" --lang cn --debug
    python -m src.recognizers.white_supply_recognizer "H:/path/to/screenshot.png" --lang en --debug
"""

from __future__ import annotations

import argparse
import itertools
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from src import config
from src.utils.fileutil import get_resources_dir
from src.utils.logging_util import get_logger

@dataclass
class SupplyCandidate:
    char: str                 # "0"-"9" 或 "slash"
    text: str                 # "0"-"9" 或 "/"
    x: int
    y: int
    w: int
    h: int
    score: float
    template_name: str

    @property
    def cx(self) -> float:
        return self.x + self.w / 2.0

    @property
    def cy(self) -> float:
        return self.y + self.h / 2.0

    @property
    def area(self) -> int:
        return max(1, self.w * self.h)


@dataclass
class SupplyResult:
    current: int
    max: int
    raw: str
    score: float
    lang: str
    roi: Tuple[int, int, int, int]
    candidates: List[SupplyCandidate]
    selected: List[SupplyCandidate]

    def to_dict(self) -> dict:
        return {
            "current": self.current,
            "max": self.max,
            "raw": self.raw,
            "score": self.score,
            "lang": self.lang,
            "roi": self.roi,
            "candidates": [c.__dict__.copy() for c in self.candidates],
            "selected": [c.__dict__.copy() for c in self.selected],
        }


class WhiteSupplyRecognizer:
    # ===== 1920x1080 基准 ROI =====
    # 格式：x, y, w, h
    ROI_CN = (1805, 18, 82, 22)
    ROI_EN = (1805, 20, 92, 20)

    # 调试用大 ROI。必要时可切到这个看是否 ROI 裁偏。
    ROI_DEBUG = (1800, 15, 105, 30)

    # 模板制作时推荐的放大倍数。
    # 注意：如果模板是从 4x 裁剪源里裁出来的，识别 ROI 也必须放大 4x 后匹配。
    TEMPLATE_SCALE = 4

    # 如果模板基于 1920x1080 制作，建议先把不同分辨率下的 ROI mask 归一化回基准 ROI 大小，再放大匹配。
    NORMALIZE_ROI_TO_BASE_SIZE = True

    # ===== 白字提取参数 =====
    # 这些默认值和 supply_template_maker.py 的初始逻辑保持接近。
    WHITE_GRAY_MIN = 145
    WHITE_RGB_MIN = 120
    WHITE_RGB_DELTA_MAX = 75
    WHITE_PERCENTILE = 78
    WHITE_USE_PERCENTILE = True
    WHITE_BLUR_KSIZE = 1
    WHITE_DILATE_ITER = 0
    WHITE_ERODE_ITER = 0

    # ===== 模板匹配参数 =====
    DIGIT_THRESHOLD = 0.55
    SLASH_THRESHOLD = 0.50
    MAX_CANDIDATES_PER_TEMPLATE = 30
    MAX_CANDIDATES_PER_CHAR_AFTER_NMS = 10
    # 同一横向位置可能同时命中 6/8、1/7、0/8。
    # 解析时每个数字位置保留多个备选，避免最高分误选导致整串失败或误读。
    DIGIT_ALTERNATIVES_PER_POSITION = 3
    SAME_CHAR_NMS_IOU = 0.25

    # slash 模板漏检时，允许用数字簇之间最大的横向空隙推断 / 的位置。
    # 这对 160/179 这种 slash 没有进入候选但 6 个数字都识别到的情况很有用。
    INFER_SLASH_IF_MISSING = True
    MIN_INFER_SEPARATOR_GAP = 60
    SAME_CHAR_CENTER_TOLERANCE = 12
    LOCAL_MAX_KERNEL = 3

    # 解析时，过滤明显来自 slash 区域的数字候选。
    # 例如 81/100 中，/ 可能同时被 7 模板命中，形成一个假的左侧第 3 位数字。
    # 这个过滤只处理“数字候选本身落在 slash 区域内”的情况，不会按距离粗暴删除左侧真实数字。
    SLASH_DIGIT_OVERLAP_IOU = 0.18
    SLASH_DIGIT_CENTER_INSIDE_MARGIN = 2

    # 某些数字的局部笔画会被 1 模板误命中，例如 12/15 会被误读成 112/115。
    # 这里过滤“嵌在更强数字框里的低分候选”。
    EMBEDDED_DIGIT_OVERLAP_RATIO = 0.15
    EMBEDDED_DIGIT_VERTICAL_OVERLAP_RATIO = 0.55
    EMBEDDED_DIGIT_SCORE_GAP = 0.20

    # 合法性限制。
    MIN_MAX_SUPPLY = 10
    MAX_MAX_SUPPLY = 250
    MAX_CURRENT_SUPPLY = 250

    def __init__(
        self,
        template_root: Optional[str] = None,
        template_scale: Optional[int] = None,
        normalize_roi_to_base_size: Optional[bool] = None,
        debug: bool = False,
        debug_dir: Optional[str] = None,
    ):
        self.logger = get_logger(__name__)
        self.template_root = template_root or get_resources_dir("templates", "white_supply")
        self.template_scale = int(template_scale or self._cfg("SUPPLY_TEMPLATE_SCALE", self.TEMPLATE_SCALE))
        self.normalize_roi_to_base_size = bool(
            self.NORMALIZE_ROI_TO_BASE_SIZE if normalize_roi_to_base_size is None else normalize_roi_to_base_size
        )
        self.debug = debug
        self.debug_dir = debug_dir or os.path.join(os.getcwd(), "tests", "supply", "debug")

        self._templates_cache: Dict[str, Dict[str, List[Tuple[str, np.ndarray]]]] = {}

        self.white_gray_min = int(self._cfg("SUPPLY_WHITE_GRAY_MIN", self.WHITE_GRAY_MIN))
        self.white_rgb_min = int(self._cfg("SUPPLY_WHITE_RGB_MIN", self.WHITE_RGB_MIN))
        self.white_rgb_delta_max = int(self._cfg("SUPPLY_WHITE_RGB_DELTA_MAX", self.WHITE_RGB_DELTA_MAX))
        self.white_percentile = int(self._cfg("SUPPLY_WHITE_PERCENTILE", self.WHITE_PERCENTILE))
        self.white_use_percentile = bool(self._cfg("SUPPLY_WHITE_USE_PERCENTILE", self.WHITE_USE_PERCENTILE))
        self.white_blur_ksize = int(self._cfg("SUPPLY_WHITE_BLUR_KSIZE", self.WHITE_BLUR_KSIZE))
        self.white_dilate_iter = int(self._cfg("SUPPLY_WHITE_DILATE_ITER", self.WHITE_DILATE_ITER))
        self.white_erode_iter = int(self._cfg("SUPPLY_WHITE_ERODE_ITER", self.WHITE_ERODE_ITER))

        self.digit_threshold = float(self._cfg("SUPPLY_DIGIT_MATCH_THRESHOLD", self.DIGIT_THRESHOLD))
        self.slash_threshold = float(self._cfg("SUPPLY_SLASH_MATCH_THRESHOLD", self.SLASH_THRESHOLD))

    @staticmethod
    def _cfg(name: str, default):
        if config is None:
            return default
        return getattr(config, name, default)

    @staticmethod
    def normalize_lang(lang: Optional[str]) -> str:
        if not lang:
            if config is not None:
                lang = getattr(config, "current_game_language", "cn")
            else:
                lang = "cn"

        value = str(lang).strip().lower()
        if value in {"zh", "chs", "cht", "cn", "zh-cn", "zh_cn", "chinese", "中文"}:
            return "cn"
        if value in {"en", "eng", "english", "英文"}:
            return "en"
        return "cn"

    def get_base_roi(self, lang: str, use_debug_roi: bool = False) -> Tuple[int, int, int, int]:
        if use_debug_roi:
            return tuple(self._cfg("SUPPLY_ROI_DEBUG", self.ROI_DEBUG))

        lang = self.normalize_lang(lang)
        if lang == "en":
            return tuple(self._cfg("SUPPLY_ROI_EN", self.ROI_EN))
        return tuple(self._cfg("SUPPLY_ROI_CN", self.ROI_CN))

    @staticmethod
    def _scaled_roi(
        base_roi: Tuple[int, int, int, int],
        scale_factor: float,
        image_shape: Tuple[int, int, int],
    ) -> Tuple[int, int, int, int]:
        x, y, w, h = base_roi
        img_h, img_w = image_shape[:2]
        sx = int(round(x * scale_factor))
        sy = int(round(y * scale_factor))
        sw = max(1, int(round(w * scale_factor)))
        sh = max(1, int(round(h * scale_factor)))

        sx = max(0, min(img_w - 1, sx))
        sy = max(0, min(img_h - 1, sy))
        ex = max(sx + 1, min(img_w, sx + sw))
        ey = max(sy + 1, min(img_h, sy + sh))
        return sx, sy, ex - sx, ey - sy

    @staticmethod
    def _read_image_unicode(path: str, flags=cv2.IMREAD_COLOR) -> Optional[np.ndarray]:
        try:
            data = np.fromfile(path, dtype=np.uint8)
            if data.size == 0:
                return None
            return cv2.imdecode(data, flags)
        except Exception:
            return None

    @staticmethod
    def _save_png_unicode(path: str, image: np.ndarray) -> bool:
        try:
            out_dir = os.path.dirname(path)
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
            ok, encoded = cv2.imencode(".png", image)
            if not ok or encoded is None:
                return False
            with open(path, "wb") as f:
                f.write(encoded.tobytes())
            return os.path.isfile(path) and os.path.getsize(path) > 0
        except Exception:
            return False

    @staticmethod
    def _to_binary_mask(gray: np.ndarray) -> np.ndarray:
        if gray is None or gray.size == 0:
            return np.zeros((1, 1), dtype=np.uint8)
        if gray.ndim == 3:
            gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
        return mask

    @staticmethod
    def _tight_crop_mask(mask: np.ndarray, padding: int = 0) -> np.ndarray:
        ys, xs = np.where(mask > 0)
        if len(xs) == 0 or len(ys) == 0:
            return mask.copy()
        h, w = mask.shape[:2]
        x1 = max(0, int(xs.min()) - padding)
        x2 = min(w, int(xs.max()) + 1 + padding)
        y1 = max(0, int(ys.min()) - padding)
        y2 = min(h, int(ys.max()) + 1 + padding)
        return mask[y1:y2, x1:x2].copy()

    def _load_templates_for_lang(self, lang: str) -> Dict[str, List[Tuple[str, np.ndarray]]]:
        lang = self.normalize_lang(lang)
        if lang in self._templates_cache:
            return self._templates_cache[lang]

        templates: Dict[str, List[Tuple[str, np.ndarray]]] = {str(i): [] for i in range(10)}
        templates["slash"] = []

        # 先读当前语言，再读 common。当前语言和 common 都可存在。
        dirs = [os.path.join(self.template_root, lang), os.path.join(self.template_root, "common")]
        pattern = re.compile(r"^(0|1|2|3|4|5|6|7|8|9|slash)_(\d+)\.png$", re.IGNORECASE)

        for folder in dirs:
            if not os.path.isdir(folder):
                continue
            for filename in sorted(os.listdir(folder)):
                m = pattern.match(filename)
                if not m:
                    continue
                char = m.group(1).lower()
                path = os.path.join(folder, filename)
                img = self._read_image_unicode(path, cv2.IMREAD_GRAYSCALE)
                if img is None:
                    self.logger.warning(f"白色人口模板读取失败：{path}")
                    continue
                mask = self._to_binary_mask(img)
                mask = self._tight_crop_mask(mask, padding=0)
                if mask.size == 0 or int((mask > 0).sum()) == 0:
                    self.logger.warning(f"白色人口模板为空：{path}")
                    continue
                templates[char].append((filename, mask))

        loaded_count = sum(len(v) for v in templates.values())
        if loaded_count == 0:
            self.logger.error(f"未加载到任何白色人口模板：{self.template_root}/{lang}")
        else:
            self.logger.info(f"已加载白色人口模板 lang={lang}, count={loaded_count}")

        self._templates_cache[lang] = templates
        return templates

    def make_white_text_mask(self, img_bgr: np.ndarray) -> np.ndarray:
        if img_bgr is None or img_bgr.size == 0:
            return np.zeros((1, 1), dtype=np.uint8)

        blur = int(self.white_blur_ksize)
        if blur > 1:
            if blur % 2 == 0:
                blur += 1
            img_bgr = cv2.GaussianBlur(img_bgr, (blur, blur), 0)

        b, g, r = cv2.split(img_bgr)
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

        rgb_min_mask = (r >= self.white_rgb_min) & (g >= self.white_rgb_min) & (b >= self.white_rgb_min)
        rgb_delta = np.maximum.reduce([r, g, b]) - np.minimum.reduce([r, g, b])
        neutral_mask = rgb_delta <= self.white_rgb_delta_max

        threshold = self.white_gray_min
        if self.white_use_percentile:
            dynamic_threshold = int(np.percentile(gray, self.white_percentile))
            threshold = max(threshold, dynamic_threshold)
        gray_mask = gray >= threshold

        mask = (rgb_min_mask & neutral_mask & gray_mask).astype(np.uint8) * 255

        if self.white_dilate_iter > 0:
            kernel = np.ones((2, 2), np.uint8)
            mask = cv2.dilate(mask, kernel, iterations=self.white_dilate_iter)

        if self.white_erode_iter > 0:
            kernel = np.ones((2, 2), np.uint8)
            mask = cv2.erode(mask, kernel, iterations=self.white_erode_iter)

        return mask

    def _prepare_roi_mask(
        self,
        img_bgr: np.ndarray,
        lang: str,
        scale_factor: Optional[float] = None,
        use_debug_roi: bool = False,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, Tuple[int, int, int, int], Tuple[int, int, int, int]]:
        if img_bgr is None or img_bgr.size == 0:
            raise ValueError("img_bgr is empty")

        if scale_factor is None:
            scale_factor = img_bgr.shape[1] / 1920.0
        scale_factor = float(scale_factor)

        base_roi = self.get_base_roi(lang, use_debug_roi=use_debug_roi)
        sx, sy, sw, sh = self._scaled_roi(base_roi, scale_factor, img_bgr.shape)
        roi_raw = img_bgr[sy:sy + sh, sx:sx + sw].copy()
        roi_mask = self.make_white_text_mask(roi_raw)

        # 将不同分辨率下的 ROI mask 归一化到 1920 基准 ROI 尺寸，再按模板倍率放大。
        if self.normalize_roi_to_base_size:
            _, _, base_w, base_h = base_roi
            roi_norm = cv2.resize(roi_mask, (int(base_w), int(base_h)), interpolation=cv2.INTER_NEAREST)
        else:
            roi_norm = roi_mask

        if self.template_scale > 1:
            h, w = roi_norm.shape[:2]
            roi_scaled = cv2.resize(
                roi_norm,
                (w * self.template_scale, h * self.template_scale),
                interpolation=cv2.INTER_NEAREST,
            )
        else:
            roi_scaled = roi_norm.copy()

        return roi_raw, roi_mask, roi_scaled, (sx, sy, sw, sh), base_roi

    @staticmethod
    def _iou(a: SupplyCandidate, b: SupplyCandidate) -> float:
        ax1, ay1, ax2, ay2 = a.x, a.y, a.x + a.w, a.y + a.h
        bx1, by1, bx2, by2 = b.x, b.y, b.x + b.w, b.y + b.h
        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
        inter = iw * ih
        if inter <= 0:
            return 0.0
        union = a.area + b.area - inter
        return inter / max(1, union)

    def _nms_same_char(self, candidates: Sequence[SupplyCandidate]) -> List[SupplyCandidate]:
        if not candidates:
            return []

        by_char: Dict[str, List[SupplyCandidate]] = {}
        for c in candidates:
            by_char.setdefault(c.char, []).append(c)

        kept_all: List[SupplyCandidate] = []
        for char, group in by_char.items():
            group = sorted(group, key=lambda c: c.score, reverse=True)
            kept: List[SupplyCandidate] = []
            for c in group:
                duplicate = False
                for k in kept:
                    center_close = abs(c.cx - k.cx) <= self.SAME_CHAR_CENTER_TOLERANCE and abs(c.cy - k.cy) <= self.SAME_CHAR_CENTER_TOLERANCE
                    if center_close or self._iou(c, k) >= self.SAME_CHAR_NMS_IOU:
                        duplicate = True
                        break
                if not duplicate:
                    kept.append(c)
                if len(kept) >= self.MAX_CANDIDATES_PER_CHAR_AFTER_NMS:
                    break
            kept_all.extend(kept)

        return sorted(kept_all, key=lambda c: c.score, reverse=True)

    def _match_templates(self, roi_scaled_mask: np.ndarray, lang: str) -> List[SupplyCandidate]:
        templates = self._load_templates_for_lang(lang)
        candidates: List[SupplyCandidate] = []

        if roi_scaled_mask is None or roi_scaled_mask.size == 0:
            return candidates

        roi = self._to_binary_mask(roi_scaled_mask)
        roi_h, roi_w = roi.shape[:2]

        local_kernel_size = max(1, int(self.LOCAL_MAX_KERNEL))
        local_kernel = np.ones((local_kernel_size, local_kernel_size), np.uint8)

        for char, tpl_list in templates.items():
            threshold = self.slash_threshold if char == "slash" else self.digit_threshold
            text = "/" if char == "slash" else char

            for template_name, tpl in tpl_list:
                tpl_h, tpl_w = tpl.shape[:2]
                if tpl_w <= 0 or tpl_h <= 0:
                    continue
                if tpl_w > roi_w or tpl_h > roi_h:
                    self.logger.debug(
                        f"跳过过大的模板 {template_name}: tpl={tpl_w}x{tpl_h}, roi={roi_w}x{roi_h}"
                    )
                    continue

                # 二值图上使用归一化相关匹配。ROI 与模板都已经是黑底白字。
                result = cv2.matchTemplate(roi, tpl, cv2.TM_CCOEFF_NORMED)
                if result.size == 0:
                    continue

                # 只取局部峰值，避免同一字符周围产生一大片重复候选。
                dilated = cv2.dilate(result, local_kernel)
                mask = (result >= threshold) & (result == dilated)
                ys, xs = np.where(mask)
                if len(xs) == 0:
                    continue

                scored_points = [(float(result[y, x]), int(x), int(y)) for y, x in zip(ys, xs)]
                scored_points.sort(key=lambda item: item[0], reverse=True)
                scored_points = scored_points[: self.MAX_CANDIDATES_PER_TEMPLATE]

                for score, x, y in scored_points:
                    candidates.append(
                        SupplyCandidate(
                            char=char,
                            text=text,
                            x=x,
                            y=y,
                            w=int(tpl_w),
                            h=int(tpl_h),
                            score=score,
                            template_name=template_name,
                        )
                    )

        return self._nms_same_char(candidates)

    def _is_digit_from_slash_region(self, digit: SupplyCandidate, slash: SupplyCandidate) -> bool:
        """
        判断某个数字候选是否其实是 slash 区域造成的误匹配。

        不能简单按 digit.cx 靠近 slash.cx 就删除，因为真实的 / 左侧数字可能和 / 横向重叠。
        这里只过滤两类更明确的情况：
        1. 数字候选中心点落在 slash 框内部，且分数不明显高于 slash；
        2. 数字候选框和 slash 框有较大 IoU，且分数低于 slash。
        """
        margin = int(self.SLASH_DIGIT_CENTER_INSIDE_MARGIN)
        sx1 = slash.x - margin
        sy1 = slash.y - margin
        sx2 = slash.x + slash.w + margin
        sy2 = slash.y + slash.h + margin

        center_inside_slash = sx1 <= digit.cx <= sx2 and sy1 <= digit.cy <= sy2
        if center_inside_slash and digit.score <= slash.score + 0.05:
            return True

        if digit.score <= slash.score and self._iou(digit, slash) >= self.SLASH_DIGIT_OVERLAP_IOU:
            return True

        return False

    @staticmethod
    def _overlap_stats(a: SupplyCandidate, b: SupplyCandidate) -> Tuple[int, int, float, float]:
        ax1, ay1, ax2, ay2 = a.x, a.y, a.x + a.w, a.y + a.h
        bx1, by1, bx2, by2 = b.x, b.y, b.x + b.w, b.y + b.h
        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        overlap_w = max(0, ix2 - ix1)
        overlap_h = max(0, iy2 - iy1)
        overlap_w_ratio = overlap_w / max(1, min(a.w, b.w))
        overlap_h_ratio = overlap_h / max(1, min(a.h, b.h))
        return overlap_w, overlap_h, overlap_w_ratio, overlap_h_ratio

    def _filter_embedded_digit_noise(self, digit_candidates: Sequence[SupplyCandidate]) -> List[SupplyCandidate]:
        """
        过滤被其他更强数字包含/压住的低分假候选。

        典型例子：英文 12/15 中，数字 2 和 5 的左侧竖笔画会匹配出额外的 1，
        导致 12/15 被解析成 112/115。真实相邻数字通常不会互相覆盖；
        假候选则会和右侧强数字产生明显横向重叠。
        """
        digits = list(digit_candidates)
        if len(digits) <= 1:
            return digits

        remove_ids = set()
        for i, cand in enumerate(digits):
            for j, other in enumerate(digits):
                if i == j:
                    continue
                if other.score - cand.score < self.EMBEDDED_DIGIT_SCORE_GAP:
                    continue

                overlap_w, overlap_h, wr, hr = self._overlap_stats(cand, other)
                if overlap_w <= 0 or overlap_h <= 0:
                    continue

                if wr >= self.EMBEDDED_DIGIT_OVERLAP_RATIO and hr >= self.EMBEDDED_DIGIT_VERTICAL_OVERLAP_RATIO:
                    remove_ids.add(i)
                    break

        return [c for idx, c in enumerate(digits) if idx not in remove_ids]

    def _cluster_digits_by_x(self, digit_candidates: Sequence[SupplyCandidate]) -> List[SupplyCandidate]:
        """
        同一真实数字可能被多个数字模板命中。
        按中心 x 聚类，每组保留分数最高的候选。

        保留这个方法主要用于兼容调试；正式解析使用 _cluster_digit_alternatives_by_x()。
        """
        digit_candidates = self._filter_embedded_digit_noise(digit_candidates)
        clusters = self._cluster_digit_alternatives_by_x(digit_candidates)
        return [cluster[0] for cluster in clusters if cluster]

    def _cluster_digit_alternatives_by_x(self, digit_candidates: Sequence[SupplyCandidate]) -> List[List[SupplyCandidate]]:
        """
        按横向中心聚类数字候选。

        与 _cluster_digits_by_x 不同，这里每个位置保留多个备选。
        例如同一位置同时命中 6 和 8 时，不立即选最高分，而是在整串解析时尝试组合。
        这样 160/179 不会因为 6 被 8 略高分压掉而变成 180/179。
        """
        if not digit_candidates:
            return []

        items = sorted(digit_candidates, key=lambda c: c.cx)
        raw_clusters: List[List[SupplyCandidate]] = []

        for c in items:
            if not raw_clusters:
                raw_clusters.append([c])
                continue

            last_cluster = raw_clusters[-1]
            cluster_cx = sum(item.cx for item in last_cluster) / len(last_cluster)
            if abs(c.cx - cluster_cx) <= self.SAME_CHAR_CENTER_TOLERANCE:
                last_cluster.append(c)
            else:
                raw_clusters.append([c])

        clusters: List[List[SupplyCandidate]] = []
        for cluster in raw_clusters:
            # 同一位置同一数字可能有多张模板命中，先按数字类型只保留最高分。
            best_by_text: Dict[str, SupplyCandidate] = {}
            for c in cluster:
                old = best_by_text.get(c.text)
                if old is None or c.score > old.score:
                    best_by_text[c.text] = c

            alternatives = sorted(best_by_text.values(), key=lambda c: c.score, reverse=True)
            alternatives = alternatives[: max(1, int(self.DIGIT_ALTERNATIVES_PER_POSITION))]
            clusters.append(alternatives)

        return clusters

    def _parse_candidates(
        self,
        candidates: Sequence[SupplyCandidate],
        lang: str,
        roi: Tuple[int, int, int, int],
    ) -> Optional[SupplyResult]:
        if not candidates:
            return None

        slash_candidates = [c for c in candidates if c.char == "slash"]
        digit_candidates = [c for c in candidates if c.char != "slash" and c.text.isdigit()]
        digit_candidates = self._filter_embedded_digit_noise(digit_candidates)
        if not digit_candidates:
            return None

        if not slash_candidates:
            if self.INFER_SLASH_IF_MISSING:
                return self._parse_candidates_without_slash(digit_candidates, lang=lang, roi=roi)
            return None

        slash_candidates = sorted(slash_candidates, key=lambda c: c.score, reverse=True)
        best_result: Optional[SupplyResult] = None
        best_rank_score = -999.0

        for slash in slash_candidates[:8]:
            left_digits: List[SupplyCandidate] = []
            right_digits: List[SupplyCandidate] = []

            for d in digit_candidates:
                # 注意：/ 的外框可能与左侧数字横向重叠。
                # 不能按“距离 slash 近”粗暴删除数字；但如果数字候选本身落在 slash 框内，
                # 基本就是 / 被 1/7 等模板误命中，应当过滤掉。
                if self._is_digit_from_slash_region(d, slash):
                    continue

                # 只用字符中心点判断左右，最后交给格式校验和分数排序处理。
                if d.cx < slash.cx:
                    left_digits.append(d)
                elif d.cx > slash.cx:
                    right_digits.append(d)

            left_clusters = self._cluster_digit_alternatives_by_x(left_digits)
            right_clusters = self._cluster_digit_alternatives_by_x(right_digits)

            # 人口左边一般 1-3 位，右边一般 2-3 位。
            if not (1 <= len(left_clusters) <= 3 and 2 <= len(right_clusters) <= 3):
                continue

            for left_combo in itertools.product(*left_clusters):
                for right_combo in itertools.product(*right_clusters):
                    left_selected = list(left_combo)
                    right_selected = list(right_combo)

                    left_text = "".join(c.text for c in left_selected)
                    right_text = "".join(c.text for c in right_selected)
                    raw = f"{left_text}/{right_text}"

                    if not re.match("^[0-9]{1,3}/[0-9]{2,3}$", raw):
                        continue

                    try:
                        current = int(left_text)
                        max_supply = int(right_text)
                    except ValueError:
                        continue

                    if current < 0 or current > self.MAX_CURRENT_SUPPLY:
                        continue
                    if max_supply < self.MIN_MAX_SUPPLY or max_supply > self.MAX_MAX_SUPPLY:
                        continue
                    # 这里保留 current <= max 校验。
                    # SC2 如果真的超占用，人口通常会变红；本模块只识别白字，红字无需触发提醒。
                    # 同时这个校验能把 160/179 被误读成 180/179 之类结果过滤掉。
                    if current > max_supply:
                        continue

                    selected = left_selected + [slash] + right_selected
                    avg_score = sum(c.score for c in selected) / max(1, len(selected))

                    # 轻微偏好更完整的解析，避免只识别到 9/00 这类少字符结果。
                    completeness_bonus = 0.015 * len(selected)

                    # slash 分数很关键，额外给一点权重。
                    slash_bonus = 0.04 * slash.score

                    rank_score = avg_score + completeness_bonus + slash_bonus

                    if rank_score > best_rank_score:
                        best_rank_score = rank_score
                        best_result = SupplyResult(
                            current=current,
                            max=max_supply,
                            raw=raw,
                            score=avg_score,
                            lang=self.normalize_lang(lang),
                            roi=roi,
                            candidates=list(candidates),
                            selected=selected,
                        )

        if best_result is None and self.INFER_SLASH_IF_MISSING:
            # slash 有候选但位置/分数不理想时，仍尝试用数字间距兜底。
            best_result = self._parse_candidates_without_slash(digit_candidates, lang=lang, roi=roi)

        return best_result

    def _parse_candidates_without_slash(
        self,
        digit_candidates: Sequence[SupplyCandidate],
        lang: str,
        roi: Tuple[int, int, int, int],
    ) -> Optional[SupplyResult]:
        """
        slash 模板没有命中时的兜底解析。

        做法：
        - 将数字候选按横向中心聚成多个“数字位置”；
        - 尝试把这些位置切成 current/max 两段；
        - 优先选择切分处横向空隙最大的结果；
        - 保留 current <= max 校验，避免把 160/179 误读成 180/179。
        """
        clusters = self._cluster_digit_alternatives_by_x(digit_candidates)
        if not (3 <= len(clusters) <= 6):
            return None

        centers = []
        for cluster in clusters:
            if not cluster:
                return None
            centers.append(sum(c.cx for c in cluster) / len(cluster))

        gaps = [centers[i] - centers[i - 1] for i in range(1, len(centers))]
        if not gaps:
            return None

        sorted_gaps = sorted(gaps)
        median_gap = sorted_gaps[len(sorted_gaps) // 2]
        min_gap = max(float(self.MIN_INFER_SEPARATOR_GAP), median_gap * 1.35)

        best_result: Optional[SupplyResult] = None
        best_rank_score = -999.0

        total_positions = len(clusters)
        for split in range(1, total_positions):
            left_len = split
            right_len = total_positions - split
            if not (1 <= left_len <= 3 and 2 <= right_len <= 3):
                continue

            split_gap = centers[split] - centers[split - 1]
            if split_gap < min_gap:
                continue

            left_clusters = clusters[:split]
            right_clusters = clusters[split:]

            for left_combo in itertools.product(*left_clusters):
                for right_combo in itertools.product(*right_clusters):
                    left_selected = list(left_combo)
                    right_selected = list(right_combo)
                    left_text = "".join(c.text for c in left_selected)
                    right_text = "".join(c.text for c in right_selected)
                    raw = f"{left_text}/{right_text}"

                    if not re.match("^[0-9]{1,3}/[0-9]{2,3}$", raw):
                        continue

                    try:
                        current = int(left_text)
                        max_supply = int(right_text)
                    except ValueError:
                        continue

                    if current < 0 or current > self.MAX_CURRENT_SUPPLY:
                        continue
                    if max_supply < self.MIN_MAX_SUPPLY or max_supply > self.MAX_MAX_SUPPLY:
                        continue
                    if current > max_supply:
                        continue

                    selected = left_selected + right_selected
                    avg_score = sum(c.score for c in selected) / max(1, len(selected))
                    completeness_bonus = 0.015 * len(selected)

                    # 越像分隔符位置的空隙，得分越高。
                    gap_bonus = min(0.08, (split_gap / max(1.0, median_gap) - 1.0) * 0.04)
                    rank_score = avg_score + completeness_bonus + gap_bonus

                    if rank_score > best_rank_score:
                        best_rank_score = rank_score
                        best_result = SupplyResult(
                            current=current,
                            max=max_supply,
                            raw=raw,
                            score=avg_score,
                            lang=self.normalize_lang(lang),
                            roi=roi,
                            candidates=list(digit_candidates),
                            selected=selected,
                        )

        return best_result

    def recognize(
        self,
        img_bgr: np.ndarray,
        lang: Optional[str] = None,
        scale_factor: Optional[float] = None,
        use_debug_roi: bool = False,
        save_debug: Optional[bool] = None,
    ) -> Optional[dict]:
        """
        识别人口。

        返回：
            {
                "current": 39,
                "max": 100,
                "raw": "39/100",
                "score": 0.86,
                "lang": "cn",
                "roi": (1805, 18, 82, 22),
                "candidates": [...],
                "selected": [...]
            }

        失败返回 None。
        """
        lang = self.normalize_lang(lang)

        roi_raw, roi_mask, roi_scaled, roi, base_roi = self._prepare_roi_mask(
            img_bgr,
            lang=lang,
            scale_factor=scale_factor,
            use_debug_roi=use_debug_roi,
        )
        candidates = self._match_templates(roi_scaled, lang)
        result = self._parse_candidates(candidates, lang=lang, roi=roi)

        do_debug = self.debug if save_debug is None else bool(save_debug)
        if do_debug:
            self._save_debug_images(
                roi_raw=roi_raw,
                roi_mask=roi_mask,
                roi_scaled=roi_scaled,
                candidates=candidates,
                selected=result.selected if result else [],
                result=result,
                lang=lang,
                base_roi=base_roi,
            )

        if result is None:
            return None
        return result.to_dict()

    def _save_debug_images(
        self,
        roi_raw: np.ndarray,
        roi_mask: np.ndarray,
        roi_scaled: np.ndarray,
        candidates: Sequence[SupplyCandidate],
        selected: Sequence[SupplyCandidate],
        result: Optional[SupplyResult],
        lang: str,
        base_roi: Tuple[int, int, int, int],
    ):
        os.makedirs(self.debug_dir, exist_ok=True)

        self._save_png_unicode(os.path.join(self.debug_dir, f"supply_{lang}_roi_raw.png"), roi_raw)
        self._save_png_unicode(os.path.join(self.debug_dir, f"supply_{lang}_roi_mask.png"), roi_mask)
        self._save_png_unicode(os.path.join(self.debug_dir, f"supply_{lang}_roi_scaled.png"), roi_scaled)

        canvas = cv2.cvtColor(roi_scaled, cv2.COLOR_GRAY2BGR)

        # 候选框：灰色；最终选中：绿色；slash：黄色。
        for c in candidates:
            color = (90, 90, 90)
            cv2.rectangle(canvas, (c.x, c.y), (c.x + c.w, c.y + c.h), color, 1)

        selected_ids = {(c.char, c.x, c.y, c.w, c.h, c.template_name) for c in selected}
        for c in selected:
            color = (0, 220, 0) if c.char != "slash" else (0, 220, 220)
            cv2.rectangle(canvas, (c.x, c.y), (c.x + c.w, c.y + c.h), color, 1)
            cv2.putText(
                canvas,
                c.text,
                (c.x, max(8, c.y - 2)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.35,
                color,
                1,
                cv2.LINE_AA,
            )

        title = result.raw if result else "None"
        cv2.putText(
            canvas,
            f"{title}  base_roi={base_roi}",
            (2, max(10, canvas.shape[0] - 4)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.35,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        self._save_png_unicode(os.path.join(self.debug_dir, f"supply_{lang}_matches.png"), canvas)

        # 额外写一份文本，方便看候选。
        txt_path = os.path.join(self.debug_dir, f"supply_{lang}_matches.txt")
        try:
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(f"result: {result.to_dict() if result else None}\n")
                f.write("\nTop candidates:\n")
                for c in sorted(candidates, key=lambda item: item.score, reverse=True)[:80]:
                    mark = "*" if (c.char, c.x, c.y, c.w, c.h, c.template_name) in selected_ids else " "
                    f.write(
                        f"{mark} char={c.text:<2} score={c.score:.3f} "
                        f"x={c.x:<4} y={c.y:<4} w={c.w:<3} h={c.h:<3} tpl={c.template_name}\n"
                    )
        except Exception:
            pass


def _main():
    parser = argparse.ArgumentParser(description="Test WhiteSupplyRecognizer")
    parser.add_argument("image", help="截图路径")
    parser.add_argument("--lang", default="cn", choices=["cn", "en"], help="游戏语言")
    parser.add_argument("--scale", type=float, default=None, help="截图缩放倍数；默认按宽度/1920 自动计算")
    parser.add_argument("--debug", action="store_true", help="保存 debug 图")
    parser.add_argument("--debug-roi", action="store_true", help="使用更大的调试 ROI")
    parser.add_argument("--debug-dir", default=None, help="debug 输出目录")
    parser.add_argument("--template-root", default=None, help="模板根目录，默认 resources/templates/white_supply")
    args = parser.parse_args()

    img = WhiteSupplyRecognizer._read_image_unicode(args.image, cv2.IMREAD_COLOR)
    if img is None:
        print(f"无法读取图片：{args.image}")
        return 2

    recognizer = WhiteSupplyRecognizer(
        template_root=args.template_root,
        debug=args.debug,
        debug_dir=args.debug_dir,
    )
    result = recognizer.recognize(
        img,
        lang=args.lang,
        scale_factor=args.scale,
        use_debug_roi=args.debug_roi,
        save_debug=args.debug,
    )

    if result is None:
        print("Result: None")
        if args.debug:
            print(f"Debug 已输出到：{recognizer.debug_dir}")
        return 1

    print(f"Result: {result['raw']}")
    print(f"current={result['current']}, max={result['max']}, score={result['score']:.3f}")
    print(f"roi={result['roi']}, lang={result['lang']}")
    if args.debug:
        print(f"Debug 已输出到：{recognizer.debug_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
