# src/detectors/minimap_red_dot_detector.py
"""
小地图红点标记检测模块。

设计目标：
1. 从 game_state_service.state.latest_screenshot 读取游戏截图。
2. 裁剪 1920x1080 基准下的小地图区域。
3. 后台持续检测红点候选。
4. confirmed detection 后才更新 monitor 的 count。
5. 对外通过 monitor_id 获取检测窗口结果。
"""

import math
import time
import uuid
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

try:
    from src.game_state_service import state
except Exception:
    # 如果你的 game_state_service 路径不同，改这里。
    from game_state_service import state

try:
    from src.utils.logging_util import get_logger
    logger = get_logger(__name__)
except Exception:
    import logging
    logger = logging.getLogger(__name__)


Point = Tuple[float, float]
BBox = Tuple[int, int, int, int]       # x, y, w, h
Region = Tuple[int, int, int, int]     # x1, y1, x2, y2


@dataclass
class RedDotDetection:
    """
    对外返回的单个 confirmed 红点。
    坐标全部以小地图左上角为原点。
    """
    track_id: str
    center_minimap: Point
    bbox_minimap: BBox
    core_bbox_minimap: BBox
    score: float
    hit_frames: int
    has_outer_ring: bool
    first_seen: float
    last_seen: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "track_id": self.track_id,
            "center_minimap": self.center_minimap,
            "bbox_minimap": self.bbox_minimap,
            "core_bbox_minimap": self.core_bbox_minimap,
            "score": self.score,
            "hit_frames": self.hit_frames,
            "has_outer_ring": self.has_outer_ring,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
        }


@dataclass
class _FrameCandidate:
    """
    单帧候选，不直接对外暴露。
    """
    center: Point
    bbox: BBox
    core_bbox: BBox
    score: float
    has_outer_ring: bool


@dataclass
class _Track:
    """
    monitor 内部的跨帧 track。
    """
    track_id: str
    center: Point
    bbox: BBox
    core_bbox: BBox
    max_score: float
    hit_frames: int
    has_outer_ring: bool
    first_seen: float
    last_seen: float
    confirmed: bool = False
    last_matched_frame_id: int = -1

    def update(self, candidate: _FrameCandidate, now: float, frame_id: int) -> None:
        # 避免同一帧被重复更新。
        if self.last_matched_frame_id == frame_id:
            return

        old_x, old_y = self.center
        new_x, new_y = candidate.center

        # 轻微平滑中心点，减少闪动。
        self.center = (old_x * 0.6 + new_x * 0.4, old_y * 0.6 + new_y * 0.4)

        self.bbox = candidate.bbox
        self.core_bbox = candidate.core_bbox
        self.max_score = max(self.max_score, candidate.score)
        self.hit_frames += 1
        self.has_outer_ring = self.has_outer_ring or candidate.has_outer_ring
        self.last_seen = now
        self.last_matched_frame_id = frame_id

    def to_detection(self) -> RedDotDetection:
        return RedDotDetection(
            track_id=self.track_id,
            center_minimap=self.center,
            bbox_minimap=self.bbox,
            core_bbox_minimap=self.core_bbox,
            score=self.max_score,
            hit_frames=self.hit_frames,
            has_outer_ring=self.has_outer_ring,
            first_seen=self.first_seen,
            last_seen=self.last_seen,
        )


@dataclass
class _MonitorState:
    monitor_id: str
    started_at: float
    ends_at: float
    region: Optional[Region]
    region_mode: str
    min_confirmed_frames: int
    min_score: float
    high_score: float
    tracks: Dict[str, _Track] = field(default_factory=dict)
    active: bool = True
    expired: bool = False
    valid: bool = False
    reason: Optional[str] = "not_updated_yet"
    updated_at: Optional[float] = None
    frame_updates: int = 0


