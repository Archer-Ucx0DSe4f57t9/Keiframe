"""Pure inference for the validated Malwarfare 3840 Time Candidate-v5."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any

import numpy as np

from .time import (
    SLOT_CLASSES,
    SLOT_NAMES,
    SLOT_RECTS,
    predict_centroid_with_offset,
    presence_passes,
    soft_yellow_projection,
    yellow_presence_statistics,
)


TIME_3840_CANDIDATE_VERSION = "malwarfare_zh_3840_time_candidate_v5"
TIME_3840_NUMERIC_VERSION = TIME_3840_CANDIDATE_VERSION
TIME_3840_MODEL_SHA256 = (
    "ca27ffe2330c677733d706e2d28f1365a0fd3c57d090c7ef68a6ea469e935340"
)
TIME_3840_PRESENCE_THRESHOLDS = {
    "core_active_pixel_minimum": 45,
    "core_strip_left_active_pixel_minimum": 16,
    "core_strip_middle_active_pixel_minimum": 6,
    "core_strip_right_active_pixel_minimum": 14,
    "yellow_peak_minimum": 229,
}


@dataclass(frozen=True)
class Time3840Model:
    path: str
    sha256: str
    base_centroids: tuple[np.ndarray, np.ndarray, np.ndarray]
    max_shift: int


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_time_3840_model(
    path: str | Path, *, expected_sha256: str = TIME_3840_MODEL_SHA256
) -> Time3840Model:
    model_path = Path(path).resolve()
    try:
        actual_sha256 = _sha256_file(model_path)
    except OSError as exc:
        raise ValueError(f"could not load frozen 3840 Time model: {model_path}") from exc
    if actual_sha256 != expected_sha256:
        raise ValueError(
            "3840 Time model SHA-256 mismatch: "
            f"expected {expected_sha256}, got {actual_sha256}"
        )
    try:
        with np.load(model_path, allow_pickle=False) as archive:
            required = {
                "model_schema", "candidate_version", "classifier",
                "roi_shape_hw", "projection_version", "slot_names",
                "slot_rects_xywh", "max_shift", "slot_0_labels",
                "slot_1_labels", "slot_2_labels", "slot_0_centroids",
                "slot_1_centroids", "slot_2_centroids",
                "supported_minimum_mss", "supported_maximum_mss",
            }
            missing = required - set(archive.files)
            if missing:
                raise ValueError(f"3840 Time v5 model is missing arrays: {sorted(missing)}")
            if str(archive["model_schema"].item()) != "malwarfare_time_centroid_ncc_v2":
                raise ValueError("3840 Time v5 model schema mismatch")
            if str(archive["candidate_version"].item()) != TIME_3840_CANDIDATE_VERSION:
                raise ValueError("3840 Time v5 candidate identity mismatch")
            if str(archive["classifier"].item()) != "centroid_ncc":
                raise ValueError("3840 Time v5 classifier mismatch")
            if tuple(int(x) for x in archive["roi_shape_hw"]) != (29, 53):
                raise ValueError("3840 Time v5 ROI shape mismatch")
            if str(archive["projection_version"].item()) != "soft_yellow_projection_v1":
                raise ValueError("3840 Time v5 projection mismatch")
            if tuple(str(x) for x in archive["slot_names"]) != SLOT_NAMES:
                raise ValueError("3840 Time v5 slot names mismatch")
            expected_rects = tuple(
                tuple(rect[key] for key in ("x", "y", "width", "height"))
                for rect in SLOT_RECTS
            )
            actual_rects = tuple(
                tuple(int(x) for x in row) for row in archive["slot_rects_xywh"]
            )
            if actual_rects != expected_rects:
                raise ValueError("3840 Time v5 slot geometry mismatch")
            labels = tuple(
                tuple(str(x) for x in archive[f"slot_{slot}_labels"])
                for slot in range(3)
            )
            if labels != SLOT_CLASSES:
                raise ValueError("3840 Time v5 class labels mismatch")
            if str(archive["supported_minimum_mss"].item()) != "000" or str(archive["supported_maximum_mss"].item()) != "259":
                raise ValueError("3840 Time v5 supported range mismatch")
            max_shift = int(archive["max_shift"].item())
            centroids = tuple(
                np.asarray(archive[f"slot_{slot}_centroids"], dtype=np.float32)
                for slot in range(3)
            )
    except OSError as exc:
        raise ValueError(f"could not load frozen 3840 Time model: {model_path}") from exc
    expected_shapes = tuple((len(classes), 88) for classes in SLOT_CLASSES)
    if tuple(value.shape for value in centroids) != expected_shapes or max_shift != 1:
        raise ValueError("3840 Time v5 centroid shape or shift mismatch")
    for value in centroids:
        if not np.isfinite(value).all():
            raise ValueError("3840 Time v5 centroids contain non-finite values")
        value.setflags(write=False)
    return Time3840Model(
        path=str(model_path), sha256=actual_sha256,
        base_centroids=(centroids[0], centroids[1], centroids[2]),
        max_shift=max_shift,
    )


def predict_time_presence_3840(roi_bgr: np.ndarray) -> dict[str, Any]:
    statistics = yellow_presence_statistics(roi_bgr)
    present = presence_passes(statistics, TIME_3840_PRESENCE_THRESHOLDS)
    return {
        "present": bool(present), "statistics": statistics,
        "thresholds": dict(TIME_3840_PRESENCE_THRESHOLDS),
    }


def predict_time_numeric_3840(
    roi_bgr: np.ndarray, model: Time3840Model
) -> dict[str, Any]:
    projection = soft_yellow_projection(roi_bgr)
    digits: list[str] = []
    slots: list[dict[str, Any]] = []
    for slot, name in enumerate(SLOT_NAMES):
        result = predict_centroid_with_offset(
            projection, slot, model.base_centroids[slot], SLOT_CLASSES[slot],
            shift1=True,
        )
        digits.append(result[0])
        slots.append({
            "slot": name, "digit": result[0], "score": result[1],
            "second_score": result[2], "margin": result[3],
            "offset": list(result[5]),
        })
    value = "".join(digits)
    if len(value) != 3 or not value.isdigit() or not 0 <= int(value) <= 259:
        raise ValueError(f"3840 Time model emitted out-of-scope MSS: {value!r}")
    return {
        "value": value, "digits": digits, "slots": slots,
        "three_five_discriminator_invoked_slots": [],
        "candidate_version": TIME_3840_CANDIDATE_VERSION,
    }


__all__ = [
    "TIME_3840_CANDIDATE_VERSION", "TIME_3840_MODEL_SHA256",
    "TIME_3840_NUMERIC_VERSION", "TIME_3840_PRESENCE_THRESHOLDS",
    "Time3840Model", "load_time_3840_model",
    "predict_time_numeric_3840", "predict_time_presence_3840",
]
