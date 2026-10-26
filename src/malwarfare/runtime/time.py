"""Frozen Time inference with no POC, dataset, video, or analysis imports."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Literal, Mapping

import cv2
import numpy as np


ROI_SHAPE = (29, 53)
SLOT_CLASSES = (("0", "1", "2"), tuple("012345"), tuple("0123456789"))
SLOT_NAMES = ("minute", "seconds_tens", "seconds_ones")
SLOT_RECTS = (
    {"x": 15, "y": 7, "width": 8, "height": 11},
    {"x": 27, "y": 7, "width": 8, "height": 11},
    {"x": 35, "y": 7, "width": 8, "height": 11},
)
COLON_RECT = {"x": 23, "y": 7, "width": 4, "height": 11}
CANDIDATE_NAME = "poc_a_centroid_ncc_shift1"
CANDIDATE_VERSION = "malwarfare_time_poc_a_shift1_v1"
RESOURCE_VERSION = "time_zh_2560_v1"
PROJECTION_VERSION = "soft_yellow_projection_v1"
ROI_VERSION = "malwarfare_time_canonical_53x29_v1"
TRANSLATION_MODE = "independent_per_slot_9_way_max_ncc"
PRESENCE_VERSION = "malwarfare_time_development_presence_v1"
PRESENCE_THRESHOLDS = {
    "yellow_peak_minimum": 169,
    "core_active_pixel_minimum": 60,
    "core_strip_left_active_pixel_minimum": 12,
    "core_strip_middle_active_pixel_minimum": 12,
    "core_strip_right_active_pixel_minimum": 12,
}
YELLOW_EXCESS_ACTIVE_THRESHOLD = 40
STRIP_ACTIVE_THRESHOLD = 60
CORE_RECT = {"x": 17, "y": 7, "width": 23, "height": 11}
CORE_STRIP_RECTS = {
    "left": {"x": 17, "y": 7, "width": 7, "height": 11},
    "middle": {"x": 24, "y": 7, "width": 8, "height": 11},
    "right": {"x": 32, "y": 7, "width": 8, "height": 11},
}
DEFAULT_TIME_RUNTIME_RESOURCE_DIR = (
    Path(__file__).resolve().parents[3]
    / "resources"
    / "malwarfare"
    / RESOURCE_VERSION
)


@dataclass(frozen=True)
class TimeRuntimeResource:
    resource_dir: Path
    model_path: Path
    model_sha256: str
    candidate_version: str
    presence_thresholds: Mapping[str, int]


@dataclass(frozen=True)
class TimeRecognizerModel:
    path: str
    sha256: str
    candidate_name: str
    candidate_version: str
    centroids: tuple[np.ndarray, np.ndarray, np.ndarray]
    labels: tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]


@dataclass(frozen=True)
class TimeSlotResult:
    name: str
    digit: str
    score: float
    second_score: float
    margin: float
    dx: int
    dy: int


@dataclass(frozen=True)
class NumericTimeResult:
    value: str
    digits: tuple[str, str, str]
    slots: tuple[TimeSlotResult, TimeSlotResult, TimeSlotResult]
    minimum_slot_margin: float
    candidate_version: str
    model_sha256: str


@dataclass(frozen=True)
class TimePresenceResult:
    present: bool
    status: Literal["numeric", "empty"]
    statistics: Mapping[str, int | float]
    thresholds: Mapping[str, int]
    presence_version: str
    evidence_role: str


@dataclass(frozen=True)
class TimeRecognitionResult:
    status: Literal["numeric", "empty"]
    value: str | None
    digits: tuple[str, str, str] | None
    slot_scores: tuple[float, float, float] | None
    slot_margins: tuple[float, float, float] | None
    slot_offsets: tuple[tuple[int, int], tuple[int, int], tuple[int, int]] | None
    minimum_slot_margin: float | None
    presence: TimePresenceResult
    candidate_version: str
    model_sha256: str


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_time_runtime_resource(
    resource_dir: str | Path = DEFAULT_TIME_RUNTIME_RESOURCE_DIR,
) -> TimeRuntimeResource:
    """Validate the production manifest without coupling to provenance text."""

    root = Path(resource_dir).resolve()
    manifest_path = root / "manifest.json"
    try:
        manifest: dict[str, Any] = json.loads(
            manifest_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"could not load frozen Time runtime manifest: {manifest_path}"
        ) from exc

    expected = {
        "schema_version": 1,
        "task": "time",
        "language": "zh",
        "resource_version": RESOURCE_VERSION,
        "candidate_name": CANDIDATE_NAME,
        "candidate_version": CANDIDATE_VERSION,
        "projection_version": PROJECTION_VERSION,
        "presence_version": PRESENCE_VERSION,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise ValueError(f"unexpected frozen Time runtime manifest field: {key}")

    roi = manifest.get("roi")
    if not isinstance(roi, dict) or roi.get("version") != ROI_VERSION:
        raise ValueError("unexpected frozen Time ROI version")
    if (roi.get("width"), roi.get("height")) != (ROI_SHAPE[1], ROI_SHAPE[0]):
        raise ValueError("unexpected frozen Time ROI geometry")

    slot_geometry = manifest.get("slot_geometry")
    expected_slots = {
        name: rect for name, rect in zip(SLOT_NAMES, SLOT_RECTS)
    }
    if slot_geometry != expected_slots or manifest.get("colon_rect") != COLON_RECT:
        raise ValueError("unexpected frozen Time slot/colon geometry")
    if manifest.get("translation_mode") != TRANSLATION_MODE:
        raise ValueError("unexpected frozen Time translation mode")

    thresholds = manifest.get("presence_thresholds")
    if not isinstance(thresholds, dict) or set(thresholds) != set(PRESENCE_THRESHOLDS):
        raise ValueError("unexpected frozen Time presence threshold fields")
    parsed_thresholds: dict[str, int] = {}
    for key, expected_value in PRESENCE_THRESHOLDS.items():
        raw = thresholds[key]
        if isinstance(raw, bool) or not isinstance(raw, int) or raw != expected_value:
            raise ValueError(f"unexpected frozen Time presence threshold: {key}")
        parsed_thresholds[key] = raw

    model = manifest.get("model")
    if not isinstance(model, dict):
        raise ValueError("frozen Time model entry is missing")
    filename = model.get("filename")
    sha256 = model.get("sha256")
    if filename != "model.npz":
        raise ValueError("unexpected frozen Time model filename")
    if not isinstance(sha256, str) or re.fullmatch(r"[0-9a-f]{64}", sha256) is None:
        raise ValueError("invalid frozen Time model SHA-256")
    model_path = root / filename
    if model_path.parent != root:
        raise ValueError("Time model must be directly inside its resource directory")
    return TimeRuntimeResource(
        resource_dir=root,
        model_path=model_path,
        model_sha256=sha256,
        candidate_version=str(manifest["candidate_version"]),
        presence_thresholds=MappingProxyType(parsed_thresholds),
    )


def _load_frozen_time_model(path: Path) -> dict[str, Any]:
    try:
        with np.load(path, allow_pickle=False) as archive:
            required = {
                "candidate_name",
                "roi_shape_hw",
                "roi_version",
                "slot_names",
                "slot_rects_xywh",
                "colon_rect_xywh",
                "projection_version",
                "translation_dx",
                "translation_dy",
                "translation_mode",
                "slot_0_labels",
                "slot_1_labels",
                "slot_2_labels",
                "slot_0_centroids",
                "slot_1_centroids",
                "slot_2_centroids",
            }
            missing = required - set(archive.files)
            if missing:
                raise ValueError(
                    f"frozen Time model is missing keys: {sorted(missing)}"
                )
            candidate_name = str(archive["candidate_name"].item())
            roi_shape = tuple(int(value) for value in archive["roi_shape_hw"])
            roi_version = str(archive["roi_version"].item())
            slot_names = tuple(str(value) for value in archive["slot_names"])
            slot_rects = np.asarray(archive["slot_rects_xywh"], dtype=np.int16)
            colon_rect = np.asarray(archive["colon_rect_xywh"], dtype=np.int16)
            dx = tuple(int(value) for value in archive["translation_dx"])
            dy = tuple(int(value) for value in archive["translation_dy"])
            labels = tuple(
                tuple(str(value) for value in archive[f"slot_{slot}_labels"])
                for slot in range(3)
            )
            centroids = tuple(
                np.asarray(archive[f"slot_{slot}_centroids"], dtype=np.float32)
                for slot in range(3)
            )
            projection_version = str(archive["projection_version"].item())
            translation_mode = str(archive["translation_mode"].item())
    except OSError as exc:
        raise ValueError(f"could not load frozen Time model: {path}") from exc

    expected_slot_rects = np.asarray(
        [
            [rect["x"], rect["y"], rect["width"], rect["height"]]
            for rect in SLOT_RECTS
        ],
        dtype=np.int16,
    )
    expected_colon_rect = np.asarray(
        [
            COLON_RECT["x"],
            COLON_RECT["y"],
            COLON_RECT["width"],
            COLON_RECT["height"],
        ],
        dtype=np.int16,
    )
    if candidate_name != CANDIDATE_NAME:
        raise ValueError("unexpected frozen Time candidate name")
    if roi_shape != ROI_SHAPE or roi_version != ROI_VERSION:
        raise ValueError("unexpected frozen Time ROI contract")
    if (
        slot_names != SLOT_NAMES
        or not np.array_equal(slot_rects, expected_slot_rects)
        or not np.array_equal(colon_rect, expected_colon_rect)
    ):
        raise ValueError("unexpected frozen Time slot metadata")
    if dx != (-1, 0, 1) or dy != (-1, 0, 1):
        raise ValueError("unexpected frozen Time translation tolerance")
    if labels != SLOT_CLASSES:
        raise ValueError("unexpected frozen Time observed classes")
    if projection_version != PROJECTION_VERSION:
        raise ValueError("frozen Time projection version mismatch")
    if translation_mode != TRANSLATION_MODE:
        raise ValueError("frozen Time translation mode mismatch")
    expected_shapes = tuple((len(classes), 88) for classes in SLOT_CLASSES)
    if tuple(model.shape for model in centroids) != expected_shapes:
        raise ValueError("unexpected frozen Time centroid shape")
    if any(not np.isfinite(model).all() for model in centroids):
        raise ValueError("frozen Time centroids contain non-finite values")
    for model in centroids:
        model.setflags(write=False)
    return {"centroids": centroids, "labels": labels}


def load_time_recognizer_model(
    model_path: str | Path, *, expected_sha256: str | None = None
) -> TimeRecognizerModel:
    path = Path(model_path).resolve()
    try:
        actual_sha256 = _sha256_file(path)
    except OSError as exc:
        raise ValueError(f"could not load frozen Time model: {path}") from exc
    if expected_sha256 is not None and actual_sha256 != expected_sha256:
        raise ValueError(
            "frozen Time model SHA-256 mismatch: "
            f"expected {expected_sha256}, got {actual_sha256}"
        )
    loaded = _load_frozen_time_model(path)
    return TimeRecognizerModel(
        path=str(path),
        sha256=actual_sha256,
        candidate_name=CANDIDATE_NAME,
        candidate_version=CANDIDATE_VERSION,
        centroids=loaded["centroids"],
        labels=loaded["labels"],
    )


def _validate_roi(roi_bgr: np.ndarray) -> None:
    if not isinstance(roi_bgr, np.ndarray):
        raise TypeError("Time ROI must be a NumPy array")
    if roi_bgr.dtype != np.uint8:
        raise ValueError(f"Time ROI must have dtype uint8, got {roi_bgr.dtype}")
    if roi_bgr.shape != (ROI_SHAPE[0], ROI_SHAPE[1], 3):
        raise ValueError(
            f"Time ROI must have shape (29, 53, 3), got {roi_bgr.shape}; "
            "stable inference never resizes inputs"
        )


def soft_yellow_projection(roi_bgr: np.ndarray) -> np.ndarray:
    _validate_roi(roi_bgr)
    image = roi_bgr.astype(np.float32) * (1.0 / 255.0)
    blue, green, red = cv2.split(image)
    yellow_base = np.minimum(red, green)
    opponent = np.clip((yellow_base - blue - 0.02) * 2.0, 0.0, 1.0)
    broad = cv2.GaussianBlur(
        opponent, (0, 0), 1.25, borderType=cv2.BORDER_REPLICATE
    )
    local = np.clip((opponent - broad + 0.12) * 2.5, 0.0, 1.0)
    brightness = np.clip((yellow_base - 0.10) * 1.35, 0.0, 1.0)
    return np.ascontiguousarray(
        opponent * (0.35 + 0.65 * local) * (0.35 + 0.65 * brightness),
        dtype=np.float32,
    )


def _extract_slot(
    projection: np.ndarray, slot: int, *, dx: int = 0, dy: int = 0
) -> np.ndarray:
    rect = SLOT_RECTS[slot]
    x, y = rect["x"] + dx, rect["y"] + dy
    crop = projection[y : y + rect["height"], x : x + rect["width"]]
    if crop.shape != (11, 8):
        raise AssertionError("frozen slot rectangle escaped the Time ROI")
    return np.ascontiguousarray(crop, dtype=np.float32)


def _normalized_slot_feature(slot_projection: np.ndarray) -> np.ndarray:
    feature = np.asarray(slot_projection, dtype=np.float32).reshape(-1).copy()
    norm = float(np.linalg.norm(feature))
    if norm > 1e-8:
        feature /= norm
    return feature


def predict_centroid_with_offset(
    projection: np.ndarray,
    slot: int,
    centroids: np.ndarray,
    classes: tuple[str, ...],
    *,
    shift1: bool,
) -> tuple[str, float, float, float, np.ndarray, tuple[int, int]]:
    offsets = ((0, 0),) if not shift1 else tuple(
        (dx, dy) for dy in (-1, 0, 1) for dx in (-1, 0, 1)
    )
    variants = np.asarray(
        [
            _normalized_slot_feature(
                _extract_slot(projection, slot, dx=dx, dy=dy)
            )
            for dx, dy in offsets
        ],
        np.float32,
    )
    similarities = variants @ centroids.T
    scores = np.max(similarities, axis=0)
    order = np.argsort(scores)
    best = int(order[-1])
    second = int(order[-2])
    chosen_variant = int(np.argmax(similarities[:, best]))
    return (
        classes[best],
        float(scores[best]),
        float(scores[second]),
        float(scores[best] - scores[second]),
        scores,
        offsets[chosen_variant],
    )


def yellow_excess(image: np.ndarray) -> np.ndarray:
    if image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("yellow_excess expects a uint8 BGR image")
    blue, green, red = [channel.astype(np.int16) for channel in cv2.split(image)]
    return np.clip(np.minimum(red, green) - blue, 0, 255).astype(np.uint8)


def yellow_presence_statistics(image: np.ndarray) -> dict[str, int | float]:
    yellow = yellow_excess(image)
    x, y = CORE_RECT["x"], CORE_RECT["y"]
    core = yellow[y : y + CORE_RECT["height"], x : x + CORE_RECT["width"]]
    if core.shape != (CORE_RECT["height"], CORE_RECT["width"]):
        raise ValueError(f"Time ROI is too small for fixed core rectangle: {image.shape}")
    binary = (yellow >= YELLOW_EXCESS_ACTIVE_THRESHOLD).astype(np.uint8)
    components, _labels, stats, _centroids = cv2.connectedComponentsWithStats(
        binary, connectivity=8
    )
    component_areas = (
        stats[1:, cv2.CC_STAT_AREA]
        if components > 1
        else np.empty(0, dtype=np.int32)
    )
    mass = int(yellow.sum(dtype=np.int64))
    core_mass = int(core.sum(dtype=np.int64))
    result: dict[str, int | float] = {
        "yellow_mass": mass,
        "yellow_peak": int(yellow.max()),
        "active_pixels_ge_20": int(np.count_nonzero(yellow >= 20)),
        "active_pixels_ge_40": int(np.count_nonzero(binary)),
        "active_pixels_ge_60": int(np.count_nonzero(yellow >= 60)),
        "core_yellow_mass": core_mass,
        "core_active_pixels_ge_40": int(
            np.count_nonzero(core >= YELLOW_EXCESS_ACTIVE_THRESHOLD)
        ),
        "core_mass_fraction": round(core_mass / mass, 8) if mass else 0.0,
        "connected_components_ge_40": int(len(component_areas)),
        "largest_component_area_ge_40": (
            int(component_areas.max()) if len(component_areas) else 0
        ),
    }
    for name, rect in CORE_STRIP_RECTS.items():
        strip = yellow[
            rect["y"] : rect["y"] + rect["height"],
            rect["x"] : rect["x"] + rect["width"],
        ]
        result[f"core_strip_{name}_active_pixels_ge_60"] = int(
            np.count_nonzero(strip >= STRIP_ACTIVE_THRESHOLD)
        )
    return result


def presence_passes(
    statistics: Mapping[str, int | float], thresholds: Mapping[str, int]
) -> bool:
    mapping = {
        "yellow_peak_minimum": "yellow_peak",
        "core_active_pixel_minimum": "core_active_pixels_ge_40",
        "core_strip_left_active_pixel_minimum": "core_strip_left_active_pixels_ge_60",
        "core_strip_middle_active_pixel_minimum": "core_strip_middle_active_pixels_ge_60",
        "core_strip_right_active_pixel_minimum": "core_strip_right_active_pixels_ge_60",
    }
    return all(
        int(statistics[mapping[name]]) >= value
        for name, value in thresholds.items()
    )


def recognize_numeric_time(
    roi_bgr: np.ndarray, model: TimeRecognizerModel
) -> NumericTimeResult:
    _validate_roi(roi_bgr)
    projection = soft_yellow_projection(roi_bgr)
    slots: list[TimeSlotResult] = []
    for slot, name in enumerate(SLOT_NAMES):
        digit, score, second_score, margin, _scores, offset = (
            predict_centroid_with_offset(
                projection,
                slot,
                model.centroids[slot],
                model.labels[slot],
                shift1=True,
            )
        )
        slots.append(
            TimeSlotResult(
                name=name,
                digit=digit,
                score=score,
                second_score=second_score,
                margin=margin,
                dx=offset[0],
                dy=offset[1],
            )
        )
    digits = tuple(item.digit for item in slots)
    value = "".join(digits)
    if len(value) != 3 or any(
        digit not in classes for digit, classes in zip(digits, SLOT_CLASSES)
    ):
        raise RuntimeError(
            f"frozen Time recognizer produced an invalid MSS value: {value!r}"
        )
    return NumericTimeResult(
        value=value,
        digits=(digits[0], digits[1], digits[2]),
        slots=(slots[0], slots[1], slots[2]),
        minimum_slot_margin=min(item.margin for item in slots),
        candidate_version=model.candidate_version,
        model_sha256=model.sha256,
    )


def detect_time_presence(roi_bgr: np.ndarray) -> TimePresenceResult:
    _validate_roi(roi_bgr)
    statistics = yellow_presence_statistics(roi_bgr)
    present = presence_passes(statistics, PRESENCE_THRESHOLDS)
    return TimePresenceResult(
        present=present,
        status="numeric" if present else "empty",
        statistics=statistics,
        thresholds=PRESENCE_THRESHOLDS.copy(),
        presence_version=PRESENCE_VERSION,
        evidence_role=(
            "development presence candidate; Time Round 1 development CV only; "
            "not independently validated"
        ),
    )


def recognize_time(
    roi_bgr: np.ndarray, model: TimeRecognizerModel
) -> TimeRecognitionResult:
    presence = detect_time_presence(roi_bgr)
    if not presence.present:
        return TimeRecognitionResult(
            status="empty",
            value=None,
            digits=None,
            slot_scores=None,
            slot_margins=None,
            slot_offsets=None,
            minimum_slot_margin=None,
            presence=presence,
            candidate_version=model.candidate_version,
            model_sha256=model.sha256,
        )
    numeric = recognize_numeric_time(roi_bgr, model)
    return TimeRecognitionResult(
        status="numeric",
        value=numeric.value,
        digits=numeric.digits,
        slot_scores=tuple(item.score for item in numeric.slots),
        slot_margins=tuple(item.margin for item in numeric.slots),
        slot_offsets=tuple((item.dx, item.dy) for item in numeric.slots),
        minimum_slot_margin=numeric.minimum_slot_margin,
        presence=presence,
        candidate_version=model.candidate_version,
        model_sha256=model.sha256,
    )


__all__ = [
    "CANDIDATE_VERSION",
    "COLON_RECT",
    "DEFAULT_TIME_RUNTIME_RESOURCE_DIR",
    "NumericTimeResult",
    "PRESENCE_THRESHOLDS",
    "PRESENCE_VERSION",
    "RESOURCE_VERSION",
    "ROI_SHAPE",
    "SLOT_CLASSES",
    "SLOT_NAMES",
    "SLOT_RECTS",
    "TimePresenceResult",
    "TimeRecognitionResult",
    "TimeRecognizerModel",
    "TimeRuntimeResource",
    "TimeSlotResult",
    "detect_time_presence",
    "load_time_recognizer_model",
    "load_time_runtime_resource",
    "presence_passes",
    "predict_centroid_with_offset",
    "recognize_numeric_time",
    "recognize_time",
    "soft_yellow_projection",
    "yellow_excess",
    "yellow_presence_statistics",
]