class RedDotFrameAnalyzer:
    """
    单帧小地图红点分析器。

    输入：小地图 BGR 图像。
    输出：当前帧红点候选列表。
    """

    def __init__(self) -> None:
        # 候选尺寸范围，基于 1920x1080 下的小地图像素。
        # 红点0.png 的本体在膨胀后仍会大于 5x5，所以这里可以安全收紧。
        self.min_candidate_w = 5
        self.min_candidate_h = 5
        self.max_candidate_w = 28
        self.max_candidate_h = 28

        # 连通块过滤。
        self.min_component_area = 3
        self.max_component_area = 220

        # 聚类时允许的红色块间隙。
        # 原本 10 太宽，容易把单位/选择框附近的红色碎片合并。
        self.cluster_gap = 5
        self.component_center_merge_distance = 9.0

        self.max_cluster_w = 28
        self.max_cluster_h = 28

    def analyze(self, minimap_bgr: np.ndarray) -> List[_FrameCandidate]:
        if minimap_bgr is None or minimap_bgr.size == 0:
            return []

        red_mask = self._build_red_mask(minimap_bgr)
        components = self._find_red_components(red_mask)

        if not components:
            return []

        candidates: List[_FrameCandidate] = []

        # 1. 先从单个红色连通块里找“中央菱形 core”
        # 这一步不依赖外圈，也不依赖 cluster 是否成功。
        core_candidates = self._find_core_candidates_from_components(components, red_mask)
        candidates.extend(core_candidates)

        # 2. 再做 cluster，用于识别中央点 + 外圈的完整红点。
        clusters = self._cluster_components(components)

        for cluster in clusters:
            candidate = self._cluster_to_candidate(cluster, red_mask)
            if candidate is not None:
                candidates.append(candidate)

        # 3. 去重，避免同一个红点既被 core 检出，又被 cluster 检出。
        return self._dedupe_candidates(candidates)

    def _build_red_mask(self, bgr: np.ndarray) -> np.ndarray:
        """
        生成红色二值 mask。
        返回 uint8 mask，红色为 255。

        这里故意偏向检测“纯红 ping 标记”，避免把小地图上的红紫色单位、
        棕红色头像/选择框像素误认为红点。
        """
        b = bgr[:, :, 0].astype(np.int16)
        g = bgr[:, :, 1].astype(np.int16)
        r = bgr[:, :, 2].astype(np.int16)

        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        hue = hsv[:, :, 0].astype(np.int16)
        sat = hsv[:, :, 1].astype(np.int16)
        val = hsv[:, :, 2].astype(np.int16)

        # SC2 小地图 ping 红点基本是非常纯的红色：
        # hue 接近 0/180，饱和度高，G/B 很低。
        red_hue = (hue <= 8) | (hue >= 172)

        pure_red_hsv = (
            red_hue &
            (sat >= 155) &
            (val >= 65)
        )

        red_dominance = (
            (r >= 65) &
            ((r - g) >= 45) &
            ((r - b) >= 45) &
            (g <= 85) &
            (b <= 85)
        )

        # 对非常亮的纯红做一点兜底。
        bright_pure_red = (
            red_hue &
            (r >= 150) &
            ((r - g) >= 80) &
            ((r - b) >= 80) &
            (g <= 90) &
            (b <= 90)
        )

        mask = ((pure_red_hsv & red_dominance) | bright_pure_red).astype(np.uint8) * 255

        # 轻微连接被背景侵蚀的红色边缘。
        # 保留 1 次膨胀，但前面的 mask 已经收紧，误合并会少很多。
        kernel = np.array(
            [[0, 1, 0],
            [1, 1, 1],
            [0, 1, 0]],
            dtype=np.uint8
        )

        mask = cv2.dilate(mask, kernel, iterations=1)

        return mask
    def _find_red_components(self, mask: np.ndarray) -> List[Dict[str, Any]]:
        """
        找红色连通块。
        """
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)

        components: List[Dict[str, Any]] = []

        for label_id in range(1, num_labels):
            x, y, w, h, area = stats[label_id]

            if area < self.min_component_area:
                continue
            if area > self.max_component_area:
                continue
            if w > self.max_candidate_w or h > self.max_candidate_h:
                continue

            cx, cy = centroids[label_id]

            components.append({
                "label_id": label_id,
                "bbox": (int(x), int(y), int(w), int(h)),
                "area": int(area),
                "center": (float(cx), float(cy)),
            })

        return components

    def _cluster_components(self, components: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """
        将中央红点和外围菱形边框的多个红色连通块聚成一个候选。
        """
        n = len(components)
        parent = list(range(n))

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(a: int, b: int) -> None:
            ra = find(a)
            rb = find(b)
            if ra != rb:
                parent[rb] = ra

        for i in range(n):
            for j in range(i + 1, n):
                if self._should_merge_components(components[i], components[j]):
                    union(i, j)

        groups: Dict[int, List[Dict[str, Any]]] = {}
        for i, comp in enumerate(components):
            root = find(i)
            groups.setdefault(root, []).append(comp)

        return list(groups.values())

    def _should_merge_components(self, a: Dict[str, Any], b: Dict[str, Any]) -> bool:
        ax, ay, aw, ah = a["bbox"]
        bx, by, bw, bh = b["bbox"]

        union_x1 = min(ax, bx)
        union_y1 = min(ay, by)
        union_x2 = max(ax + aw, bx + bw)
        union_y2 = max(ay + ah, by + bh)

        union_w = union_x2 - union_x1
        union_h = union_y2 - union_y1

        if union_w > self.max_cluster_w or union_h > self.max_cluster_h:
            return False

        gap = self.cluster_gap
        a_exp = (ax - gap, ay - gap, aw + gap * 2, ah + gap * 2)
        b_exp = (bx, by, bw, bh)

        if self._bbox_overlap(a_exp, b_exp):
            return True

        acx, acy = a["center"]
        bcx, bcy = b["center"]
        dist = math.hypot(acx - bcx, acy - bcy)

        return dist <= self.component_center_merge_distance
    
    @staticmethod
    def _bbox_overlap(a: BBox, b: BBox) -> bool:
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        return not (
            ax + aw < bx or
            bx + bw < ax or
            ay + ah < by or
            by + bh < ay
        )
        
    def _cluster_to_candidate(
        self,
        cluster: List[Dict[str, Any]],
        red_mask: np.ndarray
    ) -> Optional[_FrameCandidate]:
        x1 = min(c["bbox"][0] for c in cluster)
        y1 = min(c["bbox"][1] for c in cluster)
        x2 = max(c["bbox"][0] + c["bbox"][2] for c in cluster)
        y2 = max(c["bbox"][1] + c["bbox"][3] for c in cluster)

        w = x2 - x1
        h = y2 - y1

        if w < self.min_candidate_w or h < self.min_candidate_h:
            return None
        if w > self.max_candidate_w or h > self.max_candidate_h:
            return self._try_make_core_candidate_from_cluster(cluster, red_mask)

        aspect = w / max(1, h)

        # 红点标记整体应接近正方形。
        # 原本 0.55 太宽，会放过 9x17 这类竖向碎片组合。
        if aspect < 0.65 or aspect > 1.55:
              return self._try_make_core_candidate_from_cluster(cluster, red_mask)

        crop = red_mask[y1:y2, x1:x2]
        if crop.size == 0:
            return None

        red_count = int(np.count_nonzero(crop))

        # 过滤非常小的红色噪声。
        # 红点0.png 经过 mask + dilation 后通常明显大于这个值。
        if red_count < 18:
            return None

        score, has_outer_ring = self._score_diamond_candidate(crop)

        component_count, red_count, largest_area, fill_ratio = self._component_fragment_stats(crop)

        if self._is_fragmented_false_candidate(
            component_count=component_count,
            red_count=red_count,
            largest_area=largest_area,
            fill_ratio=fill_ratio,
            has_outer_ring=has_outer_ring,
        ):
            core_candidate = self._try_make_core_candidate_from_cluster(cluster, red_mask)

            if core_candidate is not None:
                return core_candidate

            return None

        # 没有外圈时，更要求它像一个有效中央红点，而不是单个小红色碎片。
        if not has_outer_ring:
            if w < 7 or h < 7 or red_count < 35:
                return None

        # 有外圈但分数偏低时，大概率是零散红色碎片拼出来的假 ring。
        if has_outer_ring and score < 0.68:
            return None

        # 无外圈的中心红点也不要太宽松。
        if not has_outer_ring and score < 0.72:
            return None

        core_bbox = self._estimate_core_bbox(cluster, x1, y1, w, h)

        # 用核心 bbox 中心作为红点中心，更少受外圈扩张影响。
        cx = core_bbox[0] + core_bbox[2] / 2.0
        cy = core_bbox[1] + core_bbox[3] / 2.0

        return _FrameCandidate(
            center=(cx, cy),
            bbox=(x1, y1, w, h),
            core_bbox=core_bbox,
            score=score,
            has_outer_ring=has_outer_ring,
        )

    def _score_diamond_candidate(self, crop_mask: np.ndarray) -> Tuple[float, bool]:
        """
        计算候选是否像红色菱形标记。

        重点区分：
        - 旋转 45 度的菱形红点
        - x/y 轴平行的普通红色方块/长方块
        """
        h, w = crop_mask.shape[:2]
        red = crop_mask > 0
        red_count = int(np.count_nonzero(red))

        if red_count <= 0:
            return 0.0, False

        aspect = w / max(1, h)
        aspect_score = max(0.0, 1.0 - abs(aspect - 1.0) / 0.65)

        corner_ratio = self._corner_red_ratio(red)
        corner_score = max(0.0, 1.0 - corner_ratio * 5.5)

        diamond_support_score = self._diamond_support_score(red)

        center_score = self._center_presence_score(red)

        has_outer_ring = self._has_outer_ring(red)

        size_score = 1.0
        if w <= 4 and h <= 4:
            size_score = 0.65
        elif w >= 28 or h >= 28:
            size_score = 0.75

        outer_bonus = 0.12 if has_outer_ring else 0.0

        score = (
            0.22 * aspect_score +
            0.28 * corner_score +
            0.25 * diamond_support_score +
            0.13 * center_score +
            0.12 * size_score +
            outer_bonus
        )

        return min(1.0, float(score)), has_outer_ring

    @staticmethod
    def _corner_red_ratio(red: np.ndarray) -> float:
        """
        bbox 四角红色占比。

        菱形 bbox 四角通常红色较少；
        普通轴向方块/矩形四角更容易有红色。
        """
        h, w = red.shape[:2]
        cw = max(1, int(round(w * 0.28)))
        ch = max(1, int(round(h * 0.28)))

        corners = [
            red[0:ch, 0:cw],
            red[0:ch, w - cw:w],
            red[h - ch:h, 0:cw],
            red[h - ch:h, w - cw:w],
        ]

        corner_red = sum(int(np.count_nonzero(c)) for c in corners)
        total_red = int(np.count_nonzero(red))

        if total_red <= 0:
            return 1.0

        return corner_red / total_red

    @staticmethod
    def _center_presence_score(red: np.ndarray) -> float:
        h, w = red.shape[:2]
        cx1 = max(0, int(w * 0.35))
        cx2 = min(w, int(w * 0.65) + 1)
        cy1 = max(0, int(h * 0.35))
        cy2 = min(h, int(h * 0.65) + 1)

        center_area = red[cy1:cy2, cx1:cx2]
        if center_area.size == 0:
            return 0.0

        return min(1.0, np.count_nonzero(center_area) / max(1, center_area.size * 0.35))

    @staticmethod
    def _diamond_support_score(red: np.ndarray) -> float:
        """
        粗略判断红色像素是否落在菱形结构附近。
        """
        h, w = red.shape[:2]
        ys, xs = np.where(red)

        if len(xs) == 0:
            return 0.0

        cx = (w - 1) / 2.0
        cy = (h - 1) / 2.0

        dx = np.abs(xs - cx)
        dy = np.abs(ys - cy)

        max_dx = max(1.0, w / 2.0)
        max_dy = max(1.0, h / 2.0)

        nx = dx / max_dx
        ny = dy / max_dy

        # 菱形内部大致满足 nx + ny <= 1。
        diamond_distance = nx + ny

        inside_or_near = diamond_distance <= 1.25
        support = float(np.count_nonzero(inside_or_near)) / max(1, len(xs))

        # 轴向正方形常有角落像素，corner_score 已经惩罚；
        # 这里主要保证红色分布不要离菱形结构太远。
        return support

    @staticmethod
    def _has_outer_ring(red: np.ndarray) -> bool:
        """
        判断是否存在外围菱形边框特征。

        收紧版：
        不只要求上下左右有红色，还要求红色分布不能太碎。
        """
        h, w = red.shape[:2]

        if w < 12 or h < 12:
            return False

        top_band = red[0:max(1, h // 4), :]
        bottom_band = red[h - max(1, h // 4):h, :]
        left_band = red[:, 0:max(1, w // 4)]
        right_band = red[:, w - max(1, w // 4):w]

        center_y1 = int(h * 0.35)
        center_y2 = int(h * 0.65) + 1
        center_x1 = int(w * 0.35)
        center_x2 = int(w * 0.65) + 1
        center = red[center_y1:center_y2, center_x1:center_x2]

        has_cardinal = (
            np.count_nonzero(top_band) >= 2 and
            np.count_nonzero(bottom_band) >= 2 and
            np.count_nonzero(left_band) >= 2 and
            np.count_nonzero(right_band) >= 2
        )

        has_center = np.count_nonzero(center) >= 1

        if not (has_cardinal and has_center):
            return False

        # 额外要求：整体不能太碎。
        binary = red.astype(np.uint8) * 255
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
        component_count = max(0, num_labels - 1)

        red_count = int(np.count_nonzero(red))
        largest_area = 0
        for label_id in range(1, num_labels):
            largest_area = max(largest_area, int(stats[label_id, cv2.CC_STAT_AREA]))

        largest_ratio = largest_area / max(1, red_count)

        # 很小的单连通块通常只是中央菱形本体，不要当作 outer ring。
        if component_count <= 1 and min(w, h) < 16:
            return False

        # 如果碎成 3 块以上，而且没有一个主块占主导，就不要认为它是 ring。
        if component_count >= 3 and largest_ratio < 0.72:
            return False

        return True

    @staticmethod
    def _estimate_core_bbox(
        cluster: List[Dict[str, Any]],
        group_x: int,
        group_y: int,
        group_w: int,
        group_h: int
    ) -> BBox:
        """
        估计中央红点本体 bbox。

        外圈变化会影响 full bbox，所以区域判断更适合用 core bbox。
        """
        gcx = group_x + group_w / 2.0
        gcy = group_y + group_h / 2.0

        best = None
        best_score = float("inf")

        for comp in cluster:
            x, y, w, h = comp["bbox"]
            cx, cy = comp["center"]

            dist = math.hypot(cx - gcx, cy - gcy)

            # 中央点通常更靠近组中心。
            # 面积太大的外圈片段稍微惩罚。
            area_penalty = comp["area"] * 0.02
            score = dist + area_penalty

            if score < best_score:
                best_score = score
                best = comp

        if best is None:
            return (group_x, group_y, group_w, group_h)

        return best["bbox"]
      
    @staticmethod
    def _component_fragment_stats(crop_mask: np.ndarray) -> Tuple[int, int, int, float]:
        """
        返回：
        - component_count: crop 内红色连通块数量
        - red_count: 红色像素数量
        - largest_area: 最大连通块面积
        - fill_ratio: 红色像素 / bbox 面积
        """
        binary = (crop_mask > 0).astype(np.uint8) * 255
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)

        component_count = max(0, num_labels - 1)
        red_count = int(np.count_nonzero(binary))
        fill_ratio = red_count / max(1, crop_mask.shape[0] * crop_mask.shape[1])

        largest_area = 0
        for label_id in range(1, num_labels):
            largest_area = max(largest_area, int(stats[label_id, cv2.CC_STAT_AREA]))

        return component_count, red_count, largest_area, fill_ratio


    @staticmethod
    def _is_fragmented_false_candidate(
        component_count: int,
        red_count: int,
        largest_area: int,
        fill_ratio: float,
        has_outer_ring: bool,
    ) -> bool:
        """
        过滤多个零散红色碎片被误聚类成红点的情况。
        """
        if red_count <= 0:
            return True

        largest_ratio = largest_area / max(1, red_count)

        # 典型 C4：
        # - 多个连通块
        # - bbox 内红色填充率低
        # - 最大块占比不够高
        if component_count >= 3 and fill_ratio < 0.36 and largest_ratio < 0.72:
            return True

        # 有外圈但非常稀碎，也很可疑。
        if has_outer_ring and component_count >= 3 and fill_ratio < 0.30:
            return True

        return False
      
    def _try_make_core_candidate_from_cluster(
        self,
        cluster: List[Dict[str, Any]],
        red_mask: np.ndarray
    ) -> Optional[_FrameCandidate]:
        components = sorted(cluster, key=lambda c: c["area"], reverse=True)

        for comp in components:
            candidate = self._component_to_core_candidate(comp, red_mask)
            if candidate is not None:
                return candidate

        return None
      
    def _find_core_candidates_from_components(
        self,
        components: List[Dict[str, Any]],
        red_mask: np.ndarray
    ) -> List[_FrameCandidate]:
        """
        直接从单个红色连通块中识别中央红色菱形。

        用途：
        - 保留只有中央菱形、外圈不完整、外圈被碎片干扰的真实红点。
        - 避免必须依赖 cluster 通过。
        """
        candidates: List[_FrameCandidate] = []

        for comp in components:
            candidate = self._component_to_core_candidate(comp, red_mask)
            if candidate is not None:
                candidates.append(candidate)

        return candidates

      
    def _component_to_core_candidate(
        self,
        comp: Dict[str, Any],
        red_mask: np.ndarray
    ) -> Optional[_FrameCandidate]:
        x, y, w, h = comp["bbox"]
        area = int(comp["area"])

        def reject(reason: str):
            logger.debug(
                "core reject: reason=%s bbox=%s area=%s",
                reason,
                (x, y, w, h),
                area,
            )
            return None
          
        if w < 7 or h < 7:
            return reject("too_small")

        if w > 24 or h > 24:
            return reject("too_large")

        aspect = w / max(1, h)
        if aspect < 0.70 or aspect > 1.45:
            return reject(f"bad_aspect_{aspect:.2f}")

        if area < 40:
            return reject("area_lt_40")

        crop = red_mask[y:y + h, x:x + w]
        if crop.size == 0:
            return reject("empty_crop")

        red_count = int(np.count_nonzero(crop))
        fill_ratio = red_count / max(1, w * h)

        if fill_ratio < 0.30:
            return reject(f"fill_ratio_low_{fill_ratio:.2f}")

        score, _ = self._score_diamond_candidate(crop)

        if score < 0.68:
            return reject(f"score_low_{score:.3f}")

        cx = x + w / 2.0
        cy = y + h / 2.0

        return _FrameCandidate(
            center=(cx, cy),
            bbox=(x, y, w, h),
            core_bbox=(x, y, w, h),
            score=score,
            has_outer_ring=False,
        )
        
    def _dedupe_candidates(
        self,
        candidates: List[_FrameCandidate],
        merge_distance: float = 16.0
    ) -> List[_FrameCandidate]:
        """
        去除同一个红点的重复候选。

        规则：
        - bbox 接触/轻微重叠，认为是同一红点。
        - 中心距离很近，也认为是同一红点。
        - 优先保留有 ring、bbox 更大、score 更高的候选。
        """
        if not candidates:
            return []

        def bbox_area(c: _FrameCandidate) -> int:
            return c.bbox[2] * c.bbox[3]

        def expand_bbox(bbox: BBox, gap: int) -> BBox:
            x, y, w, h = bbox
            return (x - gap, y - gap, w + gap * 2, h + gap * 2)

        def same_dot(a: _FrameCandidate, b: _FrameCandidate) -> bool:
            ax, ay = a.center
            bx, by = b.center
            dist = math.hypot(ax - bx, ay - by)

            # bbox 轻微接触/重叠，基本就是同一个 ping 的外圈/核心。
            if self._bbox_overlap(expand_bbox(a.bbox, 3), b.bbox):
                return True

            # 中心近但 bbox 没接触时，仍保守一点，避免误合并两个真实红点。
            if dist <= merge_distance:
                aw, ah = a.bbox[2], a.bbox[3]
                bw, bh = b.bbox[2], b.bbox[3]

                # 两个候选至少有一个不是很小，才按同一点合并。
                if max(aw, ah, bw, bh) >= 12:
                    return True

            return False

        sorted_candidates = sorted(
            candidates,
            key=lambda c: (
                1 if c.has_outer_ring else 0,
                bbox_area(c),
                c.score,
            ),
            reverse=True
        )

        kept: List[_FrameCandidate] = []

        for cand in sorted_candidates:
            duplicated = False

            for old in kept:
                if same_dot(cand, old):
                    duplicated = True
                    break

            if not duplicated:
                kept.append(cand)

        return kept
class MinimapRedDotDetector:
    """
    小地图红点检测器。

    推荐用法：

        red_dot_detector = MinimapRedDotDetector()
        red_dot_detector.start_worker()

        monitor_id = red_dot_detector.start_monitor(
            duration_s=3.0,
            region=(50, 50, 160, 160),
            region_mode="core_bbox_in",
        )

        result = red_dot_detector.get_result(monitor_id)

    注意：
    - start_monitor 开启检测窗口。
    - get_result 只读取缓存，不做图像检测。
    - count 只统计 confirmed detection。
    """

    MINIMAP_BASE_X = 27
    MINIMAP_BASE_Y = 807
    MINIMAP_BASE_W = 264
    MINIMAP_BASE_H = 259
    BASE_WIDTH = 1920.0

    REGION_CENTER_IN = "center_in"
    REGION_CORE_BBOX_IN = "core_bbox_in"
    REGION_FULL_BBOX_IN = "full_bbox_in"

    def __init__(
        self,
        sample_interval_s: float = 0.10,
        max_screenshot_age_s: float = 0.35,
        track_match_distance_px: float = 13.0,
        debug: bool = False,
    ) -> None:
        self.sample_interval_s = sample_interval_s
        self.max_screenshot_age_s = max_screenshot_age_s
        self.track_match_distance_px = track_match_distance_px
        self.debug = debug

        self._analyzer = RedDotFrameAnalyzer()

        self._lock = threading.RLock()
        self._monitors: Dict[str, _MonitorState] = {}

        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None

        self._frame_id = 0
        self._last_processed_screenshot_ts = 0.0

    def start_worker(self) -> None:
        """
        启动后台检测线程。
        多次调用安全。
        """
        with self._lock:
            if self._worker_thread is not None and self._worker_thread.is_alive():
                return

            self._stop_event.clear()
            self._worker_thread = threading.Thread(
                target=self._worker_loop,
                name="MinimapRedDotDetector",
                daemon=True,
            )
            self._worker_thread.start()

        logger.info("MinimapRedDotDetector worker started")

    def stop_worker(self) -> None:
        """
        停止后台检测线程。
        """
        self._stop_event.set()

        thread = self._worker_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)

        logger.info("MinimapRedDotDetector worker stopped")

    def start_monitor(
        self,
        duration_s: float,
        region: Optional[Region] = None,
        region_mode: str = REGION_CORE_BBOX_IN,
        min_confirmed_frames: int = 2,
        min_score: float = 0.58,
        high_score: float = 0.82,
    ) -> str:
        """
        开启一个检测窗口。

        Args:
            duration_s:
                现实时间秒数。
            region:
                小地图局部坐标区域，格式为 (x1, y1, x2, y2)。
                None 表示整个小地图。
            region_mode:
                center_in:
                    红点中心在区域内就算。
                core_bbox_in:
                    中央红点本体 bbox 完全在区域内才算。
                full_bbox_in:
                    当前外圈 bbox 也完全在区域内才算。
            min_confirmed_frames:
                同一 track 至少命中多少帧才 confirmed。
            min_score:
                普通候选最低确认分数。
            high_score:
                高分候选阈值。当前版本仍会遵守 min_confirmed_frames，
                先保守，避免单帧误判。

        Returns:
            monitor_id
        """
        if duration_s <= 0:
            raise ValueError("duration_s must be > 0")

        if region_mode not in {
            self.REGION_CENTER_IN,
            self.REGION_CORE_BBOX_IN,
            self.REGION_FULL_BBOX_IN,
        }:
            raise ValueError(f"invalid region_mode: {region_mode}")

        if region is not None:
            self._validate_region(region)

        now = time.perf_counter()
        monitor_id = str(uuid.uuid4())

        monitor = _MonitorState(
            monitor_id=monitor_id,
            started_at=now,
            ends_at=now + duration_s,
            region=region,
            region_mode=region_mode,
            min_confirmed_frames=max(1, int(min_confirmed_frames)),
            min_score=float(min_score),
            high_score=float(high_score),
        )

        with self._lock:
            self._monitors[monitor_id] = monitor

        self.start_worker()

        logger.debug(
            "red dot monitor started: id=%s duration=%.2f region=%s mode=%s",
            monitor_id, duration_s, region, region_mode
        )

        return monitor_id

    def get_result(self, monitor_id: str) -> Dict[str, Any]:
        """
        获取检测窗口当前快照。

        注意：这个函数不做图像检测，只读缓存。
        """
        with self._lock:
            monitor = self._monitors.get(monitor_id)

            if monitor is None:
                return {
                    "monitor_id": monitor_id,
                    "active": False,
                    "expired": False,
                    "valid": False,
                    "count": 0,
                    "current_count": 0,
                    "detections": [],
                    "current_detections": [],
                    "updated_at": None,
                    "reason": "monitor_not_found",
                }

            self._refresh_monitor_expired_state(monitor, time.perf_counter())
            return self._monitor_to_result_dict(monitor)

    def stop_monitor(self, monitor_id: str) -> bool:
        """
        删除一个检测窗口。
        """
        with self._lock:
            existed = monitor_id in self._monitors
            if existed:
                del self._monitors[monitor_id]
            return existed

    def cleanup_expired(self, older_than_s: float = 30.0) -> int:
        """
        清理过期一段时间后的 monitor。
        """
        now = time.perf_counter()
        removed = 0

        with self._lock:
            remove_ids = []

            for monitor_id, monitor in self._monitors.items():
                self._refresh_monitor_expired_state(monitor, now)
                if monitor.expired and now - monitor.ends_at >= older_than_s:
                    remove_ids.append(monitor_id)

            for monitor_id in remove_ids:
                del self._monitors[monitor_id]
                removed += 1

        return removed

    def has_active_monitors(self) -> bool:
        with self._lock:
            now = time.perf_counter()
            for monitor in self._monitors.values():
                self._refresh_monitor_expired_state(monitor, now)
                if monitor.active:
                    return True
        return False

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._process_once()
            except Exception:
                logger.exception("MinimapRedDotDetector worker error")

            time.sleep(self.sample_interval_s)

    def _process_once(self) -> None:
        now = time.perf_counter()

        with self._lock:
            if not self._monitors:
                return

            for monitor in self._monitors.values():
                self._refresh_monitor_expired_state(monitor, now)

            if not any(m.active for m in self._monitors.values()):
                return

        minimap_bgr, screenshot_ts, reason = self._copy_minimap_roi()

        if minimap_bgr is None:
            self._mark_active_monitors_invalid(reason)
            return

        # 同一张截图不重复处理。
        if screenshot_ts <= self._last_processed_screenshot_ts:
            return

        self._last_processed_screenshot_ts = screenshot_ts
        self._frame_id += 1

        candidates = self._analyzer.analyze(minimap_bgr)

        if self.debug:
            logger.debug("red dot frame candidates=%d", len(candidates))

        self._update_monitors_with_candidates(candidates, now, self._frame_id)

    def _copy_minimap_roi(self) -> Tuple[Optional[np.ndarray], float, Optional[str]]:
        """
        从全局截图复制小地图 ROI。
        """
        with state.screenshot_lock:
            screenshot = state.latest_screenshot
            screenshot_ts = float(state.screenshot_timestamp or 0.0)

            if screenshot is None:
                return None, screenshot_ts, "no_screenshot"

            if screenshot_ts <= 0:
                return None, screenshot_ts, "invalid_screenshot_timestamp"

            if time.perf_counter() - screenshot_ts > self.max_screenshot_age_s:
                return None, screenshot_ts, "stale_screenshot"

            h, w = screenshot.shape[:2]
            scale = self._get_effective_scale(w)

            x = int(round(self.MINIMAP_BASE_X * scale))
            y = int(round(self.MINIMAP_BASE_Y * scale))
            roi_w = int(round(self.MINIMAP_BASE_W * scale))
            roi_h = int(round(self.MINIMAP_BASE_H * scale))

            if x < 0 or y < 0 or x + roi_w > w or y + roi_h > h:
                return None, screenshot_ts, "minimap_roi_out_of_range"

            minimap = screenshot[y:y + roi_h, x:x + roi_w].copy()

        # 如果将来未强制缩放到 1920 宽，这里把小地图 ROI 统一缩回基准大小，
        # 让后续检测阈值继续按 264x259 工作。
        if minimap.shape[1] != self.MINIMAP_BASE_W or minimap.shape[0] != self.MINIMAP_BASE_H:
            minimap = cv2.resize(
                minimap,
                (self.MINIMAP_BASE_W, self.MINIMAP_BASE_H),
                interpolation=cv2.INTER_AREA,
            )

        return minimap, screenshot_ts, None

    def _get_effective_scale(self, screenshot_width: int) -> float:
        """
        当前 game_state_service 会把截图缩放到 1920 宽，并把 scale_factor 设为 1.0。
        如果以后取消强制缩放，这里仍尽量兼容。
        """
        if abs(screenshot_width - int(self.BASE_WIDTH)) <= 2:
            return 1.0

        scale_from_width = screenshot_width / self.BASE_WIDTH

        scale_from_state = getattr(state, "scale_factor", None)
        if isinstance(scale_from_state, (int, float)) and scale_from_state > 0:
            # 如果 state.scale_factor 明显不是 1，优先用它。
            if abs(float(scale_from_state) - 1.0) > 0.01:
                return float(scale_from_state)

        return float(scale_from_width)

    def _mark_active_monitors_invalid(self, reason: Optional[str]) -> None:
        now = time.perf_counter()

        with self._lock:
            for monitor in self._monitors.values():
                self._refresh_monitor_expired_state(monitor, now)
                if monitor.active:
                    monitor.valid = False
                    monitor.reason = reason or "unknown"
                    monitor.updated_at = now

    def _update_monitors_with_candidates(
        self,
        candidates: List[_FrameCandidate],
        now: float,
        frame_id: int
    ) -> None:
        with self._lock:
            for monitor in self._monitors.values():
                self._refresh_monitor_expired_state(monitor, now)

                if not monitor.active:
                    continue

                region_candidates = [
                    c for c in candidates
                    if self._candidate_in_monitor_region(c, monitor)
                ]

                self._update_monitor_tracks(monitor, region_candidates, now, frame_id)

                monitor.valid = True
                monitor.reason = None
                monitor.updated_at = now
                monitor.frame_updates += 1

    def _update_monitor_tracks(
        self,
        monitor: _MonitorState,
        candidates: List[_FrameCandidate],
        now: float,
        frame_id: int
    ) -> None:
        unmatched_track_ids = set(monitor.tracks.keys())

        # 高分优先匹配，避免弱候选抢 track。
        candidates = sorted(candidates, key=lambda c: c.score, reverse=True)

        for candidate in candidates:
            track = self._find_best_track(monitor, candidate, unmatched_track_ids)

            if track is None:
                track_id = str(uuid.uuid4())
                track = _Track(
                    track_id=track_id,
                    center=candidate.center,
                    bbox=candidate.bbox,
                    core_bbox=candidate.core_bbox,
                    max_score=candidate.score,
                    hit_frames=1,
                    has_outer_ring=candidate.has_outer_ring,
                    first_seen=now,
                    last_seen=now,
                    confirmed=False,
                    last_matched_frame_id=frame_id,
                )
                monitor.tracks[track_id] = track
            else:
                track.update(candidate, now, frame_id)
                unmatched_track_ids.discard(track.track_id)

            self._maybe_confirm_track(monitor, track)

    def _find_best_track(
        self,
        monitor: _MonitorState,
        candidate: _FrameCandidate,
        allowed_track_ids: set
    ) -> Optional[_Track]:
        best_track = None
        best_dist = float("inf")

        cx, cy = candidate.center

        for track_id in allowed_track_ids:
            track = monitor.tracks.get(track_id)
            if track is None:
                continue

            tx, ty = track.center
            dist = math.hypot(cx - tx, cy - ty)

            # confirmed track 保留到窗口结束。
            # 这样同一个红点外圈消失后再次出现，不会重复计数。
            max_dist = self.track_match_distance_px
            if track.confirmed:
                max_dist = max(max_dist, 16.0)

            if dist <= max_dist and dist < best_dist:
                best_dist = dist
                best_track = track

        return best_track

    @staticmethod
    def _maybe_confirm_track(monitor: _MonitorState, track: _Track) -> None:
        if track.confirmed:
            return

        if track.hit_frames < monitor.min_confirmed_frames:
            return

        # 严格模式：
        # core-only 只用于维持 track，不直接确认。
        # 必须至少观察到一次 outer ring，才认为这是红点 ping。
        if not track.has_outer_ring:
            return

        if track.max_score >= monitor.min_score:
            track.confirmed = True
            return

        if track.max_score >= monitor.high_score:
            track.confirmed = True

    def _candidate_in_monitor_region(
        self,
        candidate: _FrameCandidate,
        monitor: _MonitorState
    ) -> bool:
        region = monitor.region
        if region is None:
            return True

        if monitor.region_mode == self.REGION_CENTER_IN:
            cx, cy = candidate.center
            return self._point_in_region(cx, cy, region)

        if monitor.region_mode == self.REGION_CORE_BBOX_IN:
            return self._bbox_inside_region(candidate.core_bbox, region)

        if monitor.region_mode == self.REGION_FULL_BBOX_IN:
            return self._bbox_inside_region(candidate.bbox, region)

        return False

    @staticmethod
    def _point_in_region(x: float, y: float, region: Region) -> bool:
        x1, y1, x2, y2 = region
        return x1 <= x <= x2 and y1 <= y <= y2

    @staticmethod
    def _bbox_inside_region(bbox: BBox, region: Region) -> bool:
        bx, by, bw, bh = bbox
        x1, y1, x2, y2 = region
        return bx >= x1 and by >= y1 and bx + bw <= x2 and by + bh <= y2

    @staticmethod
    def _validate_region(region: Region) -> None:
        x1, y1, x2, y2 = region

        if x2 <= x1 or y2 <= y1:
            raise ValueError(f"invalid region: {region}")

        if x1 < 0 or y1 < 0 or x2 > 264 or y2 > 259:
            raise ValueError(
                f"region must be minimap-local coordinates within 264x259, got: {region}"
            )

    @staticmethod
    def _refresh_monitor_expired_state(monitor: _MonitorState, now: float) -> None:
        if monitor.active and now >= monitor.ends_at:
            monitor.active = False
            monitor.expired = True

    @staticmethod
    def _monitor_to_result_dict(monitor: _MonitorState) -> Dict[str, Any]:
        confirmed_tracks = [
            t for t in monitor.tracks.values()
            if t.confirmed
        ]

        now = time.perf_counter()

        # 当前仍然可见的 confirmed tracks。
        # count 是窗口内已经确认过的总数；
        # current_count 是最近仍被看到的数量。
        current_tracks = [
            t for t in confirmed_tracks
            if now - t.last_seen <= 0.45
        ]

        detections = [
            t.to_detection().to_dict()
            for t in sorted(confirmed_tracks, key=lambda item: item.first_seen)
        ]

        current_detections = [
            t.to_detection().to_dict()
            for t in sorted(current_tracks, key=lambda item: item.first_seen)
        ]

        return {
            "monitor_id": monitor.monitor_id,
            "active": monitor.active,
            "expired": monitor.expired,
            "valid": monitor.valid,
            "count": len(confirmed_tracks),
            "current_count": len(current_tracks),
            "detections": detections,
            "current_detections": current_detections,
            "region": monitor.region,
            "region_mode": monitor.region_mode,
            "started_at": monitor.started_at,
            "ends_at": monitor.ends_at,
            "updated_at": monitor.updated_at,
            "frame_updates": monitor.frame_updates,
            "reason": monitor.reason,
        }


# 可选：全局单例，方便其他模块直接 import 使用。
red_dot_detector = MinimapRedDotDetector()