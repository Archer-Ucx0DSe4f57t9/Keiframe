"""Portable production runtime for the frozen Malwarfare 3840 OCR bundle."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping

import cv2
import numpy as np

from .ocr_processor import MalwarfareOcrResult
from .paused_recognizer import PausedRecognizer
from .profile import MalwarfareProfile, load_profile
from .runtime.count import (
    COUNT_RUNTIME_PROFILES,
    CountRecognitionResult,
    CountPresenceThresholds,
    load_frozen_count_model,
    recognize_count_details,
)
from .runtime.geometry import CANONICAL_HEIGHT, CANONICAL_WIDTH, Rect
from .runtime.paused_3840 import (
    PAUSED_3840_MODEL_SHA256,
    load_paused_3840_model,
    predict_paused_3840,
)
from .runtime.time_3840 import (
    TIME_3840_MODEL_SHA256,
    TIME_3840_PRESENCE_THRESHOLDS,
    load_time_3840_model,
    predict_time_numeric_3840,
    predict_time_presence_3840,
)


BUNDLE_ID_3840 = "malwarfare_ocr_runtime_zh_3840_v1"
NATIVE_FRAME_SHAPE_3840 = (2160, 3840, 3)
CANONICAL_FRAME_SHAPE = (CANONICAL_HEIGHT, CANONICAL_WIDTH, 3)
SUPPORTED_UI_PROFILE_3840 = "Normal"
DEFAULT_RUNTIME_3840_RESOURCE_DIR = (
    Path(__file__).resolve().parents[2] / "resources" / "malwarfare_3840"
)
EXPECTED_BUNDLE_MANIFEST_SHA256 = (
    "6c336934a992f8767efd7849564fd96934490d5636a625c98de3dbe2a9c2bfd1"
)


@dataclass(frozen=True)
class Malwarfare3840Timings:
    model_load_ms: float
    canonicalization_ms: float
    count_ms: float
    time_ms: float
    paused_ms: float
    total_per_frame_ms: float


@dataclass(frozen=True)
class Malwarfare3840DiagnosticResult:
    count: int | None
    raw_count_prediction: str
    raw_count_present: bool
    raw_count_score: float
    raw_time_presence: bool
    raw_time_prediction: str | None
    raw_time_presence_details: Mapping[str, Any]
    raw_time_numeric_details: Mapping[str, Any] | None
    raw_paused_prediction: bool
    raw_paused_score: float
    raw_paused_baseline_ncc_score: float
    raw_paused_details: Mapping[str, Any]
    time_paused_conflict: bool
    production_time_first_time: str | None
    production_time_first_paused: bool
    runtime_bundle_id: str
    timings: Malwarfare3840Timings


@dataclass(frozen=True)
class Malwarfare3840StatusDiagnosticResult:
    raw_time_presence: bool
    raw_time_prediction: str | None
    raw_time_presence_details: Mapping[str, Any]
    raw_time_numeric_details: Mapping[str, Any] | None
    raw_paused_prediction: bool
    raw_paused_score: float
    raw_paused_baseline_ncc_score: float
    raw_paused_details: Mapping[str, Any]
    time_paused_conflict: bool
    production_time_first_time: str | None
    production_time_first_paused: bool
    time_ms: float
    paused_ms: float


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
        raise ValueError(f"could not read 3840 runtime manifest: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"3840 runtime manifest must be an object: {path}")
    return value


def verify_runtime_bundle_3840(
    resource_dir: str | Path = DEFAULT_RUNTIME_3840_RESOURCE_DIR,
) -> dict[str, Any]:
    """Verify the bundle root manifest and every declared resource hash."""

    resource_root = Path(resource_dir).resolve()
    bundle_root = resource_root.parents[1]
    manifest_path = resource_root / "runtime_bundle_manifest.json"
    actual_manifest_sha256 = _sha256_file(manifest_path)
    if actual_manifest_sha256 != EXPECTED_BUNDLE_MANIFEST_SHA256:
        raise ValueError(
            "3840 runtime bundle manifest SHA-256 mismatch: "
            f"expected {EXPECTED_BUNDLE_MANIFEST_SHA256}, "
            f"got {actual_manifest_sha256}"
        )
    manifest = _read_json(manifest_path)
    expected = {
        "schema_version": 1,
        "bundle_id": BUNDLE_ID_3840,
        "supported_native_resolution": {"width": 3840, "height": 2160},
        "canonical_resolution": {"width": 1920, "height": 1080},
        "ui_profile": SUPPORTED_UI_PROFILE_3840,
        "entrypoint": "src.malwarfare.Malwarfare3840Runtime.from_default_resources",
        "source_candidate_lock_sha256": (
            "2e6ac6feea23a28bf812b3f2a0c9f12fd34c2cbae3a75b8d22f3a5d5eff6a113"
        ),
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise ValueError(f"unexpected 3840 runtime bundle field: {key}")
    if manifest.get("external_dependencies") != ["numpy", "opencv-python"]:
        raise ValueError("unexpected 3840 runtime external dependencies")
    python_files = manifest.get("python_files")
    resource_files = manifest.get("resource_files")
    file_sha256 = manifest.get("resource_file_sha256")
    if not isinstance(python_files, list) or not python_files:
        raise ValueError("3840 runtime python_files must be a non-empty list")
    if not isinstance(resource_files, list) or not resource_files:
        raise ValueError("3840 runtime resource_files must be a non-empty list")
    if not isinstance(file_sha256, dict):
        raise ValueError("3840 runtime resource_file_sha256 is missing")
    manifest_relative = "resources/malwarfare_3840/runtime_bundle_manifest.json"
    if manifest_relative not in resource_files:
        raise ValueError("3840 bundle manifest is not declared as a resource")
    hashed_resources = set(resource_files) - {manifest_relative}
    if set(file_sha256) != hashed_resources:
        raise ValueError("3840 runtime resource hash coverage is incomplete")
    for relative, expected_sha256 in file_sha256.items():
        path = (bundle_root / str(relative)).resolve()
        if not path.is_file() or not path.is_relative_to(bundle_root):
            raise ValueError(f"missing or escaped 3840 runtime resource: {relative}")
        actual_sha256 = _sha256_file(path)
        if actual_sha256 != expected_sha256:
            raise ValueError(
                f"3840 runtime resource SHA-256 mismatch: {relative}; "
                f"expected {expected_sha256}, got {actual_sha256}"
            )
    for relative in python_files:
        path = (bundle_root / str(relative)).resolve()
        if not path.is_file() or not path.is_relative_to(bundle_root):
            raise ValueError(f"missing or escaped 3840 runtime Python file: {relative}")
    return {
        "bundle_id": BUNDLE_ID_3840,
        "manifest_sha256": actual_manifest_sha256,
        "python_file_count": len(python_files),
        "resource_file_count": len(resource_files),
        "verified": True,
    }


class Malwarfare3840Runtime:
    """Load the frozen models once and recognize native 3840x2160 BGR frames."""

    def __init__(
        self,
        *,
        resource_dir: str | Path,
        verify_bundle: bool = True,
    ) -> None:
        started = perf_counter()
        self._resource_dir = Path(resource_dir).resolve()
        if verify_bundle:
            verify_runtime_bundle_3840(self._resource_dir)
        self._profile: MalwarfareProfile = load_profile(
            self._resource_dir / "profile.json"
        )
        self._count_thresholds, self._count_centroids = self._load_count()
        self._time_model = self._load_time()
        self._paused_model, self._paused_baseline = self._load_paused()
        self._model_load_ms = (perf_counter() - started) * 1000.0

    @classmethod
    def from_default_resources(
        cls,
        *,
        resource_dir: str | Path = DEFAULT_RUNTIME_3840_RESOURCE_DIR,
    ) -> "Malwarfare3840Runtime":
        return cls(resource_dir=resource_dir, verify_bundle=True)

    @property
    def bundle_id(self) -> str:
        return BUNDLE_ID_3840

    @property
    def model_load_ms(self) -> float:
        return self._model_load_ms

    @staticmethod
    def canonicalize(frame_bgr: np.ndarray) -> np.ndarray:
        if not isinstance(frame_bgr, np.ndarray):
            raise TypeError("frame_bgr must be a numpy.ndarray")
        if frame_bgr.dtype != np.uint8:
            raise ValueError(f"frame_bgr must have dtype uint8, got {frame_bgr.dtype}")
        if frame_bgr.shape != NATIVE_FRAME_SHAPE_3840:
            raise ValueError(
                "Malwarfare3840Runtime accepts only native 3840x2160 BGR frames "
                f"with shape {NATIVE_FRAME_SHAPE_3840}; got {frame_bgr.shape}"
            )
        canonical = cv2.resize(
            frame_bgr,
            (CANONICAL_WIDTH, CANONICAL_HEIGHT),
            interpolation=cv2.INTER_AREA,
        )
        if canonical.shape != CANONICAL_FRAME_SHAPE or canonical.dtype != np.uint8:
            raise RuntimeError("3840 native-to-canonical conversion violated contract")
        return canonical

    def resolved_rois(self, ui_profile: str) -> dict[str, Rect]:
        if ui_profile != SUPPORTED_UI_PROFILE_3840:
            raise ValueError(
                "3840 runtime supports only verified UI profile "
                f"{SUPPORTED_UI_PROFILE_3840!r}; got {ui_profile!r}"
            )
        return {
            task: self._profile.resolved_task(task, ui_profile)[1]
            for task in ("count", "time", "paused")
        }

    @staticmethod
    def _validate_canonical(frame_bgr: np.ndarray) -> None:
        if not isinstance(frame_bgr, np.ndarray):
            raise TypeError("canonical_frame_bgr must be a numpy.ndarray")
        if frame_bgr.dtype != np.uint8:
            raise ValueError(
                "canonical_frame_bgr must have dtype uint8, "
                f"got {frame_bgr.dtype}"
            )
        if frame_bgr.shape != CANONICAL_FRAME_SHAPE:
            raise ValueError(
                "canonical_frame_bgr must be 1920x1080 BGR with shape "
                f"{CANONICAL_FRAME_SHAPE}; got {frame_bgr.shape}"
            )

    def _validate_adapted_rois(self, rois: Mapping[str, Rect]) -> dict[str, Rect]:
        if not isinstance(rois, Mapping) or set(rois) != {
            "count",
            "time",
            "paused",
        }:
            raise ValueError("adapted ROIs must contain count, time, and paused")
        normal = self.resolved_rois(SUPPORTED_UI_PROFILE_3840)
        validated: dict[str, Rect] = {}
        for task_id, expected in normal.items():
            rect = rois[task_id]
            if not isinstance(rect, Rect):
                raise TypeError(f"adapted {task_id} ROI must be a Rect")
            if (rect.width, rect.height) != (expected.width, expected.height):
                raise ValueError(
                    f"adapted {task_id} ROI must keep frozen size "
                    f"{expected.width}x{expected.height}; got "
                    f"{rect.width}x{rect.height}"
                )
            if rect.right > CANONICAL_WIDTH or rect.bottom > CANONICAL_HEIGHT:
                raise ValueError(f"adapted {task_id} ROI is outside canonical frame")
            validated[task_id] = rect
        return validated

    @staticmethod
    def _crop(frame_bgr: np.ndarray, rect: Rect) -> np.ndarray:
        return frame_bgr[rect.y : rect.bottom, rect.x : rect.right]

    def recognize_count_canonical_details(
        self,
        canonical_frame_bgr: np.ndarray,
        *,
        count_rect: Rect,
        count_color_profile: str,
    ) -> CountRecognitionResult:
        """Run frozen Count inference on one geometry-adapted canonical ROI."""

        self._validate_canonical(canonical_frame_bgr)
        normal_count = self.resolved_rois(SUPPORTED_UI_PROFILE_3840)["count"]
        if not isinstance(count_rect, Rect):
            raise TypeError("count_rect must be a Rect")
        if (count_rect.width, count_rect.height) != (
            normal_count.width,
            normal_count.height,
        ):
            raise ValueError(
                "adapted count ROI must preserve the frozen Count ROI size"
            )
        if count_rect.right > CANONICAL_WIDTH or count_rect.bottom > CANONICAL_HEIGHT:
            raise ValueError("adapted count ROI is outside canonical frame")
        color = str(count_color_profile).lower()
        if color not in self._count_centroids:
            raise ValueError(f"unsupported Count color profile: {count_color_profile}")
        return recognize_count_details(
            self._crop(canonical_frame_bgr, count_rect),
            color_profile=color,
            centroids=self._count_centroids[color],
            thresholds=self._count_thresholds[color],
        )

    def recognize_status_canonical_diagnostic(
        self,
        canonical_frame_bgr: np.ndarray,
        *,
        time_rect: Rect,
        paused_rect: Rect,
    ) -> Malwarfare3840StatusDiagnosticResult:
        """Run frozen Time-first/Paused inference on adapted canonical ROIs."""

        self._validate_canonical(canonical_frame_bgr)
        normal = self.resolved_rois(SUPPORTED_UI_PROFILE_3840)
        for task_id, rect in (("time", time_rect), ("paused", paused_rect)):
            expected = normal[task_id]
            if not isinstance(rect, Rect):
                raise TypeError(f"{task_id}_rect must be a Rect")
            if (rect.width, rect.height) != (expected.width, expected.height):
                raise ValueError(
                    f"adapted {task_id} ROI must preserve frozen ROI size"
                )
            if rect.right > CANONICAL_WIDTH or rect.bottom > CANONICAL_HEIGHT:
                raise ValueError(f"adapted {task_id} ROI is outside canonical frame")

        stage = perf_counter()
        time_roi = self._crop(canonical_frame_bgr, time_rect)
        presence = predict_time_presence_3840(time_roi)
        numeric = (
            predict_time_numeric_3840(time_roi, self._time_model)
            if bool(presence["present"])
            else None
        )
        time_ms = (perf_counter() - stage) * 1000.0

        stage = perf_counter()
        paused_roi = self._crop(canonical_frame_bgr, paused_rect)
        baseline = self._paused_baseline.score_details(paused_roi)
        paused = predict_paused_3840(
            self._paused_model,
            paused_roi,
            baseline_score=baseline.score,
        )
        paused_ms = (perf_counter() - stage) * 1000.0

        time_present = bool(presence["present"])
        paused_prediction = bool(paused["prediction"])
        raw_time = None if numeric is None else str(numeric["value"])
        return Malwarfare3840StatusDiagnosticResult(
            raw_time_presence=time_present,
            raw_time_prediction=raw_time,
            raw_time_presence_details=dict(presence),
            raw_time_numeric_details=None if numeric is None else dict(numeric),
            raw_paused_prediction=paused_prediction,
            raw_paused_score=float(paused["discrimination_margin"]),
            raw_paused_baseline_ncc_score=float(baseline.score),
            raw_paused_details={
                **dict(paused),
                "baseline_best_template": baseline.best_template,
                "baseline_ncc_score": float(baseline.score),
            },
            time_paused_conflict=time_present and paused_prediction,
            production_time_first_time=raw_time if time_present else None,
            production_time_first_paused=(
                False if time_present else paused_prediction
            ),
            time_ms=time_ms,
            paused_ms=paused_ms,
        )

    def process_canonical_diagnostic(
        self,
        canonical_frame_bgr: np.ndarray,
        *,
        rois: Mapping[str, Rect],
        count_color_profile: str,
    ) -> Malwarfare3840DiagnosticResult:
        """Apply frozen inference to shared-profile canonical ROI geometry."""

        total_started = perf_counter()
        self._validate_canonical(canonical_frame_bgr)
        resolved = self._validate_adapted_rois(rois)

        stage = perf_counter()
        count = self.recognize_count_canonical_details(
            canonical_frame_bgr,
            count_rect=resolved["count"],
            count_color_profile=count_color_profile,
        )
        count_ms = (perf_counter() - stage) * 1000.0
        status = self.recognize_status_canonical_diagnostic(
            canonical_frame_bgr,
            time_rect=resolved["time"],
            paused_rect=resolved["paused"],
        )
        return Malwarfare3840DiagnosticResult(
            count=count.value,
            raw_count_prediction=count.raw_prediction,
            raw_count_present=count.present,
            raw_count_score=count.best_score,
            raw_time_presence=status.raw_time_presence,
            raw_time_prediction=status.raw_time_prediction,
            raw_time_presence_details=status.raw_time_presence_details,
            raw_time_numeric_details=status.raw_time_numeric_details,
            raw_paused_prediction=status.raw_paused_prediction,
            raw_paused_score=status.raw_paused_score,
            raw_paused_baseline_ncc_score=(
                status.raw_paused_baseline_ncc_score
            ),
            raw_paused_details=status.raw_paused_details,
            time_paused_conflict=status.time_paused_conflict,
            production_time_first_time=status.production_time_first_time,
            production_time_first_paused=status.production_time_first_paused,
            runtime_bundle_id=BUNDLE_ID_3840,
            timings=Malwarfare3840Timings(
                model_load_ms=self._model_load_ms,
                canonicalization_ms=0.0,
                count_ms=count_ms,
                time_ms=status.time_ms,
                paused_ms=status.paused_ms,
                total_per_frame_ms=(perf_counter() - total_started) * 1000.0,
            ),
        )

    def process_canonical(
        self,
        canonical_frame_bgr: np.ndarray,
        *,
        rois: Mapping[str, Rect],
        count_color_profile: str,
    ) -> MalwarfareOcrResult:
        diagnostic = self.process_canonical_diagnostic(
            canonical_frame_bgr,
            rois=rois,
            count_color_profile=count_color_profile,
        )
        return MalwarfareOcrResult(
            count=diagnostic.count,
            time=diagnostic.production_time_first_time,
            paused=diagnostic.production_time_first_paused,
        )

    def process_diagnostic(
        self,
        frame_bgr: np.ndarray,
        *,
        ui_profile: str,
        count_color_profile: str,
    ) -> Malwarfare3840DiagnosticResult:
        total_started = perf_counter()
        stage = perf_counter()
        canonical = self.canonicalize(frame_bgr)
        canonicalization_ms = (perf_counter() - stage) * 1000.0
        rois = self.resolved_rois(ui_profile)
        result = self.process_canonical_diagnostic(
            canonical,
            rois=rois,
            count_color_profile=count_color_profile,
        )
        return replace(
            result,
            timings=replace(
                result.timings,
                canonicalization_ms=canonicalization_ms,
                total_per_frame_ms=(perf_counter() - total_started) * 1000.0,
            ),
        )

    def process(
        self,
        frame_bgr: np.ndarray,
        *,
        ui_profile: str,
        count_color_profile: str,
    ) -> MalwarfareOcrResult:
        diagnostic = self.process_diagnostic(
            frame_bgr,
            ui_profile=ui_profile,
            count_color_profile=count_color_profile,
        )
        return MalwarfareOcrResult(
            count=diagnostic.count,
            time=diagnostic.production_time_first_time,
            paused=diagnostic.production_time_first_paused,
        )

    def _load_count(
        self,
    ) -> tuple[dict[str, CountPresenceThresholds], dict[str, np.ndarray]]:
        manifest = _read_json(self._resource_dir / "count" / "manifest.json")
        if manifest.get("candidate_version") != "malwarfare_zh_3840_candidate_v1":
            raise ValueError("unexpected 3840 Count candidate identity")
        raw_thresholds = manifest.get("thresholds")
        raw_models = manifest.get("models")
        if not isinstance(raw_thresholds, dict) or set(raw_thresholds) != set(
            COUNT_RUNTIME_PROFILES
        ):
            raise ValueError("3840 Count thresholds are incomplete")
        if not isinstance(raw_models, dict) or set(raw_models) != set(
            COUNT_RUNTIME_PROFILES
        ):
            raise ValueError("3840 Count models are incomplete")
        thresholds: dict[str, CountPresenceThresholds] = {}
        centroids: dict[str, np.ndarray] = {}
        for color in COUNT_RUNTIME_PROFILES:
            threshold = raw_thresholds[color]
            model_entry = raw_models[color]
            if not isinstance(threshold, dict) or not isinstance(model_entry, dict):
                raise ValueError(f"invalid 3840 Count manifest entry: {color}")
            thresholds[color] = CountPresenceThresholds(
                projection_sum_minimum=threshold.get("projection_sum_minimum"),
                best_score_minimum=threshold.get("best_score_minimum"),
            )
            model = load_frozen_count_model(
                self._resource_dir / "count" / str(model_entry.get("filename"))
            )
            if model["sha256"] != model_entry.get("sha256"):
                raise ValueError(f"3840 Count model SHA-256 mismatch: {color}")
            value = np.asarray(model["centroids"], dtype=np.float32)
            value.setflags(write=False)
            centroids[color] = value
        return thresholds, centroids

    def _load_time(self):
        manifest = _read_json(self._resource_dir / "time" / "manifest.json")
        if manifest.get("candidate_version") != "malwarfare_zh_3840_candidate_v4":
            raise ValueError("unexpected 3840 Time candidate identity")
        if manifest.get("presence_thresholds") != TIME_3840_PRESENCE_THRESHOLDS:
            raise ValueError("3840 Time presence thresholds changed")
        model = manifest.get("model")
        if not isinstance(model, dict) or model.get("sha256") != TIME_3840_MODEL_SHA256:
            raise ValueError("invalid 3840 Time model manifest entry")
        return load_time_3840_model(
            self._resource_dir / "time" / str(model.get("filename")),
            expected_sha256=TIME_3840_MODEL_SHA256,
        )

    def _load_paused(self):
        manifest = _read_json(self._resource_dir / "paused" / "manifest.json")
        if manifest.get("candidate_version") != "malwarfare_zh_3840_candidate_v2":
            raise ValueError("unexpected 3840 Paused candidate identity")
        model = manifest.get("model")
        if not isinstance(model, dict) or model.get("sha256") != PAUSED_3840_MODEL_SHA256:
            raise ValueError("invalid 3840 Paused model manifest entry")
        paused_model = load_paused_3840_model(
            self._resource_dir / "paused" / str(model.get("filename")),
            expected_sha256=PAUSED_3840_MODEL_SHA256,
        )
        baseline = PausedRecognizer(self._resource_dir / "paused" / "baseline")
        return paused_model, baseline


__all__ = [
    "BUNDLE_ID_3840",
    "CANONICAL_FRAME_SHAPE",
    "DEFAULT_RUNTIME_3840_RESOURCE_DIR",
    "Malwarfare3840DiagnosticResult",
    "Malwarfare3840Runtime",
    "Malwarfare3840StatusDiagnosticResult",
    "Malwarfare3840Timings",
    "NATIVE_FRAME_SHAPE_3840",
    "SUPPORTED_UI_PROFILE_3840",
    "verify_runtime_bundle_3840",
]
