"""Offline detector for the enemy-composition tooltip panel.

This module intentionally implements only the first two offline phases of the
enemy-composition work:

* detect the single-frame tooltip panel from a normalized BGR screenshot; and
* derive a conservative crop around the first two text rows.

It does not read shared game state, perform OCR, match composition names, or
keep temporal state.  The detector is therefore safe to call independently on
successive frames from a future recognizer.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np


BBox = Tuple[int, int, int, int]

BASE_WIDTH = 1920.0

# The values below are expressed in the normalized 1920-wide coordinate
# system.  The detector scales coordinates if it is handed a different-sized
# image, but the intended runtime input is already normalized by
# game_state_service.
SEARCH_X_MIN = 1400
SEARCH_Y_MIN = 240
SEARCH_Y_MAX = 820

EDGE_LOW_THRESHOLD = 40
EDGE_HIGH_THRESHOLD = 120
HOUGH_THRESHOLD = 110
HOUGH_MIN_LINE_LENGTH = 300
HOUGH_MAX_LINE_GAP = 28

MIN_HORIZONTAL_LINE_SPAN = 300
MIN_PANEL_WIDTH = 360
MAX_PANEL_WIDTH = 450
MIN_PANEL_HEIGHT = 180
MAX_PANEL_HEIGHT = 300
MIN_LINE_OVERLAP_RATIO = 0.70
MIN_HORIZONTAL_SUPPORT = 0.45
MIN_VERTICAL_SUPPORT = 0.50
PANEL_SCORE_THRESHOLD = 0.58

# The panel's first two text rows are near its top in every supplied sample.
# This is deliberately a fixed top crop, not a fraction of the variable panel
# height.  The small padding prefers retaining a little background over
# clipping a Chinese or English title.
TITLE_LEFT_PADDING = 8
TITLE_RIGHT_PADDING = 8
TITLE_TOP_PADDING = 8
TITLE_CROP_HEIGHT = 46


DETECTOR_PARAMETERS: Dict[str, Any] = {
    "normalized_base_width": int(BASE_WIDTH),
    "search_roi": (SEARCH_X_MIN, SEARCH_Y_MIN, int(BASE_WIDTH) - SEARCH_X_MIN, SEARCH_Y_MAX - SEARCH_Y_MIN),
    "edge": {
        "low_threshold": EDGE_LOW_THRESHOLD,
        "high_threshold": EDGE_HIGH_THRESHOLD,
    },
    "hough": {
        "threshold": HOUGH_THRESHOLD,
        "min_line_length": HOUGH_MIN_LINE_LENGTH,
        "max_line_gap": HOUGH_MAX_LINE_GAP,
    },
    "panel_width": (MIN_PANEL_WIDTH, MAX_PANEL_WIDTH),
    "panel_height": (MIN_PANEL_HEIGHT, MAX_PANEL_HEIGHT),
    "min_horizontal_line_span": MIN_HORIZONTAL_LINE_SPAN,
    "min_line_overlap_ratio": MIN_LINE_OVERLAP_RATIO,
    "min_horizontal_support": MIN_HORIZONTAL_SUPPORT,
    "min_vertical_support": MIN_VERTICAL_SUPPORT,
    "panel_score_threshold": PANEL_SCORE_THRESHOLD,
    "title_crop": {
        "left_padding": TITLE_LEFT_PADDING,
        "right_padding": TITLE_RIGHT_PADDING,
        "top_padding": TITLE_TOP_PADDING,
        "height": TITLE_CROP_HEIGHT,
    },
}


@dataclass(frozen=True)
class EnemyCompositionPanelDetection:
    """Structured result from one detector call.

    Coordinates use the input image's coordinate system and follow the usual
    OpenCV ``(x, y, width, height)`` convention.  ``debug`` contains only
    scalar/tuple metadata suitable for offline report generation; callers do
    not need it for normal use.
    """

    found: bool
    bbox: Optional[BBox]
    score: float
    reason: str
    title_bbox: Optional[BBox] = None
    debug: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-friendly representation of the result."""

        return {
            "found": self.found,
            "bbox": self.bbox,
            "score": float(self.score),
            "reason": self.reason,
            "title_bbox": self.title_bbox,
            "debug": self.debug,
        }


