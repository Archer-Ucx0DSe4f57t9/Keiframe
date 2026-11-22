"""Pure inference for the frozen Malwarfare 3840 Candidate-v2 Paused model."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from ..paused_recognizer import preprocess_paused_roi


PAUSED_3840_CANDIDATE_NAME = "paused_binary_centroid_margin_v1"
PAUSED_3840_FEATURE_VERSION = "legacy_yellow_v1_binary_flat_l2_v1"
PAUSED_3840_MODEL_SHA256 = (
    "c63580ac829ce5e074819566404b446f6cf1fffa11e64de71075eb99faa76419"
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def paused_binary_feature_3840(roi_bgr: np.ndarray) -> np.ndarray:
    processed = preprocess_paused_roi(roi_bgr)
    feature = np.asarray(processed, np.float32).reshape(-1)
    norm = float(np.linalg.norm(feature))
    if norm > 1e-8:
        feature = feature / norm
    return np.ascontiguousarray(feature, dtype=np.float32)


def load_paused_3840_model(
    path: str | Path, *, expected_sha256: str = PAUSED_3840_MODEL_SHA256
) -> dict[str, Any]:
    model_path = Path(path).resolve()
    try:
        actual_sha256 = _sha256_file(model_path)
        with np.load(model_path, allow_pickle=False) as archive:
            required = {
                "candidate_name",
                "feature_version",
                "processed_shape_hw",
                "positive_centroid",
                "negative_centroid",
                "discrimination_margin_threshold",
                "baseline_positive_ncc_threshold",
                "selected_candidate",
            }
            missing = required - set(archive.files)
            if missing:
                raise ValueError(
                    f"3840 Paused model is missing arrays: {sorted(missing)}"
                )
            candidate_name = str(archive["candidate_name"].item())
            feature_version = str(archive["feature_version"].item())
            shape = tuple(int(value) for value in archive["processed_shape_hw"])
            positive = np.asarray(archive["positive_centroid"], np.float32)
            negative = np.asarray(archive["negative_centroid"], np.float32)
            threshold = float(
                archive["discrimination_margin_threshold"].item()
            )
            baseline = float(archive["baseline_positive_ncc_threshold"].item())
            selected = str(archive["selected_candidate"].item())
    except OSError as exc:
        raise ValueError(
            f"could not load frozen 3840 Paused model: {model_path}"
        ) from exc
    if actual_sha256 != expected_sha256:
        raise ValueError(
            "3840 Paused model SHA-256 mismatch: "
            f"expected {expected_sha256}, got {actual_sha256}"
        )
    if (
        candidate_name != PAUSED_3840_CANDIDATE_NAME
        or feature_version != PAUSED_3840_FEATURE_VERSION
    ):
        raise ValueError("unexpected 3840 Paused model identity")
    if (
        shape != (128, 212)
        or positive.shape != (128 * 212,)
        or negative.shape != (128 * 212,)
    ):
        raise ValueError("unexpected 3840 Paused model geometry")
    if (
        not np.isfinite(positive).all()
        or not np.isfinite(negative).all()
        or not np.isfinite(threshold)
    ):
        raise ValueError("3840 Paused model contains non-finite values")
    if selected not in {"candidate_a_margin", "candidate_b_ncc_and_margin"}:
        raise ValueError("unexpected selected 3840 Paused candidate")
    positive.setflags(write=False)
    negative.setflags(write=False)
    return {
        "candidate_name": candidate_name,
        "feature_version": feature_version,
        "positive_centroid": positive,
        "negative_centroid": negative,
        "threshold": threshold,
        "baseline_threshold": baseline,
        "selected_candidate": selected,
        "sha256": actual_sha256,
    }


def predict_paused_3840(
    model: Mapping[str, Any],
    roi_bgr: np.ndarray,
    *,
    baseline_score: float | None = None,
) -> dict[str, Any]:
    feature = paused_binary_feature_3840(roi_bgr)
    positive = float(feature @ model["positive_centroid"])
    negative = float(feature @ model["negative_centroid"])
    margin = positive - negative
    prediction = margin >= float(model["threshold"])
    if model["selected_candidate"] == "candidate_b_ncc_and_margin":
        if baseline_score is None:
            raise ValueError("3840 Paused Candidate B requires baseline NCC")
        prediction = prediction and float(baseline_score) >= float(
            model["baseline_threshold"]
        )
    return {
        "positive_similarity": positive,
        "negative_similarity": negative,
        "discrimination_margin": margin,
        "prediction": bool(prediction),
    }


__all__ = [
    "PAUSED_3840_CANDIDATE_NAME",
    "PAUSED_3840_FEATURE_VERSION",
    "PAUSED_3840_MODEL_SHA256",
    "load_paused_3840_model",
    "paused_binary_feature_3840",
    "predict_paused_3840",
]
