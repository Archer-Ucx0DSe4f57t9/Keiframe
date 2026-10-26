"""Frozen 2560-source Chinese Malwarfare Paused production candidate.

The recognizer accepts only an already-cropped canonical 53x32 BGR uint8
Paused ROI.  It deliberately owns neither UI-offset discovery nor a
standalone processing flow.  Its production operating point is loaded from
the frozen resource manifest.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np


CANDIDATE = "legacy_template"
CANDIDATE_VERSION = "paused_zh_2560_v1"
PREPROCESSING_VERSION = "legacy_yellow_v1"
ROI_SHAPE = (32, 53, 3)
DEFAULT_RESOURCE_DIR = (
    Path(__file__).resolve().parents[2]
    / "resources"
    / "malwarfare"
    / CANDIDATE_VERSION
)


@dataclass(frozen=True)
class PausedScore:
    """Raw frozen-candidate result for one canonical Paused ROI."""

    score: float
    best_template: str


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_roi(roi_bgr: np.ndarray) -> None:
    if not isinstance(roi_bgr, np.ndarray):
        raise TypeError("Paused ROI must be a numpy.ndarray")
    if roi_bgr.dtype != np.uint8:
        raise ValueError(f"Paused ROI dtype must be uint8, got {roi_bgr.dtype}")
    if roi_bgr.shape != ROI_SHAPE:
        raise ValueError(
            "Paused ROI must have shape (32, 53, 3) in BGR channel order; "
            f"got {roi_bgr.shape}"
        )


def preprocess_paused_roi(roi_bgr: np.ndarray) -> np.ndarray:
    """Apply the frozen legacy-yellow preprocessing without resizing input in place."""

    _validate_roi(roi_bgr)
    resized = cv2.resize(roi_bgr, (53 * 4, 32 * 4), interpolation=cv2.INTER_CUBIC)
    hsv = cv2.cvtColor(resized, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([21, 50, 50]), np.array([35, 255, 255]))
    value = hsv[:, :, 2]
    gray = cv2.bitwise_and(value, value, mask=mask)
    if cv2.countNonZero(mask) > 0:
        gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
    _threshold, binary = cv2.threshold(gray, 110, 255, cv2.THRESH_BINARY)
    return np.ascontiguousarray(binary, dtype=np.uint8)


class PausedRecognizer:
    """Score canonical Paused ROIs against exactly two frozen templates."""

    def __init__(self, resource_dir: str | Path = DEFAULT_RESOURCE_DIR) -> None:
        self._resource_dir = Path(resource_dir).resolve()
        manifest_path = self._resource_dir / "manifest.json"
        try:
            manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"could not load frozen Paused manifest: {manifest_path}") from exc
        self._validate_manifest(manifest)

        templates: list[tuple[str, np.ndarray]] = []
        for entry in manifest["templates"]:
            filename = str(entry["filename"])
            path = self._resource_dir / filename
            if path.parent != self._resource_dir:
                raise ValueError(f"template must be directly inside frozen resource directory: {filename}")
            actual_hash = _sha256_file(path)
            if actual_hash != entry["sha256"]:
                raise ValueError(f"frozen Paused template SHA-256 mismatch: {filename}")
            try:
                encoded = np.fromfile(path, dtype=np.uint8)
            except OSError as exc:
                raise ValueError(f"could not read frozen Paused template: {filename}") from exc
            template = cv2.imdecode(encoded, cv2.IMREAD_GRAYSCALE)
            if template is None or template.dtype != np.uint8 or template.ndim != 2:
                raise ValueError(f"invalid frozen Paused grayscale template: {filename}")
            template.setflags(write=False)
            templates.append((filename, template))
        self._templates = tuple(templates)
        self._manifest = manifest
        self._production_threshold = float(manifest["production_threshold"])

    @staticmethod
    def _validate_manifest(manifest: dict[str, Any]) -> None:
        expected = {
            "task": "paused",
            "language": "zh",
            "source_resolution_profile": "native_2560_to_canonical_1920",
            "canonical_roi_width": 53,
            "canonical_roi_height": 32,
            "candidate": CANDIDATE,
            "candidate_version": CANDIDATE_VERSION,
            "validation_status": "frozen_after_within_recording_temporal_holdout_validation",
            "validation_type": "locked-candidate temporal holdout validation",
            "independent_recording_validation": False,
        }
        for key, value in expected.items():
            if manifest.get(key) != value:
                raise ValueError(f"unexpected frozen Paused manifest field: {key}")
        threshold = manifest.get("production_threshold")
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
            raise ValueError("frozen Paused production threshold must be a finite real number")
        if not np.isfinite(float(threshold)):
            raise ValueError("frozen Paused production threshold must be finite")
        preprocessing = manifest.get("preprocessing", {})
        expected_preprocessing = {
            "version": PREPROCESSING_VERSION,
            "resize_scale": 4,
            "interpolation": "INTER_CUBIC",
            "color_space": "HSV",
            "h_min": 21,
            "h_max": 35,
            "s_min": 50,
            "v_min": 50,
            "normalization": "NORM_MINMAX_0_255_when_yellow_mask_nonempty",
            "binary_threshold": 110,
            "matcher": "TM_CCOEFF_NORMED",
            "aggregation": "max",
        }
        if not isinstance(preprocessing, dict) or any(
            preprocessing.get(key) != value
            for key, value in expected_preprocessing.items()
        ):
            raise ValueError("unexpected frozen Paused preprocessing contract")
        templates = manifest.get("templates")
        if not isinstance(templates, list) or len(templates) != 2:
            raise ValueError("frozen Paused manifest must name exactly two templates")
        filenames = [entry.get("filename") for entry in templates if isinstance(entry, dict)]
        if filenames != ["paused_v01_yellow.png", "paused_v02_white.png"]:
            raise ValueError("unexpected frozen Paused template order or filenames")
        if any(not isinstance(entry.get("sha256"), str) for entry in templates):
            raise ValueError("frozen Paused template hash is missing")

    @property
    def manifest(self) -> dict[str, Any]:
        """Return a detached copy of the validated frozen manifest."""

        return json.loads(json.dumps(self._manifest))

    @property
    def production_threshold(self) -> float:
        """Return the production threshold loaded from the frozen manifest."""

        return self._production_threshold

    def score_details(self, roi_bgr: np.ndarray) -> PausedScore:
        """Return raw maximum NCC and its deterministic best template."""

        processed = preprocess_paused_roi(roi_bgr)
        best_score = -np.inf
        best_template = ""
        for filename, template in self._templates:
            if template.shape[0] > processed.shape[0] or template.shape[1] > processed.shape[1]:
                raise ValueError(f"frozen template is larger than preprocessed ROI: {filename}")
            response = cv2.matchTemplate(processed, template, cv2.TM_CCOEFF_NORMED)
            score = float(response.max())
            if not np.isfinite(score):
                raise ValueError(f"non-finite Paused NCC score from template: {filename}")
            if score > best_score:
                best_score = score
                best_template = filename
        return PausedScore(score=float(best_score), best_template=best_template)

    def score(self, roi_bgr: np.ndarray) -> float:
        """Return the raw maximum NCC score across the frozen template family."""

        return self.score_details(roi_bgr).score

    def is_paused(self, roi_bgr: np.ndarray, *, threshold: float) -> bool:
        """Classify with an explicit threshold for analysis or testing."""

        if isinstance(threshold, bool) or not isinstance(threshold, (int, float, np.number)):
            raise TypeError("threshold must be a finite real number")
        value = float(threshold)
        if not np.isfinite(value):
            raise ValueError("threshold must be finite")
        return self.score(roi_bgr) >= value

    def is_paused_runtime(self, roi_bgr: np.ndarray) -> bool:
        """Classify with the production threshold from the frozen manifest."""

        return self.is_paused(roi_bgr, threshold=self.production_threshold)


__all__ = [
    "CANDIDATE",
    "CANDIDATE_VERSION",
    "DEFAULT_RESOURCE_DIR",
    "PREPROCESSING_VERSION",
    "PausedRecognizer",
    "PausedScore",
    "preprocess_paused_roi",
]