def clip_bbox(bbox: Optional[Sequence[int]], image_shape: Sequence[int]) -> Optional[BBox]:
    """Clip an ``(x, y, w, h)`` box to an image shape.

    The helper is intentionally independent of the detector so it can be
    tested and reused by future crop code.  Invalid or empty boxes return
    ``None`` rather than raising.
    """

    if bbox is None or image_shape is None or len(image_shape) < 2:
        return None

    try:
        x, y, width, height = (int(value) for value in bbox)
        image_height = int(image_shape[0])
        image_width = int(image_shape[1])
    except (TypeError, ValueError):
        return None

    if image_width <= 0 or image_height <= 0 or width <= 0 or height <= 0:
        return None

    x1 = max(0, min(image_width, x))
    y1 = max(0, min(image_height, y))
    x2 = max(0, min(image_width, x + width))
    y2 = max(0, min(image_height, y + height))

    if x2 <= x1 or y2 <= y1:
        return None

    return (x1, y1, x2 - x1, y2 - y1)


def get_enemy_composition_title_bbox(
    panel_bbox: Optional[Sequence[int]],
    image_shape: Sequence[int],
) -> Optional[BBox]:
    """Derive the fixed-height top title crop from a detected panel.

    The crop includes the category row and composition-name row.  It is based
    on ``panel_bbox``'s top/left/right edges and a fixed normalized pixel
    height; it never uses a fraction of the variable panel height.
    """

    panel = clip_bbox(panel_bbox, image_shape)
    if panel is None or len(image_shape) < 2:
        return None

    image_height = int(image_shape[0])
    image_width = int(image_shape[1])
    scale = image_width / BASE_WIDTH if image_width > 0 else 1.0

    x, y, width, _ = panel
    left_padding = max(1, int(round(TITLE_LEFT_PADDING * scale)))
    right_padding = max(1, int(round(TITLE_RIGHT_PADDING * scale)))
    top_padding = max(1, int(round(TITLE_TOP_PADDING * scale)))
    crop_height = max(1, int(round(TITLE_CROP_HEIGHT * scale)))

    x1 = min(image_width, x + left_padding)
    x2 = max(x1, min(image_width, x + width - right_padding))
    y1 = min(image_height, y + top_padding)
    y2 = min(image_height, y1 + crop_height)

    if x2 <= x1 or y2 <= y1:
        return None

    return (x1, y1, x2 - x1, y2 - y1)


def crop_enemy_composition_title(
    image_bgr: Optional[np.ndarray],
    panel_bbox: Optional[Sequence[int]],
) -> Optional[Tuple[np.ndarray, BBox]]:
    """Return ``(title_crop, title_bbox)`` for a detected panel.

    A copy is returned so a future caller can cache the crop after releasing
    any screenshot lock.  Invalid input returns ``None``.
    """

    if image_bgr is None or not isinstance(image_bgr, np.ndarray) or image_bgr.size == 0:
        return None
    if image_bgr.ndim < 2:
        return None

    title_bbox = get_enemy_composition_title_bbox(panel_bbox, image_bgr.shape)
    if title_bbox is None:
        return None

    x, y, width, height = title_bbox
    crop = image_bgr[y:y + height, x:x + width]
    if crop.size == 0:
        return None

    return crop.copy(), title_bbox


