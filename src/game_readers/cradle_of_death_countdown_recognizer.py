# -*- coding: utf-8 -*-
"""
Cradle of Death countdown recognizer.

This module only recognizes white countdown digits inside a screenshot ROI. It
is intentionally standalone: no global state reads, no threads, no UI, no Toast,
and no integration with map handlers.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from src.game_readers.white_supply_recognizer import WhiteSupplyRecognizer
from src.utils.fileutil import get_project_root
from src.utils.logging_util import get_logger


Roi = Tuple[int, int, int, int]


@dataclass(frozen=True)
class CradleCountdownConfig:
    roi_by_lang: Dict[str, Roi] = field(
        default_factory=lambda: {
            "cn": (1795, 141, 37, 14),
            # Placeholder until English screenshots/templates are calibrated.
            "en": (1795, 141, 37, 14),
        }
    )
    template_scale: int = 4
    normalize_roi_to_base_size: bool = True
    match_threshold: float = 0.55
    max_candidates_per_template: int = 30
    max_candidates_after_nms: int = 6
    nms_iou: float = 0.25
    same_center_tolerance: int = 8
    local_max_kernel: int = 3
    use_common_templates: bool = True

    # Same defaults as WhiteSupplyRecognizer's verified white text pipeline.
    white_gray_min: int = WhiteSupplyRecognizer.WHITE_GRAY_MIN
    white_rgb_min: int = WhiteSupplyRecognizer.WHITE_RGB_MIN
    white_rgb_delta_max: int = WhiteSupplyRecognizer.WHITE_RGB_DELTA_MAX
    white_percentile: int = WhiteSupplyRecognizer.WHITE_PERCENTILE
    white_use_percentile: bool = WhiteSupplyRecognizer.WHITE_USE_PERCENTILE
    white_blur_ksize: int = WhiteSupplyRecognizer.WHITE_BLUR_KSIZE
    white_dilate_iter: int = WhiteSupplyRecognizer.WHITE_DILATE_ITER
    white_erode_iter: int = WhiteSupplyRecognizer.WHITE_ERODE_ITER


@dataclass
class CountdownCandidate:
    digit: str
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

    def to_dict(self) -> dict:
        return {
            "digit": self.digit,
            "x": self.x,
            "y": self.y,
            "w": self.w,
            "h": self.h,
            "score": self.score,
            "template_name": self.template_name,
        }


class CradleOfDeathCountdownRecognizer:
    """Template matcher for Cradle of Death countdown digits."""

    TEMPLATE_DIR_NAME = "cradle_of_death_digits"
    TEMPLATE_NAME_RE = re.compile(r".+\.(png|bmp|jpg|jpeg)$", re.IGNORECASE)

    def __init__(
        self,
        template_root: Optional[str] = None,
        config: Optional[CradleCountdownConfig] = None,
        debug_dir: Optional[str] = None,
    ):
        self.logger = get_logger(__name__)
        self.config = config or CradleCountdownConfig()
        self.template_root = template_root or os.path.join(
            get_project_root(), "resources", "templates", self.TEMPLATE_DIR_NAME
        )
        self.debug_dir = debug_dir or os.path.join(os.getcwd(), "tests", "debug_cradle_of_death_countdown")
        self._templates_cache: Dict[str, Dict[str, List[Tuple[str, np.ndarray]]]] = {}

        # Attribute names intentionally match WhiteSupplyRecognizer so its
        # make_white_text_mask implementation can be reused directly.
        self.white_gray_min = int(self.config.white_gray_min)
        self.white_rgb_min = int(self.config.white_rgb_min)
        self.white_rgb_delta_max = int(self.config.white_rgb_delta_max)
        self.white_percentile = int(self.config.white_percentile)
        self.white_use_percentile = bool(self.config.white_use_percentile)
        self.white_blur_ksize = int(self.config.white_blur_ksize)
        self.white_dilate_iter = int(self.config.white_dilate_iter)
        self.white_erode_iter = int(self.config.white_erode_iter)

    @staticmethod
    def normalize_lang(lang: Optional[str]) -> str:
        value = str(lang or "cn").strip().lower()
        if value in {"zh", "zh-cn", "zh_cn", "chs", "cht", "cn", "chinese"}:
            return "cn"
        if value in {"en", "eng", "english"}:
            return "en"
        return "cn"

    @staticmethod
    def _read_image_unicode(path: str, flags=cv2.IMREAD_COLOR) -> Optional[np.ndarray]:
        return WhiteSupplyRecognizer._read_image_unicode(path, flags)

    @staticmethod
    def _save_png_unicode(path: str, image: np.ndarray) -> bool:
        return WhiteSupplyRecognizer._save_png_unicode(path, image)

    @staticmethod
    def _to_binary_mask(gray: np.ndarray) -> np.ndarray:
        return WhiteSupplyRecognizer._to_binary_mask(gray)

    @staticmethod
    def _tight_crop_mask(mask: np.ndarray, padding: int = 0) -> np.ndarray:
        return WhiteSupplyRecognizer._tight_crop_mask(mask, padding=padding)

    def make_white_text_mask(self, img_bgr: np.ndarray) -> np.ndarray:
        return WhiteSupplyRecognizer.make_white_text_mask(self, img_bgr)

    def get_base_roi(self, lang: Optional[str] = "cn") -> Roi:
        normalized = self.normalize_lang(lang)
        if normalized in self.config.roi_by_lang:
            return tuple(self.config.roi_by_lang[normalized])
        return tuple(self.config.roi_by_lang["cn"])

    @staticmethod
    def offset_roi(roi: Roi, dx: int = 0, dy: int = 0) -> Roi:
        x, y, w, h = roi
        return x + int(dx), y + int(dy), w, h

    @staticmethod
    def _scaled_roi(base_roi: Roi, scale_factor: float, image_shape: Tuple[int, int, int]) -> Roi:
        return WhiteSupplyRecognizer._scaled_roi(base_roi, scale_factor, image_shape)

    def _load_templates_for_lang(self, lang: str) -> Dict[str, List[Tuple[str, np.ndarray]]]:
        lang = self.normalize_lang(lang)
        if lang in self._templates_cache:
            return self._templates_cache[lang]

        templates: Dict[str, List[Tuple[str, np.ndarray]]] = {str(i): [] for i in range(10)}
        lang_dirs = [os.path.join(self.template_root, lang)]
        if self.config.use_common_templates:
            lang_dirs.append(os.path.join(self.template_root, "common"))

        for lang_dir in lang_dirs:
            if not os.path.isdir(lang_dir):
                continue

            for digit in templates:
                digit_dir = os.path.join(lang_dir, digit)
                if not os.path.isdir(digit_dir):
                    continue

                for filename in sorted(os.listdir(digit_dir)):
                    if not self.TEMPLATE_NAME_RE.match(filename):
                        continue
                    path = os.path.join(digit_dir, filename)
                    img = self._read_image_unicode(path, cv2.IMREAD_GRAYSCALE)
                    if img is None:
                        self.logger.warning("Failed to read Cradle countdown template: %s", path)
                        continue

                    mask = self._to_binary_mask(img)
                    mask = self._tight_crop_mask(mask, padding=0)
                    if mask.size == 0 or int((mask > 0).sum()) == 0:
                        self.logger.warning("Empty Cradle countdown template skipped: %s", path)
                        continue
                    templates[digit].append((filename, mask))

        loaded_count = sum(len(v) for v in templates.values())
        if loaded_count == 0:
            self.logger.warning("No Cradle countdown templates loaded for lang=%s from: %s", lang, self.template_root)
        else:
            self.logger.info("Loaded Cradle countdown templates lang=%s count=%s", lang, loaded_count)

        self._templates_cache[lang] = templates
        return templates

    def _prepare_roi(
        self,
        game_screen: np.ndarray,
        lang: str,
        scale_factor: float,
        roi_override: Optional[Roi] = None,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, Roi, Roi]:
        base_roi = tuple(roi_override or self.get_base_roi(lang))
        sx, sy, sw, sh = self._scaled_roi(base_roi, scale_factor, game_screen.shape)
        roi_raw = game_screen[sy:sy + sh, sx:sx + sw].copy()
        roi_mask = self.make_white_text_mask(roi_raw)

        if self.config.normalize_roi_to_base_size:
            _, _, base_w, base_h = base_roi
            roi_norm = cv2.resize(roi_mask, (int(base_w), int(base_h)), interpolation=cv2.INTER_NEAREST)
        else:
            roi_norm = roi_mask

        if self.config.template_scale > 1:
            h, w = roi_norm.shape[:2]
            roi_scaled = cv2.resize(
                roi_norm,
                (w * self.config.template_scale, h * self.config.template_scale),
                interpolation=cv2.INTER_NEAREST,
            )
        else:
            roi_scaled = roi_norm.copy()

        return roi_raw, roi_mask, roi_scaled, (sx, sy, sw, sh), base_roi

    @staticmethod
    def _iou(a: CountdownCandidate, b: CountdownCandidate) -> float:
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

    def _nms(self, candidates: Sequence[CountdownCandidate]) -> List[CountdownCandidate]:
        kept: List[CountdownCandidate] = []
        for cand in sorted(candidates, key=lambda c: c.score, reverse=True):
            duplicate = False
            for old in kept:
                center_close = (
                    abs(cand.cx - old.cx) <= self.config.same_center_tolerance
                    and abs(cand.cy - old.cy) <= self.config.same_center_tolerance
                )
                if center_close or self._iou(cand, old) >= self.config.nms_iou:
                    duplicate = True
                    break
            if not duplicate:
                kept.append(cand)
            if len(kept) >= int(self.config.max_candidates_after_nms):
                break
        return sorted(kept, key=lambda c: c.cx)

    def _match_templates(self, roi_scaled_mask: np.ndarray, lang: str) -> List[CountdownCandidate]:
        templates = self._load_templates_for_lang(lang)
        roi = self._to_binary_mask(roi_scaled_mask)
        roi_h, roi_w = roi.shape[:2]
        candidates: List[CountdownCandidate] = []

        local_kernel_size = max(1, int(self.config.local_max_kernel))
        local_kernel = np.ones((local_kernel_size, local_kernel_size), np.uint8)

        for digit, tpl_list in templates.items():
            for template_name, tpl in tpl_list:
                tpl_h, tpl_w = tpl.shape[:2]
                if tpl_w <= 0 or tpl_h <= 0 or tpl_w > roi_w or tpl_h > roi_h:
                    continue

                result = cv2.matchTemplate(roi, tpl, cv2.TM_CCOEFF_NORMED)
                if result.size == 0:
                    continue

                dilated = cv2.dilate(result, local_kernel)
                mask = (result >= float(self.config.match_threshold)) & (result == dilated)
                ys, xs = np.where(mask)
                if len(xs) == 0:
                    continue

                scored_points = [(float(result[y, x]), int(x), int(y)) for y, x in zip(ys, xs)]
                scored_points.sort(key=lambda item: item[0], reverse=True)
                scored_points = scored_points[: int(self.config.max_candidates_per_template)]

                for score, x, y in scored_points:
                    candidates.append(
                        CountdownCandidate(
                            digit=digit,
                            x=x,
                            y=y,
                            w=int(tpl_w),
                            h=int(tpl_h),
                            score=score,
                            template_name=template_name,
                        )
                    )

        return self._nms(candidates)

    @staticmethod
    def _binary_f1_score(candidate: np.ndarray, template: np.ndarray) -> float:
        if candidate is None or candidate.size == 0 or template is None or template.size == 0:
            return -1.0
        candidate = CradleOfDeathCountdownRecognizer._to_binary_mask(candidate)
        template = CradleOfDeathCountdownRecognizer._to_binary_mask(template)
        resized = cv2.resize(
            candidate,
            (template.shape[1], template.shape[0]),
            interpolation=cv2.INTER_NEAREST,
        )
        cand_on = resized > 0
        tpl_on = template > 0
        denom = int(cand_on.sum()) + int(tpl_on.sum())
        if denom <= 0:
            return -1.0
        return float(2.0 * int((cand_on & tpl_on).sum()) / denom)

    def _segment_digit_runs(self, roi_mask: np.ndarray) -> List[Tuple[int, int]]:
        mask = self._to_binary_mask(roi_mask)
        if mask is None or mask.size == 0:
            return []

        active_cols = [x for x in range(mask.shape[1]) if int((mask[:, x] > 0).sum()) > 0]
        if not active_cols:
            return []

        runs: List[Tuple[int, int]] = []
        start = active_cols[0]
        last = active_cols[0]
        max_gap_inside_digit = 2
        for x in active_cols[1:]:
            if x - last <= max_gap_inside_digit:
                last = x
            else:
                runs.append((start, last))
                start = x
                last = x
        runs.append((start, last))

        filtered = []
        run_stats = []
        for x1, x2 in runs:
            width = x2 - x1 + 1
            segment = mask[:, x1:x2 + 1]
            pixels = int((segment > 0).sum())
            ys, _ = np.where(segment > 0)
            height = int(ys.max() - ys.min() + 1) if len(ys) else 0
            if width >= 2 and pixels >= 3:
                filtered.append((x1, x2))
                run_stats.append({"width": width, "pixels": pixels, "height": height})

        # Some SC2 countdown captures keep the colon in the white mask. The
        # colon is an internal, very narrow run; drop it before accepting 3/4
        # digit results. Pure digit captures such as 1301/1300 are unaffected.
        if len(filtered) in (4, 5):
            colon_index = None
            for index in range(1, len(filtered) - 1):
                stats = run_stats[index]
                if stats["width"] <= 2 and stats["pixels"] <= 10:
                    colon_index = index
                    break
            if colon_index is not None:
                filtered.pop(colon_index)

        return filtered

    def _match_segment_alternatives(
        self,
        roi_mask: np.ndarray,
        x1: int,
        x2: int,
        lang: str,
        alternatives_per_segment: int = 4,
    ) -> List[CountdownCandidate]:
        templates = self._load_templates_for_lang(lang)
        mask = self._to_binary_mask(roi_mask)
        padded_x1 = max(0, x1 - 1)
        padded_x2 = min(mask.shape[1] - 1, x2 + 1)
        column_crop = mask[:, padded_x1:padded_x2 + 1]
        ys, xs = np.where(column_crop > 0)
        if len(xs) == 0 or len(ys) == 0:
            return []

        crop_x1 = int(xs.min())
        crop_x2 = int(xs.max()) + 1
        crop_y1 = int(ys.min())
        crop_y2 = int(ys.max()) + 1
        crop = column_crop[crop_y1:crop_y2, crop_x1:crop_x2].copy()
        if crop.size == 0:
            return []

        best_by_digit: Dict[str, CountdownCandidate] = {}
        for digit, tpl_list in templates.items():
            for template_name, tpl in tpl_list:
                score = self._binary_f1_score(crop, tpl)
                old = best_by_digit.get(digit)
                if old is None or score > old.score:
                    scale = int(self.config.template_scale)
                    best_by_digit[digit] = CountdownCandidate(
                        digit=digit,
                        x=(padded_x1 + crop_x1) * scale,
                        y=crop_y1 * scale,
                        w=max(1, (crop_x2 - crop_x1) * scale),
                        h=max(1, (crop_y2 - crop_y1) * scale),
                        score=score,
                        template_name=template_name,
                    )

        alternatives = sorted(best_by_digit.values(), key=lambda c: c.score, reverse=True)
        return alternatives[:alternatives_per_segment]

    def _recognize_by_segments(
        self,
        roi_mask: np.ndarray,
        lang: str,
        roi: Roi,
    ) -> Tuple[Optional[dict], List[CountdownCandidate], List[List[CountdownCandidate]]]:
        runs = self._segment_digit_runs(roi_mask)
        if len(runs) not in (3, 4):
            return None, [], []

        alternatives_by_segment = [
            self._match_segment_alternatives(roi_mask, x1, x2, lang=lang)
            for x1, x2 in runs
        ]
        if any(not alternatives for alternatives in alternatives_by_segment):
            return None, [], alternatives_by_segment

        best_result: Optional[dict] = None
        best_selected: List[CountdownCandidate] = []
        best_rank = -1.0

        import itertools

        for combo in itertools.product(*alternatives_by_segment):
            combo = list(combo)
            result = self._format_result(combo, lang=lang, roi=roi)
            if result is None:
                continue
            if result["min_score"] < float(self.config.match_threshold):
                continue
            avg_score = sum(c.score for c in combo) / max(1, len(combo))
            rank = avg_score + result["min_score"] * 0.08
            if rank > best_rank:
                best_rank = rank
                best_result = result
                best_selected = combo

        return best_result, best_selected, alternatives_by_segment
    @staticmethod
    def _format_result(candidates: Sequence[CountdownCandidate], lang: str, roi: Roi) -> Optional[dict]:
        if len(candidates) not in (3, 4):
            return None

        raw_digits = "".join(c.digit for c in candidates)
        if not raw_digits.isdigit() or len(raw_digits) not in (3, 4):
            return None

        seconds = int(raw_digits[-2:])
        if seconds < 0 or seconds > 59:
            return None

        minutes = int(raw_digits[:-2])
        digit_scores = [float(c.score) for c in candidates]
        return {
            "raw_digits": raw_digits,
            "formatted_time": f"{minutes}:{seconds:02d}",
            "countdown_seconds": minutes * 60 + seconds,
            "digit_scores": digit_scores,
            "min_score": min(digit_scores),
            "lang": CradleOfDeathCountdownRecognizer.normalize_lang(lang),
            "roi": list(roi),
        }

    def analyze(
        self,
        game_screen: np.ndarray,
        lang: str = "cn",
        scale_factor: float = 1.0,
        roi: Optional[Roi] = None,
        save_debug: bool = False,
        debug_dir: Optional[str] = None,
    ) -> Tuple[Optional[dict], dict]:
        lang = self.normalize_lang(lang)
        if game_screen is None or game_screen.size == 0:
            debug_info = {"result": None, "lang": lang, "error": "empty_screen"}
            return None, debug_info

        roi_raw, roi_mask, roi_scaled, scaled_roi, base_roi = self._prepare_roi(
            game_screen,
            lang=lang,
            scale_factor=float(scale_factor),
            roi_override=roi,
        )
        candidates = self._match_templates(roi_scaled, lang=lang)
        segment_result, segment_selected, segment_alternatives = self._recognize_by_segments(
            roi_mask,
            lang=lang,
            roi=scaled_roi,
        )
        template_result = self._format_result(candidates, lang=lang, roi=scaled_roi)

        if segment_result is not None:
            result = segment_result
            selected = segment_selected
            recognition_method = "segments"
        elif segment_alternatives:
            result = None
            selected = []
            recognition_method = "segments_failed"
        else:
            result = template_result
            selected = candidates if result else []
            recognition_method = "template_window"

        debug_info = {
            "result": result,
            "lang": lang,
            "roi": list(scaled_roi),
            "base_roi": list(base_roi),
            "template_root": self.template_root,
            "threshold": float(self.config.match_threshold),
            "recognition_method": recognition_method,
            "candidates": [c.to_dict() for c in candidates],
            "segment_candidates": [c.to_dict() for c in segment_selected],
            "segment_alternatives": [
                [candidate.to_dict() for candidate in alternatives]
                for alternatives in segment_alternatives
            ],
            "selected": [c.to_dict() for c in selected],
        }

        if save_debug:
            self._save_debug_images(
                game_screen=game_screen,
                roi_raw=roi_raw,
                roi_mask=roi_mask,
                roi_scaled=roi_scaled,
                roi=scaled_roi,
                candidates=candidates,
                selected=selected,
                result=result,
                debug_info=debug_info,
                debug_dir=debug_dir,
            )

        return result, debug_info

    def recognize(
        self,
        game_screen: np.ndarray,
        lang: str = "cn",
        scale_factor: float = 1.0,
        save_debug: bool = False,
        roi: Optional[Roi] = None,
    ) -> Optional[dict]:
        result, _ = self.analyze(
            game_screen,
            lang=lang,
            scale_factor=scale_factor,
            roi=roi,
            save_debug=save_debug,
        )
        return result

    def _save_debug_images(
        self,
        game_screen: np.ndarray,
        roi_raw: np.ndarray,
        roi_mask: np.ndarray,
        roi_scaled: np.ndarray,
        roi: Roi,
        candidates: Sequence[CountdownCandidate],
        selected: Sequence[CountdownCandidate],
        result: Optional[dict],
        debug_info: dict,
        debug_dir: Optional[str] = None,
    ) -> None:
        out_dir = debug_dir or self.debug_dir
        os.makedirs(out_dir, exist_ok=True)

        original = game_screen.copy()
        x, y, w, h = roi
        cv2.rectangle(original, (x, y), (x + w, y + h), (0, 220, 0), 2)
        label = result["formatted_time"] if result else "None"
        cv2.putText(
            original,
            label,
            (x, max(12, y - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 220, 0) if result else (0, 0, 255),
            2,
            cv2.LINE_AA,
        )

        self._save_png_unicode(os.path.join(out_dir, "01_original_with_roi.png"), original)
        self._save_png_unicode(os.path.join(out_dir, "02_countdown_roi_raw.png"), roi_raw)
        self._save_png_unicode(os.path.join(out_dir, "03_countdown_roi_white_mask.png"), roi_mask)
        self._save_png_unicode(os.path.join(out_dir, "04_countdown_roi_scaled_mask.png"), roi_scaled)

        canvas = cv2.cvtColor(roi_scaled, cv2.COLOR_GRAY2BGR)
        selected_ids = {(c.digit, c.x, c.y, c.w, c.h, c.template_name) for c in selected}
        for c in candidates:
            key = (c.digit, c.x, c.y, c.w, c.h, c.template_name)
            color = (0, 220, 0) if key in selected_ids else (90, 90, 90)
            cv2.rectangle(canvas, (c.x, c.y), (c.x + c.w, c.y + c.h), color, 1)
            cv2.putText(
                canvas,
                f"{c.digit}:{c.score:.2f}",
                (c.x, max(8, c.y - 2)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.32,
                color,
                1,
                cv2.LINE_AA,
            )

        for c in selected:
            key = (c.digit, c.x, c.y, c.w, c.h, c.template_name)
            if key in selected_ids:
                cv2.rectangle(canvas, (c.x, c.y), (c.x + c.w, c.y + c.h), (0, 220, 0), 1)
                cv2.putText(
                    canvas,
                    f"{c.digit}:{c.score:.2f}",
                    (c.x, min(canvas.shape[0] - 2, c.y + c.h + 8)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.32,
                    (0, 220, 0),
                    1,
                    cv2.LINE_AA,
                )
        self._save_png_unicode(os.path.join(out_dir, "05_matches.png"), canvas)

        with open(os.path.join(out_dir, "matches.json"), "w", encoding="utf-8") as f:
            json.dump(debug_info, f, ensure_ascii=False, indent=2)

        with open(os.path.join(out_dir, "matches.txt"), "w", encoding="utf-8") as f:
            f.write(f"result: {result}\n")
            f.write(f"lang: {debug_info.get('lang')}\n")
            f.write(f"roi: {debug_info.get('roi')}\n")
            f.write(f"base_roi: {debug_info.get('base_roi')}\n")
            f.write(f"template_root: {self.template_root}\n")
            f.write(f"threshold: {self.config.match_threshold:.3f}\n")
            f.write(f"recognition_method: {debug_info.get('recognition_method')}\n\n")

            f.write("Selected candidates:\n")
            for c in selected:
                f.write(
                    f"* digit={c.digit} score={c.score:.3f} "
                    f"x={c.x} y={c.y} w={c.w} h={c.h} tpl={c.template_name}\n"
                )

            f.write("\nSegment alternatives:\n")
            for index, alternatives in enumerate(debug_info.get("segment_alternatives", []), start=1):
                f.write(f"segment {index}:\n")
                for item in alternatives:
                    f.write(
                        f"  digit={item.get('digit')} score={float(item.get('score', -1.0)):.3f} "
                        f"x={item.get('x')} y={item.get('y')} w={item.get('w')} h={item.get('h')} "
                        f"tpl={item.get('template_name')}\n"
                    )

            f.write("\nTemplate-window candidates:\n")
            for c in candidates:
                mark = "*" if (c.digit, c.x, c.y, c.w, c.h, c.template_name) in selected_ids else " "
                f.write(
                    f"{mark} digit={c.digit} score={c.score:.3f} "
                    f"x={c.x} y={c.y} w={c.w} h={c.h} tpl={c.template_name}\n"
                )


__all__ = ["CradleCountdownConfig", "CradleOfDeathCountdownRecognizer", "CountdownCandidate"]