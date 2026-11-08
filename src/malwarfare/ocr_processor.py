"""Stateless visual OCR for canonical Malwarfare frames.

This module owns no capture, canonicalization, or cross-frame game-state
interpretation.  It accepts only an already canonicalized 1920x1080 BGR
frame, crops the configured canonical ROIs, and runs the frozen recognizers.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import numpy as np

from .runtime.geometry import CANONICAL_HEIGHT, CANONICAL_WIDTH, Rect
from .runtime.count import (
    COUNT_RUNTIME_PROFILES,
    DEFAULT_COUNT_RUNTIME_RESOURCE_DIR,
    CountPresenceRuntimeConfig,
    load_count_presence_runtime_config,
    load_frozen_count_model,
    recognize_count_runtime,
)
from .paused_recognizer import DEFAULT_RESOURCE_DIR as DEFAULT_PAUSED_RESOURCE_DIR
from .paused_recognizer import PausedRecognizer
from .profile import MalwarfareProfile, load_profile
from .runtime.time import (
    DEFAULT_TIME_RUNTIME_RESOURCE_DIR,
    TimeRecognizerModel,
    load_time_recognizer_model,
    load_time_runtime_resource,
    recognize_time,
)


DEFAULT_PROFILE_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "malwarfare_zh.json"
)
CANONICAL_FRAME_SHAPE = (CANONICAL_HEIGHT, CANONICAL_WIDTH, 3)
# Historical patch point retained without importing the former comparison module.
load_frozen_poc_a_shift1 = load_frozen_count_model


@dataclass(frozen=True)
class MalwarfareOcrResult:
    """Stable public result for one canonical Malwarfare frame."""

    count: int | None
    time: str | None
    paused: bool


class MalwarfareOcrProcessor:
    """Cache frozen OCR resources and process canonical Malwarfare frames.

    Use :meth:`from_default_resources` for the portable production bundle.
    The explicit constructor remains available for tests and custom packaging.
    Every model, manifest, and template is loaded and verified only once here.
    """

    def __init__(
        self,
        *,
        count_model_paths: Mapping[str, str | Path],
        time_model_path: str | Path,
        time_model_sha256: str | None = None,
        profile_path: str | Path = DEFAULT_PROFILE_PATH,
        count_resource_dir: str | Path = DEFAULT_COUNT_RUNTIME_RESOURCE_DIR,
        paused_resource_dir: str | Path = DEFAULT_PAUSED_RESOURCE_DIR,
    ) -> None:
        self._profile: MalwarfareProfile = load_profile(profile_path)
        self._count_runtime: CountPresenceRuntimeConfig = (
            load_count_presence_runtime_config(count_resource_dir)
        )
        self._count_centroids = self._load_count_models(count_model_paths)
        self._time_model: TimeRecognizerModel = load_time_recognizer_model(
            time_model_path,
            expected_sha256=time_model_sha256,
        )
        self._paused_recognizer = PausedRecognizer(paused_resource_dir)

    @classmethod
    def from_default_resources(
        cls,
        *,
        profile_path: str | Path = DEFAULT_PROFILE_PATH,
        count_resource_dir: str | Path = DEFAULT_COUNT_RUNTIME_RESOURCE_DIR,
        time_resource_dir: str | Path = DEFAULT_TIME_RUNTIME_RESOURCE_DIR,
        paused_resource_dir: str | Path = DEFAULT_PAUSED_RESOURCE_DIR,
    ) -> "MalwarfareOcrProcessor":
        """Construct from the versioned production resources in the bundle."""

        count_root = Path(count_resource_dir).resolve()
        time_resource = load_time_runtime_resource(time_resource_dir)
        return cls(
            count_model_paths={
                profile: count_root / f"{profile}.npz"
                for profile in COUNT_RUNTIME_PROFILES
            },
            time_model_path=time_resource.model_path,
            time_model_sha256=time_resource.model_sha256,
            profile_path=profile_path,
            count_resource_dir=count_root,
            paused_resource_dir=paused_resource_dir,
        )

    @property
    def profile(self) -> MalwarfareProfile:
        """Expose the shared canonical UI geometry as immutable profile data."""

        return self._profile

    def resolved_rois(self, ui_profile: str) -> dict[str, Rect]:
        return {
            task_id: self._profile.resolved_task(task_id, ui_profile)[1]
            for task_id in ("count", "time", "paused")
        }

    def recognize_count(
        self,
        frame_bgr: np.ndarray,
        *,
        ui_profile: str,
        count_color_profile: str,
    ) -> int | None:
        """Recognize only the Count visual in one canonical BGR frame."""

        self._validate_frame(frame_bgr)
        color_profile = str(count_color_profile).lower()
        try:
            centroids = self._count_centroids[color_profile]
        except KeyError as exc:
            raise ValueError(
                f"unsupported Count color profile: {count_color_profile}"
            ) from exc

        _count_task, count_rect = self._profile.resolved_task("count", ui_profile)
        return recognize_count_runtime(
            self._crop(frame_bgr, count_rect),
            color_profile=color_profile,
            centroids=centroids,
            runtime_config=self._count_runtime,
        )

    def recognize_time_paused(
        self,
        frame_bgr: np.ndarray,
        *,
        ui_profile: str,
    ) -> tuple[str | None, bool]:
        """Recognize mutually exclusive Time and Paused visuals."""

        self._validate_frame(frame_bgr)
        _time_task, time_rect = self._profile.resolved_task("time", ui_profile)
        current_time = recognize_time(
            self._crop(frame_bgr, time_rect), self._time_model
        ).value
        if current_time is not None:
            return current_time, False

        _paused_task, paused_rect = self._profile.resolved_task(
            "paused", ui_profile
        )
        paused = self._paused_recognizer.is_paused_runtime(
            self._crop(frame_bgr, paused_rect)
        )
        return None, paused

    def process(
        self,
        frame_bgr: np.ndarray,
        *,
        ui_profile: str,
        count_color_profile: str,
    ) -> MalwarfareOcrResult:
        """Compose independent visual OCR results without retaining state."""

        count = self.recognize_count(
            frame_bgr,
            ui_profile=ui_profile,
            count_color_profile=count_color_profile,
        )
        time_value, paused = self.recognize_time_paused(
            frame_bgr,
            ui_profile=ui_profile,
        )
        return MalwarfareOcrResult(
            count=count,
            time=time_value,
            paused=paused,
        )

    def _load_count_models(
        self,
        model_paths: Mapping[str, str | Path],
    ) -> dict[str, np.ndarray]:
        if not isinstance(model_paths, Mapping):
            raise TypeError("count_model_paths must be a mapping")
        supplied = set(model_paths)
        expected = set(COUNT_RUNTIME_PROFILES)
        if supplied != expected:
            missing = sorted(expected - supplied)
            unexpected = sorted(supplied - expected)
            raise ValueError(
                "count_model_paths must contain exactly orange, blue, and green; "
                f"missing={missing}, unexpected={unexpected}"
            )

        loaded: dict[str, np.ndarray] = {}
        for color_profile in COUNT_RUNTIME_PROFILES:
            model = load_frozen_poc_a_shift1(model_paths[color_profile])
            expected_hash = self._count_runtime.models[color_profile].sha256
            if model["sha256"] != expected_hash:
                raise ValueError(
                    "frozen Count model SHA-256 mismatch for "
                    f"{color_profile}: expected {expected_hash}, got {model['sha256']}"
                )
            centroids = np.asarray(model["centroids"], dtype=np.float32)
            centroids.setflags(write=False)
            loaded[color_profile] = centroids
        return loaded

    @staticmethod
    def _validate_frame(frame_bgr: np.ndarray) -> None:
        if not isinstance(frame_bgr, np.ndarray):
            raise TypeError("frame_bgr must be a numpy.ndarray")
        if frame_bgr.dtype != np.uint8:
            raise ValueError(
                f"frame_bgr must have dtype uint8, got {frame_bgr.dtype}"
            )
        if frame_bgr.shape != CANONICAL_FRAME_SHAPE:
            raise ValueError(
                "frame_bgr must be an already-canonicalized 1920x1080 BGR frame "
                f"with shape {CANONICAL_FRAME_SHAPE}; got {frame_bgr.shape}"
            )

    @staticmethod
    def _crop(frame_bgr: np.ndarray, rect: Rect) -> np.ndarray:
        return frame_bgr[rect.y : rect.bottom, rect.x : rect.right]


__all__ = [
    "CANONICAL_FRAME_SHAPE",
    "DEFAULT_PROFILE_PATH",
    "MalwarfareOcrProcessor",
    "MalwarfareOcrResult",
]