def detect_enemy_composition_panel(
    image_bgr: Optional[np.ndarray],
) -> EnemyCompositionPanelDetection:
    """Detect an enemy-composition tooltip panel in one BGR screenshot.

    The input should be the BGR screenshot after the same width normalization
    used by ``game_state_service``.  The implementation deliberately uses
    grayscale edge geometry and does not require a particular tooltip color.
    """

    base_debug: Dict[str, Any] = {
        "search_roi": None,
        "horizontal_line_count": 0,
        "candidate_count": 0,
    }

    if image_bgr is None or not isinstance(image_bgr, np.ndarray) or image_bgr.size == 0:
        return EnemyCompositionPanelDetection(
            found=False,
            bbox=None,
            score=0.0,
            reason="invalid_image",
            debug=base_debug,
        )

    if image_bgr.ndim != 3 or image_bgr.shape[2] != 3:
        return EnemyCompositionPanelDetection(
            found=False,
            bbox=None,
            score=0.0,
            reason="expected_bgr_color_image",
            debug=base_debug,
        )

    image_height, image_width = image_bgr.shape[:2]
    if image_width < 640 or image_height < 360:
        return EnemyCompositionPanelDetection(
            found=False,
            bbox=None,
            score=0.0,
            reason="image_too_small",
            debug=base_debug,
        )

    scale = image_width / BASE_WIDTH
    search_x0 = max(0, min(image_width - 1, int(round(SEARCH_X_MIN * scale))))
    search_y0 = max(0, min(image_height - 1, int(round(SEARCH_Y_MIN * scale))))
    search_x1 = image_width
    search_y1 = max(search_y0 + 1, min(image_height, int(round(SEARCH_Y_MAX * scale))))
    search_roi = (search_x0, search_y0, search_x1 - search_x0, search_y1 - search_y0)
    base_debug["search_roi"] = search_roi

    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(blurred, EDGE_LOW_THRESHOLD, EDGE_HIGH_THRESHOLD)
    roi_edges = edges[search_y0:search_y1, search_x0:search_x1]

    horizontal_lines = _find_horizontal_lines(
        roi_edges=roi_edges,
        offset_x=search_x0,
        offset_y=search_y0,
        image_width=image_width,
        scale=scale,
    )
    base_debug["horizontal_line_count"] = len(horizontal_lines)

    if not horizontal_lines:
        return EnemyCompositionPanelDetection(
            found=False,
            bbox=None,
            score=0.0,
            reason="no_horizontal_panel_lines",
            debug=base_debug,
        )

    candidates = _build_panel_candidates(
        edges=edges,
        gray=gray,
        horizontal_lines=horizontal_lines,
        search_roi=search_roi,
        scale=scale,
    )
    base_debug["candidate_count"] = len(candidates)

    if not candidates:
        return EnemyCompositionPanelDetection(
            found=False,
            bbox=None,
            score=0.0,
            reason="no_geometric_panel_pair",
            debug=base_debug,
        )

    best = max(candidates, key=lambda candidate: candidate["score"])
    debug = dict(base_debug)
    debug.update(
        {
            "candidate_bbox": best["bbox"],
            "candidate_score": float(best["score"]),
            "line_pair": (best["top_y"], best["bottom_y"]),
            "horizontal_support_top": float(best["horizontal_support_top"]),
            "horizontal_support_bottom": float(best["horizontal_support_bottom"]),
            "vertical_support_left": float(best["vertical_support_left"]),
            "vertical_support_right": float(best["vertical_support_right"]),
            "line_overlap_ratio": float(best["line_overlap_ratio"]),
            "panel_width": int(best["panel_width"]),
            "panel_height": int(best["panel_height"]),
            "interior_median_gray": float(best["interior_median_gray"]),
        }
    )

    if best["score"] < PANEL_SCORE_THRESHOLD:
        return EnemyCompositionPanelDetection(
            found=False,
            bbox=None,
            score=float(best["score"]),
            reason="geometric_candidate_below_threshold",
            debug=debug,
        )

    bbox = best["bbox"]
    title_bbox = get_enemy_composition_title_bbox(bbox, image_bgr.shape)
    return EnemyCompositionPanelDetection(
        found=True,
        bbox=bbox,
        score=float(best["score"]),
        reason="horizontal_borders_with_vertical_sides",
        title_bbox=title_bbox,
        debug=debug,
    )


