"""Frozen Count inference with no training, comparison, or analysis imports."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Mapping

import cv2
import numpy as np


COUNT_LABELS = ("c0", "c1", "c2", "c3", "c4")
ROI_SHAPE = (31, 47, 3)
ACTIVE_RESPONSE_MINIMUM = 0.10
HIGH_RESPONSE_MINIMUM = 0.50
PRESENCE_ALGORITHM_VERSION = "count_projection_sum_and_frozen_score_v1"
COUNT_RUNTIME_CANDIDATE_VERSION = "count_zh_2560_v1"
LEGACY_COUNT_RUNTIME_CANDIDATE_VERSION = "count_presence_zh_2560_v1"
COUNT_RUNTIME_PROFILES = ("orange", "blue", "green")
DEFAULT_COUNT_RUNTIME_RESOURCE_DIR = (
    Path(__file__).resolve().parents[3]
    / "resources"
    / "malwarfare"
    / COUNT_RUNTIME_CANDIDATE_VERSION
)
# Compatibility name retained for callers of the former count_presence module.
DEFAULT_COUNT_RUNTIME_CONFIG_DIR = DEFAULT_COUNT_RUNTIME_RESOURCE_DIR


@dataclass(frozen=True)
class CountProjectionStatistics:
    sum: float
    mean: float
    maximum: float
    standard_deviation: float
    active_pixel_count: int
    high_response_pixel_count: int


@dataclass(frozen=True)
class CountPresenceThresholds:
    projection_sum_minimum: float
    best_score_minimum: float

    def __post_init__(self) -> None:
        for name, raw in (
            ("projection_sum_minimum", self.projection_sum_minimum),
            ("best_score_minimum", self.best_score_minimum),
        ):
            if isinstance(raw, bool) or not isinstance(raw, (int, float, np.number)):
                raise TypeError(f"{name} must be a finite real number")
            if not np.isfinite(float(raw)):
                raise ValueError(f"{name} must be finite")


@dataclass(frozen=True)
class CountModelProvenance:
    identifier: str
    provenance_path: str
    sha256: str
    filename: str = ""


@dataclass(frozen=True)
class CountPresenceRuntimeConfig:
    candidate_version: str
    source_resolution_profile: str
    presence_algorithm_version: str
    thresholds: Mapping[str, CountPresenceThresholds]
    models: Mapping[str, CountModelProvenance]
    validation_type: str
    independent_recording_validation: bool
    status: str
    validation_artifact: str
    validation_summary: str

    def for_profile(self, color_profile: str) -> CountPresenceThresholds:
        profile = str(color_profile).lower()
        try:
            return self.thresholds[profile]
        except KeyError as exc:
            raise ValueError(
                f"unsupported Count color profile: {color_profile}"
            ) from exc


@dataclass(frozen=True)
class CountRecognitionResult:
    value: int | None
    present: bool
    raw_prediction: str
    best_score: float
    margin: float
    class_scores: Mapping[str, float]
    projection: CountProjectionStatistics
    thresholds: CountPresenceThresholds
    color_profile: str
    presence_algorithm_version: str = PRESENCE_ALGORITHM_VERSION


def _require_mapping(value: Any, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Count runtime manifest field must be an object: {field}")
    return value


def load_count_presence_runtime_config(
    resource_dir: str | Path = DEFAULT_COUNT_RUNTIME_RESOURCE_DIR,
) -> CountPresenceRuntimeConfig:
    """Load inference-critical Count settings; provenance remains descriptive."""

    manifest_path = Path(resource_dir).resolve() / "manifest.json"
    try:
        manifest: dict[str, Any] = json.loads(
            manifest_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"could not load frozen Count runtime manifest: {manifest_path}"
        ) from exc

    candidate_version = manifest.get("candidate_version")
    if candidate_version not in {
        COUNT_RUNTIME_CANDIDATE_VERSION,
        LEGACY_COUNT_RUNTIME_CANDIDATE_VERSION,
    }:
        raise ValueError("unexpected frozen Count candidate version")
    expected = {
        "schema_version": 1,
        "language": "zh",
        "presence_algorithm_version": PRESENCE_ALGORITHM_VERSION,
        "source_resolution_profile": "native_2560_to_canonical_1920",
    }
    for key, expected_value in expected.items():
        if manifest.get(key) != expected_value:
            raise ValueError(f"unexpected frozen Count runtime manifest field: {key}")
    if manifest.get("task") not in {"count", "count_presence"}:
        raise ValueError("unexpected frozen Count runtime manifest field: task")

    raw_thresholds = _require_mapping(manifest.get("thresholds"), field="thresholds")
    raw_models = _require_mapping(manifest.get("models"), field="models")
    if set(raw_thresholds) != set(COUNT_RUNTIME_PROFILES):
        raise ValueError("Count runtime manifest has unexpected threshold profiles")
    if set(raw_models) != set(COUNT_RUNTIME_PROFILES):
        raise ValueError("Count runtime manifest has unexpected model profiles")

    thresholds: dict[str, CountPresenceThresholds] = {}
    models: dict[str, CountModelProvenance] = {}
    for profile in COUNT_RUNTIME_PROFILES:
        threshold = _require_mapping(
            raw_thresholds[profile], field=f"thresholds.{profile}"
        )
        thresholds[profile] = CountPresenceThresholds(
            projection_sum_minimum=threshold.get("projection_sum_minimum"),
            best_score_minimum=threshold.get("best_score_minimum"),
        )

        model = _require_mapping(raw_models[profile], field=f"models.{profile}")
        identifier = model.get("identifier")
        if not isinstance(identifier, str) or not identifier:
            raise ValueError(f"frozen Count model identity is missing: {profile}")
        sha256 = model.get("sha256")
        if not isinstance(sha256, str) or re.fullmatch(r"[0-9a-f]{64}", sha256) is None:
            raise ValueError(f"invalid frozen Count model SHA-256: {profile}")
        filename = model.get("filename", "")
        if filename and filename != f"{profile}.npz":
            raise ValueError(f"unexpected frozen Count model filename: {profile}")
        models[profile] = CountModelProvenance(
            identifier=identifier,
            provenance_path=str(model.get("provenance_path", "")),
            sha256=sha256,
            filename=str(filename),
        )

    return CountPresenceRuntimeConfig(
        candidate_version=str(candidate_version),
        source_resolution_profile=str(manifest["source_resolution_profile"]),
        presence_algorithm_version=str(manifest["presence_algorithm_version"]),
        thresholds=MappingProxyType(thresholds),
        models=MappingProxyType(models),
        validation_type=str(manifest.get("validation_type", "")),
        independent_recording_validation=bool(
            manifest.get("independent_recording_validation", False)
        ),
        status=str(manifest.get("status", "")),
        validation_artifact=str(manifest.get("validation_artifact", "")),
        validation_summary=str(manifest.get("validation_summary", "")),
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_frozen_count_model(path: str | Path) -> dict[str, Any]:
    """Load the frozen shift-tolerant centroid model without fitting."""

    model_path = Path(path).resolve()
    try:
        digest = _sha256_file(model_path)
        with np.load(model_path, allow_pickle=False) as archive:
            required = {"labels", "centroids", "translation_tolerance"}
            if not required.issubset(archive.files):
                raise ValueError(
                    "frozen Count model is missing arrays: "
                    f"{sorted(required - set(archive.files))}"
                )
            labels = tuple(str(value) for value in archive["labels"].tolist())
            centroids = np.asarray(archive["centroids"], dtype=np.float32)
            translation = np.asarray(
                archive["translation_tolerance"]
            ).reshape(-1)
    except OSError as exc:
        raise ValueError(f"could not load frozen Count model: {model_path}") from exc
    if labels != COUNT_LABELS:
        raise ValueError(f"frozen Count labels must be {COUNT_LABELS}, got {labels}")
    if centroids.shape != (5, 1457):
        raise ValueError(
            f"frozen Count centroids must have shape (5, 1457), got {centroids.shape}"
        )
    if translation.shape != (1,) or int(translation[0]) != 1:
        raise ValueError("frozen Count model must enable shift1 translation tolerance")
    if not np.all(np.isfinite(centroids)):
        raise ValueError("frozen Count centroids contain non-finite values")
    return {
        "path": str(model_path),
        "sha256": digest,
        "size_bytes": model_path.stat().st_size,
        "labels": labels,
        "centroids": centroids,
        "translation_tolerance": True,
    }


def _validate_projection_roi(roi_bgr: np.ndarray) -> None:
    if roi_bgr.shape != ROI_SHAPE or roi_bgr.dtype != np.uint8:
        raise ValueError("soft_count_projection requires a uint8 47x31 BGR ROI")


def soft_orange_projection(roi_bgr: np.ndarray) -> np.ndarray:
    _validate_projection_roi(roi_bgr)
    image = roi_bgr.astype(np.float32) * (1.0 / 255.0)
    blue, green, red = cv2.split(image)
    warm = np.clip((red - blue - 0.025) * 1.75, 0.0, 1.0)
    orange_balance = np.clip((green - blue + 0.035) * 2.25, 0.0, 1.0)
    broad_red = cv2.GaussianBlur(
        red, (0, 0), 2.0, borderType=cv2.BORDER_REPLICATE
    )
    local = np.clip((red - broad_red + 0.075) * 3.25, 0.0, 1.0)
    return np.ascontiguousarray(
        warm * (0.35 + 0.65 * orange_balance) * local
    )


def _soft_blue_projection(roi_bgr: np.ndarray) -> np.ndarray:
    _validate_projection_roi(roi_bgr)
    image = roi_bgr.astype(np.float32) * (1.0 / 255.0)
    blue, green, red = cv2.split(image)
    blue_red = np.clip((blue - 0.5 * (green + red) - 0.015) * 2.0, 0.0, 1.0)
    cyan_balance = np.clip((blue - red + 0.035) * 2.0, 0.0, 1.0)
    broad_blue = cv2.GaussianBlur(
        blue, (0, 0), 2.0, borderType=cv2.BORDER_REPLICATE
    )
    local = np.clip((blue - broad_blue + 0.075) * 3.25, 0.0, 1.0)
    return np.ascontiguousarray(
        blue_red * (0.35 + 0.65 * cyan_balance) * local
    )


def _soft_green_projection(roi_bgr: np.ndarray) -> np.ndarray:
    _validate_projection_roi(roi_bgr)
    image = roi_bgr.astype(np.float32) * (1.0 / 255.0)
    blue, green, red = cv2.split(image)
    opponent = np.clip(
        (green - np.maximum(red, blue) - 0.004) * 3.0, 0.0, 1.0
    )
    chroma = np.maximum(np.maximum(blue, green), red) - np.minimum(
        np.minimum(blue, green), red
    )
    saturation = np.clip(chroma * 2.0, 0.0, 1.0)
    broad_opponent = cv2.GaussianBlur(
        opponent, (0, 0), 1.5, borderType=cv2.BORDER_REPLICATE
    )
    local = np.clip((opponent - broad_opponent + 0.10) * 3.0, 0.0, 1.0)
    return np.ascontiguousarray(opponent * (0.25 + 0.75 * saturation) * local)


def soft_count_projection(roi_bgr: np.ndarray, color_profile: str) -> np.ndarray:
    profile = str(color_profile).lower()
    if profile == "orange":
        return soft_orange_projection(roi_bgr)
    if profile == "blue":
        return _soft_blue_projection(roi_bgr)
    if profile == "green":
        return _soft_green_projection(roi_bgr)
    raise ValueError(f"unsupported Count color profile: {color_profile!r}")


def atomic_feature(projection: np.ndarray) -> np.ndarray:
    feature = np.asarray(projection, dtype=np.float32).reshape(-1).copy()
    feature -= float(feature.mean())
    norm = float(np.linalg.norm(feature))
    if norm > 1e-8:
        feature /= norm
    return feature


def shifted_atomic_features(projection: np.ndarray) -> list[np.ndarray]:
    features: list[np.ndarray] = []
    height, width = ROI_SHAPE[:2]
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            shifted = np.zeros_like(projection)
            src_y0, src_y1 = max(0, -dy), min(height, height - dy)
            src_x0, src_x1 = max(0, -dx), min(width, width - dx)
            shifted[
                src_y0 + dy : src_y1 + dy, src_x0 + dx : src_x1 + dx
            ] = projection[src_y0:src_y1, src_x0:src_x1]
            features.append(atomic_feature(shifted))
    return features


def predict_atomic(
    projection: np.ndarray,
    centroids: np.ndarray,
    *,
    translation_tolerance: bool,
) -> tuple[str, float, float, np.ndarray]:
    variants = (
        shifted_atomic_features(projection)
        if translation_tolerance
        else [atomic_feature(projection)]
    )
    scores = np.max(np.asarray(variants, np.float32) @ centroids.T, axis=0)
    order = np.argsort(scores)
    best = int(order[-1])
    margin = float(scores[best] - scores[int(order[-2])])
    return COUNT_LABELS[best], float(scores[best]), margin, scores


def projection_statistics(projection: np.ndarray) -> CountProjectionStatistics:
    value = np.asarray(projection)
    if value.shape != ROI_SHAPE[:2]:
        raise ValueError(f"Count projection must have shape (31, 47), got {value.shape}")
    if not np.issubdtype(value.dtype, np.floating):
        raise ValueError("Count projection must use a floating dtype")
    if not np.isfinite(value).all():
        raise ValueError("Count projection contains non-finite values")
    return CountProjectionStatistics(
        sum=float(value.sum(dtype=np.float64)),
        mean=float(value.mean(dtype=np.float64)),
        maximum=float(value.max()),
        standard_deviation=float(value.std(dtype=np.float64)),
        active_pixel_count=int(np.count_nonzero(value >= ACTIVE_RESPONSE_MINIMUM)),
        high_response_pixel_count=int(
            np.count_nonzero(value >= HIGH_RESPONSE_MINIMUM)
        ),
    )


def presence_passes(
    statistics: CountProjectionStatistics,
    best_score: float,
    thresholds: CountPresenceThresholds,
) -> bool:
    score = float(best_score)
    if not np.isfinite(score):
        raise ValueError("best_score must be finite")
    return (
        statistics.sum >= float(thresholds.projection_sum_minimum)
        and score >= float(thresholds.best_score_minimum)
    )


def recognize_count_details(
    roi_bgr: np.ndarray,
    *,
    color_profile: str,
    centroids: np.ndarray,
    thresholds: CountPresenceThresholds,
) -> CountRecognitionResult:
    if not isinstance(roi_bgr, np.ndarray):
        raise TypeError("Count ROI must be a numpy.ndarray")
    if roi_bgr.dtype != np.uint8 or roi_bgr.shape != ROI_SHAPE:
        raise ValueError(
            f"Count ROI must have shape {ROI_SHAPE} and dtype uint8; "
            f"got {roi_bgr.shape} {roi_bgr.dtype}"
        )
    centroid_array = np.asarray(centroids)
    if centroid_array.shape != (len(COUNT_LABELS), ROI_SHAPE[0] * ROI_SHAPE[1]):
        raise ValueError(
            "Count centroids must have shape (5, 1457); "
            f"got {centroid_array.shape}"
        )
    projection = soft_count_projection(roi_bgr, color_profile)
    prediction, score, margin, scores = predict_atomic(
        projection, centroid_array, translation_tolerance=True
    )
    statistics = projection_statistics(projection)
    present = presence_passes(statistics, score, thresholds)
    return CountRecognitionResult(
        value=int(prediction[1:]) if present else None,
        present=present,
        raw_prediction=prediction,
        best_score=float(score),
        margin=float(margin),
        class_scores={
            label: float(value) for label, value in zip(COUNT_LABELS, scores)
        },
        projection=statistics,
        thresholds=thresholds,
        color_profile=str(color_profile).lower(),
    )


def recognize_count(
    roi_bgr: np.ndarray,
    *,
    color_profile: str,
    centroids: np.ndarray,
    thresholds: CountPresenceThresholds,
) -> int | None:
    return recognize_count_details(
        roi_bgr,
        color_profile=color_profile,
        centroids=centroids,
        thresholds=thresholds,
    ).value


def recognize_count_runtime(
    roi_bgr: np.ndarray,
    *,
    color_profile: str,
    centroids: np.ndarray,
    runtime_config: CountPresenceRuntimeConfig,
) -> int | None:
    return recognize_count(
        roi_bgr,
        color_profile=color_profile,
        centroids=centroids,
        thresholds=runtime_config.for_profile(color_profile),
    )


__all__ = [
    "ACTIVE_RESPONSE_MINIMUM",
    "COUNT_LABELS",
    "COUNT_RUNTIME_CANDIDATE_VERSION",
    "COUNT_RUNTIME_PROFILES",
    "CountModelProvenance",
    "CountPresenceRuntimeConfig",
    "CountPresenceThresholds",
    "CountProjectionStatistics",
    "CountRecognitionResult",
    "DEFAULT_COUNT_RUNTIME_CONFIG_DIR",
    "DEFAULT_COUNT_RUNTIME_RESOURCE_DIR",
    "HIGH_RESPONSE_MINIMUM",
    "PRESENCE_ALGORITHM_VERSION",
    "atomic_feature",
    "load_count_presence_runtime_config",
    "load_frozen_count_model",
    "predict_atomic",
    "presence_passes",
    "projection_statistics",
    "recognize_count",
    "recognize_count_details",
    "recognize_count_runtime",
    "shifted_atomic_features",
    "soft_count_projection",
    "soft_orange_projection",
]
