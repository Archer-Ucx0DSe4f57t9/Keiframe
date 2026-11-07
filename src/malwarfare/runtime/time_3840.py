"""Pure inference for the frozen Malwarfare 3840 Candidate-v4 Time model."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from .time import (
    SLOT_CLASSES,
    SLOT_NAMES,
    load_time_recognizer_model,
    predict_centroid_with_offset,
    presence_passes,
    soft_yellow_projection,
    yellow_presence_statistics,
)


TIME_3840_CANDIDATE_VERSION = "malwarfare_zh_3840_candidate_v4"
TIME_3840_NUMERIC_VERSION = "malwarfare_zh_3840_candidate_v3"
TIME_3840_MODEL_SHA256 = (
    "e827381a2edf7073ea8999c4229767907c501cb2c4dcc80284fb34b0fea7b0f7"
)
TIME_3840_PRESENCE_THRESHOLDS = {
    "core_active_pixel_minimum": 54,
    "core_strip_left_active_pixel_minimum": 17,
    "core_strip_middle_active_pixel_minimum": 8,
    "core_strip_right_active_pixel_minimum": 18,
    "yellow_peak_minimum": 255,
}


@dataclass(frozen=True)
class Time3840Model:
    path: str
    sha256: str
    base_centroids: tuple[np.ndarray, np.ndarray, np.ndarray]
    shared_three_five_prototypes: np.ndarray
    invoke_rule: str


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_time_3840_model(
    path: str | Path, *, expected_sha256: str = TIME_3840_MODEL_SHA256
) -> Time3840Model:
    """Load and validate the byte-identical Candidate-v3 numeric model."""

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
    base = load_time_recognizer_model(
        model_path, expected_sha256=expected_sha256
    )
    try:
        with np.load(model_path, allow_pickle=False) as archive:
            required = {
                "candidate_v3_version",
                "supported_time_minimum_mss",
                "supported_time_maximum_mss",
                "minute_classes_v3",
                "three_five_enabled",
                "three_five_slot_scope",
                "three_five_labels",
                "three_five_feature_version",
                "three_five_decision_method",
                "three_five_invoke_rule",
                "three_five_shared_prototypes",
            }
            missing = required - set(archive.files)
            if missing:
                raise ValueError(
                    f"3840 Time model is missing arrays: {sorted(missing)}"
                )
            if str(archive["candidate_v3_version"].item()) != TIME_3840_NUMERIC_VERSION:
                raise ValueError("3840 Time numeric candidate version mismatch")
            if (
                str(archive["supported_time_minimum_mss"].item()) != "000"
                or str(archive["supported_time_maximum_mss"].item()) != "259"
            ):
                raise ValueError("3840 Time supported range mismatch")
            if tuple(str(item) for item in archive["minute_classes_v3"]) != (
                "0",
                "1",
                "2",
            ):
                raise ValueError("3840 Time minute classes mismatch")
            if not bool(archive["three_five_enabled"].item()):
                raise ValueError("3840 Time 3/5 discriminator is disabled")
            if tuple(str(item) for item in archive["three_five_labels"]) != (
                "3",
                "5",
            ):
                raise ValueError("3840 Time 3/5 labels mismatch")
            prototypes = np.asarray(
                archive["three_five_shared_prototypes"], dtype=np.float32
            )
            invoke_rule = str(archive["three_five_invoke_rule"].item())
    except OSError as exc:
        raise ValueError(f"could not load frozen 3840 Time model: {model_path}") from exc
    if prototypes.shape != (2, 88) or not np.isfinite(prototypes).all():
        raise ValueError("3840 Time 3/5 prototypes are invalid")
    prototypes.setflags(write=False)
    return Time3840Model(
        path=str(model_path),
        sha256=actual_sha256,
        base_centroids=base.centroids,
        shared_three_five_prototypes=prototypes,
        invoke_rule=invoke_rule,
    )


def predict_time_presence_3840(roi_bgr: np.ndarray) -> dict[str, Any]:
    statistics = yellow_presence_statistics(roi_bgr)
    present = presence_passes(statistics, TIME_3840_PRESENCE_THRESHOLDS)
    return {
        "present": bool(present),
        "statistics": statistics,
        "thresholds": dict(TIME_3840_PRESENCE_THRESHOLDS),
    }


def predict_time_numeric_3840(
    roi_bgr: np.ndarray, model: Time3840Model
) -> dict[str, Any]:
    """Apply the frozen Candidate-v3 numeric and 3/5 decision logic."""

    projection = soft_yellow_projection(roi_bgr)
    digits: list[str] = []
    invoked: list[str] = []
    for slot, name in enumerate(SLOT_NAMES):
        base = predict_centroid_with_offset(
            projection,
            slot,
            model.base_centroids[slot],
            SLOT_CLASSES[slot],
            shift1=True,
        )
        digit = base[0]
        if slot in (1, 2):
            order = np.argsort(base[4])[::-1]
            top_two = {SLOT_CLASSES[slot][int(item)] for item in order[:2]}
            if top_two == {"3", "5"}:
                digit = predict_centroid_with_offset(
                    projection,
                    slot,
                    model.shared_three_five_prototypes,
                    ("3", "5"),
                    shift1=True,
                )[0]
                invoked.append(name)
        digits.append(digit)
    value = "".join(digits)
    if len(value) != 3 or not value.isdigit() or not 0 <= int(value) <= 259:
        raise ValueError(f"3840 Time model emitted out-of-scope MSS: {value!r}")
    return {
        "value": value,
        "digits": digits,
        "three_five_discriminator_invoked_slots": invoked,
    }


__all__ = [
    "TIME_3840_CANDIDATE_VERSION",
    "TIME_3840_MODEL_SHA256",
    "TIME_3840_NUMERIC_VERSION",
    "TIME_3840_PRESENCE_THRESHOLDS",
    "Time3840Model",
    "load_time_3840_model",
    "predict_time_numeric_3840",
    "predict_time_presence_3840",
]