def _find_horizontal_lines(
    roi_edges: np.ndarray,
    offset_x: int,
    offset_y: int,
    image_width: int,
    scale: float,
) -> List[Tuple[int, int, int, int]]:
    """Return long, near-horizontal Hough segments near the right edge."""

    min_line_length = max(30, int(round(HOUGH_MIN_LINE_LENGTH * scale)))
    max_line_gap = max(2, int(round(HOUGH_MAX_LINE_GAP * scale)))
    lines = cv2.HoughLinesP(
        roi_edges,
        rho=1,
        theta=np.pi / 180.0,
        threshold=HOUGH_THRESHOLD,
        minLineLength=min_line_length,
        maxLineGap=max_line_gap,
    )

    if lines is None:
        return []

    min_span = max(30, int(round(MIN_HORIZONTAL_LINE_SPAN * scale)))
    right_edge_min = image_width - max(15, int(round(35 * scale)))
    result = set()

    for x1, y1, x2, y2 in lines.reshape(-1, 4):
        x1, y1, x2, y2 = (int(value) for value in (x1, y1, x2, y2))
        if abs(y2 - y1) > max(3, int(round(3 * scale))):
            continue

        local_x1, local_x2 = sorted((x1, x2))
        span = local_x2 - local_x1
        absolute_x1 = local_x1 + offset_x
        absolute_x2 = local_x2 + offset_x
        if span < min_span or absolute_x2 < right_edge_min:
            continue

        absolute_y = int(round((y1 + y2) / 2.0)) + offset_y
        result.add((absolute_y, absolute_x1, absolute_x2, span))

    return sorted(result, key=lambda line: (line[0], line[1], -line[3]))


def _build_panel_candidates(
    edges: np.ndarray,
    gray: np.ndarray,
    horizontal_lines: Sequence[Tuple[int, int, int, int]],
    search_roi: BBox,
    scale: float,
) -> List[Dict[str, Any]]:
    """Pair horizontal lines and score the rectangle's remaining geometry."""

    image_height, image_width = edges.shape[:2]
    search_x0, search_y0, _, _ = search_roi
    min_height = max(20, int(round(MIN_PANEL_HEIGHT * scale)))
    max_height = max(min_height + 1, int(round(MAX_PANEL_HEIGHT * scale)))
    min_width = max(30, int(round(MIN_PANEL_WIDTH * scale)))
    max_width = max(min_width + 1, int(round(MAX_PANEL_WIDTH * scale)))

    left_search_min = max(search_x0, min(image_width - min_width, int(round(1450 * scale))))
    left_search_max = min(image_width - min_width, int(round(1600 * scale)))
    right_search_min = max(search_x0, image_width - max(15, int(round(30 * scale))))
    right_search_max = image_width - 1

    candidates: List[Dict[str, Any]] = []
    lines = list(horizontal_lines)

    for top_index, top_line in enumerate(lines):
        top_y, top_x1, top_x2, top_span = top_line

        for bottom_line in lines[top_index + 1:]:
            bottom_y, bottom_x1, bottom_x2, bottom_span = bottom_line
            height = bottom_y - top_y
            if height < min_height:
                continue
            if height > max_height:
                # Lines are sorted by y, so later pairs will only be taller.
                break

            overlap = max(0, min(top_x2, bottom_x2) - max(top_x1, bottom_x1))
            overlap_ratio = overlap / max(1, max(top_span, bottom_span))
            if overlap_ratio < MIN_LINE_OVERLAP_RATIO:
                continue

            left_support, left_x = _best_vertical_support(
                edges=edges,
                top_y=top_y,
                bottom_y=bottom_y,
                x_min=left_search_min,
                x_max=left_search_max,
            )
            right_support, right_x = _best_vertical_support(
                edges=edges,
                top_y=top_y,
                bottom_y=bottom_y,
                x_min=right_search_min,
                x_max=right_search_max,
            )
            if left_x is None or right_x is None:
                continue

            panel_width = right_x - left_x
            if panel_width < min_width or panel_width > max_width:
                continue
            if left_support < MIN_VERTICAL_SUPPORT or right_support < MIN_VERTICAL_SUPPORT:
                continue

            horizontal_support_top = _best_horizontal_support(
                edges=edges,
                y=top_y,
                x1=left_x,
                x2=right_x,
            )
            horizontal_support_bottom = _best_horizontal_support(
                edges=edges,
                y=bottom_y,
                x1=left_x,
                x2=right_x,
            )
            if min(horizontal_support_top, horizontal_support_bottom) < MIN_HORIZONTAL_SUPPORT:
                continue

            inner_x1 = max(0, left_x + max(4, int(round(12 * scale))))
            inner_x2 = min(image_width, right_x - max(4, int(round(12 * scale))))
            inner_y1 = max(0, top_y + max(4, int(round(12 * scale))))
            inner_y2 = min(image_height, bottom_y - max(4, int(round(12 * scale))))
            interior = gray[inner_y1:inner_y2, inner_x1:inner_x2]
            interior_median = float(np.median(interior)) if interior.size else 255.0

            line_quality = min(1.0, min(top_span, bottom_span) / max(1.0, 400.0 * scale))
            horizontal_quality = min(horizontal_support_top, horizontal_support_bottom)
            vertical_quality = min(left_support, right_support)
            width_quality = max(
                0.0,
                1.0 - abs(panel_width - 405.0 * scale) / max(1.0, 100.0 * scale),
            )
            dark_interior_quality = max(0.0, min(1.0, 1.0 - interior_median / 100.0))

            score = (
                0.25 * line_quality
                + 0.20 * horizontal_quality
                + 0.35 * vertical_quality
                + 0.10 * min(1.0, overlap_ratio)
                + 0.05 * width_quality
                + 0.05 * dark_interior_quality
            )

            bbox = _make_panel_bbox(
                left_x=left_x,
                top_y=top_y,
                right_x=right_x,
                bottom_y=bottom_y,
                image_shape=edges.shape,
                scale=scale,
            )
            if bbox is None:
                continue

            candidates.append(
                {
                    "bbox": bbox,
                    "score": float(score),
                    "top_y": int(top_y),
                    "bottom_y": int(bottom_y),
                    "panel_width": int(panel_width),
                    "panel_height": int(height),
                    "horizontal_support_top": float(horizontal_support_top),
                    "horizontal_support_bottom": float(horizontal_support_bottom),
                    "vertical_support_left": float(left_support),
                    "vertical_support_right": float(right_support),
                    "line_overlap_ratio": float(overlap_ratio),
                    "interior_median_gray": float(interior_median),
                }
            )

    return candidates


