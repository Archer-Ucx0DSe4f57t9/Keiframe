"""Frozen native-1920 Malwarfare OCR runtime.

Only production inference lives here. The development candidates, training
code, recordings, annotations, and benchmark reports remain outside KeiFrame.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping

import cv2
import numpy as np

from .ocr_processor import DEFAULT_PROFILE_PATH, MalwarfareOcrResult
from .profile import MalwarfareProfile, load_profile
from .runtime.count import (
    COUNT_RUNTIME_PROFILES,
    CountPresenceThresholds,
    load_frozen_count_model,
    recognize_count_details,
)
from .runtime.time import (
    SLOT_CLASSES,
    presence_passes as time_presence_passes,
    soft_yellow_projection,
    yellow_presence_statistics,
)


BUNDLE_ID_1920 = "malwarfare_native_1920_v1"
CANDIDATE_VERSION_COUNT = "malwarfare_native_1920_count_candidate_v1"
CANDIDATE_VERSION_TIME = "malwarfare_native_1920_time_candidate_v1"
CANDIDATE_VERSION_PAUSED = "malwarfare_native_1920_paused_candidate_v1"
FRAME_SHAPE = (1080, 1920, 3)
COUNT_ROI_SHAPE = (31, 47, 3)
TIME_ROI_SHAPE = (29, 53, 3)
PAUSED_ROI_SHAPE = (32, 53, 3)
DEFAULT_RUNTIME_1920_RESOURCE_DIR = (
    Path(__file__).resolve().parents[3]
    / "resources"
    / "templates"
    / "malwarfare"
    / "runtime_1920_2560"
    / "native_1920_v1"
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not load native-1920 runtime manifest: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"native-1920 runtime manifest must be an object: {path}")
    return value


def _verified_resource(root: Path, relative: str, expected_sha256: str) -> Path:
    path = (root / relative).resolve()
    if root not in path.parents or not path.is_file():
        raise ValueError(f"missing or escaped native-1920 resource: {relative}")
    actual = _sha256_file(path)
    if actual != expected_sha256:
        raise ValueError(
            f"native-1920 resource SHA-256 mismatch: {relative}; "
            f"expected {expected_sha256}, got {actual}"
        )
    return path


def _normalized(vector: np.ndarray) -> np.ndarray:
    result = np.asarray(vector, np.float32).reshape(-1).copy()
    norm = float(np.linalg.norm(result))
    if norm > 1e-8:
        result /= norm
    return np.ascontiguousarray(result, dtype=np.float32)


def _time_feature(
    projection: np.ndarray,
    rect: Mapping[str, int],
    dx: int,
    dy: int,
) -> np.ndarray:
    x, y, width, height = (
        int(rect[key]) for key in ("x", "y", "width", "height")
    )
    crop = projection[y + dy : y + dy + height, x + dx : x + dx + width]
    if crop.shape != (height, width):
        raise ValueError("native-1920 Time slot geometry escaped ROI")
    return _normalized(crop)


def _soft_paused_projection(roi_bgr: np.ndarray) -> np.ndarray:
    if not isinstance(roi_bgr, np.ndarray):
        raise TypeError("native-1920 Paused ROI must be a numpy.ndarray")
    if roi_bgr.dtype != np.uint8 or roi_bgr.shape != PAUSED_ROI_SHAPE:
        raise ValueError(
            "native-1920 Paused ROI must be uint8 BGR shape (32, 53, 3)"
        )
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
        opponent
        * (0.35 + 0.65 * local)
        * (0.35 + 0.65 * brightness),
        dtype=np.float32,
    )


class Malwarfare1920Runtime:
    """Load and cache the three frozen native-1920 recognizers."""

    def __init__(
        self,
        *,
        resource_dir: str | Path = DEFAULT_RUNTIME_1920_RESOURCE_DIR,
        profile_path: str | Path = DEFAULT_PROFILE_PATH,
    ) -> None:
        started = perf_counter()
        self._resource_dir = Path(resource_dir).resolve()
        self.profile: MalwarfareProfile = load_profile(profile_path)
        self._load_count()
        self._load_time()
        self._load_paused()
        self.model_load_ms = (perf_counter() - started) * 1000.0

    @classmethod
    def from_default_resources(
        cls,
        *,
        resource_dir: str | Path = DEFAULT_RUNTIME_1920_RESOURCE_DIR,
        profile_path: str | Path = DEFAULT_PROFILE_PATH,
    ) -> "Malwarfare1920Runtime":
        return cls(resource_dir=resource_dir, profile_path=profile_path)

    def _load_count(self) -> None:
        root = (self._resource_dir / "count").resolve()
        manifest = _read_json(root / "manifest.json")
        if manifest.get("candidate_version") != CANDIDATE_VERSION_COUNT:
            raise ValueError("unexpected native-1920 Count candidate version")
        if manifest.get("resolution") != [1920, 1080]:
            raise ValueError("unexpected native-1920 Count source resolution")
        models = manifest.get("models")
        if not isinstance(models, dict) or set(models) != set(COUNT_RUNTIME_PROFILES):
            raise ValueError("native-1920 Count manifest must define three colors")
        self._count_centroids: dict[str, np.ndarray] = {}
        self._count_thresholds: dict[str, CountPresenceThresholds] = {}
        for color in COUNT_RUNTIME_PROFILES:
            row = models[color]
            path = _verified_resource(root, str(row["filename"]), str(row["sha256"]))
            loaded = load_frozen_count_model(path)
            self._count_centroids[color] = np.asarray(
                loaded["centroids"], dtype=np.float32
            )
            thresholds = row["presence_thresholds_inherited_from_2560"]
            self._count_thresholds[color] = CountPresenceThresholds(
                projection_sum_minimum=float(thresholds["projection_sum_minimum"]),
                best_score_minimum=float(thresholds["best_score_minimum"]),
            )

    def _load_time(self) -> None:
        root = (self._resource_dir / "time").resolve()
        manifest = _read_json(root / "manifest.json")
        if manifest.get("candidate_version") != CANDIDATE_VERSION_TIME:
            raise ValueError("unexpected native-1920 Time candidate version")
        if manifest.get("classifier") != "template_bank_ncc":
            raise ValueError("native-1920 Time runtime requires template_bank_ncc")
        model_row = manifest.get("model")
        if not isinstance(model_row, dict):
            raise ValueError("native-1920 Time model entry is missing")
        model_path = _verified_resource(
            root, str(model_row["filename"]), str(model_row["sha256"])
        )
        with np.load(model_path, allow_pickle=False) as archive:
            if str(archive["candidate_version"].item()) != CANDIDATE_VERSION_TIME:
                raise ValueError("unexpected native-1920 Time model identity")
            if tuple(int(value) for value in archive["roi_shape_hw"]) != (29, 53):
                raise ValueError("unexpected native-1920 Time ROI shape")
            self._time_templates = tuple(
                tuple(
                    np.asarray(
                        archive[f"slot_{slot}_class_{label}_templates"],
                        dtype=np.float32,
                    )
                    for label in classes
                )
                for slot, classes in enumerate(SLOT_CLASSES)
            )
        self._time_rects = tuple(dict(rect) for rect in manifest["slot_rects"])
        self._time_max_shift = int(manifest["max_shift"])
        self._time_presence_thresholds = dict(manifest["presence_thresholds"])
        self._time_slot_score_minimums = tuple(
            float(value) for value in manifest["slot_score_minimums"]
        )

    def _load_paused(self) -> None:
        root = (self._resource_dir / "paused").resolve()
        manifest = _read_json(root / "manifest.json")
        if manifest.get("candidate_version") != CANDIDATE_VERSION_PAUSED:
            raise ValueError("unexpected native-1920 Paused candidate version")
        model_path = _verified_resource(
            root,
            str(manifest["model_filename"]),
            str(manifest["model_sha256"]),
        )
        with np.load(model_path, allow_pickle=False) as archive:
            if str(archive["candidate_version"].item()) != CANDIDATE_VERSION_PAUSED:
                raise ValueError("unexpected native-1920 Paused model identity")
            if tuple(int(value) for value in archive["roi_shape"]) != PAUSED_ROI_SHAPE:
                raise ValueError("unexpected native-1920 Paused ROI shape")
            self._paused_positive = _normalized(archive["positive_centroid"])
            self._paused_negative = _normalized(archive["negative_centroid"])
            self._paused_threshold = float(archive["threshold"].item())
            self._paused_max_shift = int(archive["max_shift"].item())
        if self._paused_max_shift != 0 or not np.isfinite(self._paused_threshold):
            raise ValueError("unexpected native-1920 Paused operating point")

    @staticmethod
    def _validate_frame(frame_bgr: np.ndarray) -> None:
        if not isinstance(frame_bgr, np.ndarray):
            raise TypeError("frame_bgr must be a numpy.ndarray")
        if frame_bgr.dtype != np.uint8 or frame_bgr.shape != FRAME_SHAPE:
            raise ValueError(
                f"native-1920 runtime requires uint8 BGR {FRAME_SHAPE}; "
                f"got {getattr(frame_bgr, 'shape', None)} "
                f"{getattr(frame_bgr, 'dtype', None)}"
            )

    @staticmethod
    def _crop(frame_bgr: np.ndarray, rect) -> np.ndarray:
        return frame_bgr[rect.y : rect.bottom, rect.x : rect.right]

    def recognize_count_details(
        self,
        frame_bgr: np.ndarray,
        *,
        ui_profile: str,
        count_color_profile: str,
    ):
        self._validate_frame(frame_bgr)
        color = str(count_color_profile).lower()
        if color not in self._count_centroids:
            raise ValueError(f"unsupported Count color profile: {count_color_profile}")
        rect = self.profile.resolved_task("count", ui_profile)[1]
        roi = self._crop(frame_bgr, rect)
        if roi.shape != COUNT_ROI_SHAPE:
            raise ValueError("native-1920 Count ROI geometry mismatch")
        return recognize_count_details(
            roi,
            color_profile=color,
            centroids=self._count_centroids[color],
            thresholds=self._count_thresholds[color],
        )

    def recognize_count(
        self,
        frame_bgr: np.ndarray,
        *,
        ui_profile: str,
        count_color_profile: str,
    ) -> int | None:
        return self.recognize_count_details(
            frame_bgr,
            ui_profile=ui_profile,
            count_color_profile=count_color_profile,
        ).value

    def _predict_time(self, roi_bgr: np.ndarray) -> tuple[str, tuple[float, ...]]:
        if roi_bgr.dtype != np.uint8 or roi_bgr.shape != TIME_ROI_SHAPE:
            raise ValueError("native-1920 Time ROI must be uint8 BGR (29, 53, 3)")
        projection = soft_yellow_projection(roi_bgr)
        offsets = tuple(
            (dx, dy)
            for dy in range(-self._time_max_shift, self._time_max_shift + 1)
            for dx in range(-self._time_max_shift, self._time_max_shift + 1)
        )
        digits: list[str] = []
        best_scores: list[float] = []
        for slot, classes in enumerate(SLOT_CLASSES):
            variants = np.asarray(
                [
                    _time_feature(projection, self._time_rects[slot], dx, dy)
                    for dx, dy in offsets
                ],
                dtype=np.float32,
            )
            scores = np.asarray(
                [
                    float(np.max(variants @ bank.T))
                    for bank in self._time_templates[slot]
                ],
                dtype=np.float32,
            )
            best = int(np.argmax(scores))
            digits.append(classes[best])
            best_scores.append(float(scores[best]))
        value = "".join(digits)
        if len(value) != 3 or not value.isascii() or not value.isdigit():
            raise RuntimeError(f"native-1920 Time produced illegal MSS: {value!r}")
        return value, tuple(best_scores)

    def recognize_time(self, roi_bgr: np.ndarray) -> str | None:
        statistics = yellow_presence_statistics(roi_bgr)
        yellow_present = time_presence_passes(
            statistics, self._time_presence_thresholds
        )
        value, scores = self._predict_time(roi_bgr)
        glyph_present = all(
            score >= minimum
            for score, minimum in zip(scores, self._time_slot_score_minimums)
        )
        return value if yellow_present and glyph_present else None

    def recognize_paused(self, roi_bgr: np.ndarray) -> bool:
        feature = _normalized(_soft_paused_projection(roi_bgr))
        score = float(feature @ self._paused_positive) - float(
            feature @ self._paused_negative
        )
        return bool(score >= self._paused_threshold)

    def recognize_time_paused(
        self,
        frame_bgr: np.ndarray,
        *,
        ui_profile: str,
    ) -> tuple[str | None, bool]:
        self._validate_frame(frame_bgr)
        time_rect = self.profile.resolved_task("time", ui_profile)[1]
        time_value = self.recognize_time(self._crop(frame_bgr, time_rect))
        if time_value is not None:
            return time_value, False
        paused_rect = self.profile.resolved_task("paused", ui_profile)[1]
        return None, self.recognize_paused(self._crop(frame_bgr, paused_rect))

    def process(
        self,
        frame_bgr: np.ndarray,
        *,
        ui_profile: str,
        count_color_profile: str,
    ) -> MalwarfareOcrResult:
        count = self.recognize_count(
            frame_bgr,
            ui_profile=ui_profile,
            count_color_profile=count_color_profile,
        )
        time_value, paused = self.recognize_time_paused(
            frame_bgr, ui_profile=ui_profile
        )
        return MalwarfareOcrResult(count=count, time=time_value, paused=paused)


__all__ = [
    "BUNDLE_ID_1920",
    "DEFAULT_RUNTIME_1920_RESOURCE_DIR",
    "Malwarfare1920Runtime",
]