def _best_vertical_support(
    edges: np.ndarray,
    top_y: int,
    bottom_y: int,
    x_min: int,
    x_max: int,
) -> Tuple[float, Optional[int]]:
    """Find the strongest mostly-vertical edge in an x search interval."""

    image_height, image_width = edges.shape[:2]
    top_y = max(0, min(image_height - 1, top_y))
    bottom_y = max(top_y + 1, min(image_height, bottom_y + 1))
    x_min = max(0, min(image_width - 1, x_min))
    x_max = max(x_min, min(image_width - 1, x_max))
    height = max(1, bottom_y - top_y)

    best_score = 0.0
    best_x: Optional[int] = None
    for x in range(x_min, x_max + 1):
        band_x1 = max(0, x - 2)
        band_x2 = min(image_width, x + 3)
        band = edges[top_y:bottom_y, band_x1:band_x2] > 0
        if band.size == 0:
            continue
        score = float(np.count_nonzero(band, axis=0).max()) / height
        if score > best_score:
            best_score = score
            best_x = x

    return best_score, best_x


def _best_horizontal_support(edges: np.ndarray, y: int, x1: int, x2: int) -> float:
    """Find horizontal edge coverage near a proposed top/bottom row."""

    image_height, image_width = edges.shape[:2]
    x1 = max(0, min(image_width - 1, x1))
    x2 = max(x1 + 1, min(image_width, x2 + 1))
    y1 = max(0, y - 3)
    y2 = min(image_height, y + 4)
    band = edges[y1:y2, x1:x2] > 0
    if band.size == 0:
        return 0.0

    width = max(1, x2 - x1)
    return float(np.count_nonzero(band, axis=1).max()) / width


def _make_panel_bbox(
    left_x: int,
    top_y: int,
    right_x: int,
    bottom_y: int,
    image_shape: Sequence[int],
    scale: float,
) -> Optional[BBox]:
    """Add a small border margin and return a clipped panel box."""

    margin_x = max(1, int(round(3 * scale)))
    margin_y = max(1, int(round(2 * scale)))
    raw_bbox = (
        left_x - margin_x,
        top_y - margin_y,
        (right_x - left_x) + 2 * margin_x,
        (bottom_y - top_y) + 2 * margin_y,
    )
    return clip_bbox(raw_bbox, image_shape)


__all__ = [
    "BBox",
    "DETECTOR_PARAMETERS",
    "EnemyCompositionPanelDetection",
    "clip_bbox",
    "crop_enemy_composition_title",
    "detect_enemy_composition_panel",
    "get_enemy_composition_title_bbox",
]
