"""Cached native-resolution router for Malwarfare 1920/2560/3840 OCR."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Mapping

import cv2
import numpy as np

from .ocr_processor import MalwarfareOcrProcessor, MalwarfareOcrResult
from .runtime.geometry import CANONICAL_HEIGHT, CANONICAL_WIDTH, Rect
from .runtime_1920 import (
    BUNDLE_ID_1920,
    DEFAULT_RUNTIME_1920_RESOURCE_DIR,
    Malwarfare1920Runtime,
)
from .runtime_3840 import (
    BUNDLE_ID_3840,
    DEFAULT_RUNTIME_3840_RESOURCE_DIR,
    Malwarfare3840Runtime,
)


BUNDLE_ID_2560 = "malwarfare_ocr_runtime_zh_2560_v1"
SUPPORTED_MODEL_WIDTHS = (1920, 2560, 3840)
NATIVE_FRAME_SHAPE_1920 = (1080, 1920, 3)
NATIVE_FRAME_SHAPE_2560 = (1440, 2560, 3)
NATIVE_FRAME_SHAPE_3840 = (2160, 3840, 3)


class MalwarfareRuntimeRouter:
    """Select one cached runtime from the SC2 client width."""

    def __init__(
        self,
        *,
        runtime_2560: MalwarfareOcrProcessor,
        runtime_1920: Malwarfare1920Runtime | None = None,
        runtime_3840: Malwarfare3840Runtime | None = None,
        model_load_ms_1920: float | None = None,
        model_load_ms_2560: float = 0.0,
        model_load_ms_3840: float | None = None,
    ) -> None:
        self._runtime_1920 = runtime_1920
        self._runtime_2560 = runtime_2560
        self._runtime_3840 = runtime_3840
        runtime_1920_load = getattr(runtime_1920, "model_load_ms", 0.0)
        runtime_3840_load = getattr(runtime_3840, "model_load_ms", 0.0)
        self._model_load_ms_1920 = (
            0.0
            if runtime_1920 is None
            else float(model_load_ms_1920)
            if model_load_ms_1920 is not None
            else float(runtime_1920_load)
            if isinstance(runtime_1920_load, (int, float))
            else 0.0
        )
        self._model_load_ms_2560 = float(model_load_ms_2560)
        self._model_load_ms_3840 = (
            0.0
            if runtime_3840 is None
            else float(model_load_ms_3840)
            if model_load_ms_3840 is not None
            else float(runtime_3840_load)
            if isinstance(runtime_3840_load, (int, float))
            else 0.0
        )
        self._last_runtime_bundle_id: str | None = None

    @classmethod
    def from_default_resources(
        cls,
        *,
        runtime_2560: MalwarfareOcrProcessor | None = None,
        resource_dir_1920: str | Path = DEFAULT_RUNTIME_1920_RESOURCE_DIR,
        resource_dir_3840: str | Path = DEFAULT_RUNTIME_3840_RESOURCE_DIR,
    ) -> "MalwarfareRuntimeRouter":
        load_2560 = 0.0
        if runtime_2560 is None:
            started = perf_counter()
            runtime_2560 = MalwarfareOcrProcessor.from_default_resources()
            load_2560 = (perf_counter() - started) * 1000.0
        runtime_1920 = Malwarfare1920Runtime.from_default_resources(
            resource_dir=resource_dir_1920
        )
        runtime_3840 = Malwarfare3840Runtime.from_default_resources(
            resource_dir=resource_dir_3840
        )
        return cls(
            runtime_1920=runtime_1920,
            runtime_2560=runtime_2560,
            runtime_3840=runtime_3840,
            model_load_ms_2560=load_2560,
        )

    @property
    def last_runtime_bundle_id(self) -> str | None:
        return self._last_runtime_bundle_id

    @property
    def model_load_ms(self) -> dict[str, float]:
        return {
            BUNDLE_ID_1920: self._model_load_ms_1920,
            BUNDLE_ID_2560: self._model_load_ms_2560,
            BUNDLE_ID_3840: self._model_load_ms_3840,
        }

    @staticmethod
    def select_model_width(client_width: int) -> int:
        if isinstance(client_width, bool) or not isinstance(client_width, int):
            raise TypeError("client_width must be an integer")
        if client_width <= 0:
            raise ValueError("client_width must be positive")
        return min(
            SUPPORTED_MODEL_WIDTHS,
            key=lambda width: (abs(width - client_width), width),
        )

    def runtime_for_width(self, model_width: int):
        if model_width == 1920:
            runtime = self._runtime_1920
        elif model_width == 2560:
            runtime = self._runtime_2560
        elif model_width == 3840:
            runtime = self._runtime_3840
        else:
            raise ValueError(f"unsupported Malwarfare model width: {model_width}")
        if runtime is None:
            raise RuntimeError(f"Malwarfare {model_width} Runtime is not loaded")
        return runtime

    @staticmethod
    def runtime_bundle_id_for_shape(shape: tuple[int, ...]) -> str:
        if tuple(shape) == NATIVE_FRAME_SHAPE_1920:
            return BUNDLE_ID_1920
        if tuple(shape) == NATIVE_FRAME_SHAPE_2560:
            return BUNDLE_ID_2560
        if tuple(shape) == NATIVE_FRAME_SHAPE_3840:
            return BUNDLE_ID_3840
        raise ValueError(
            "unsupported native Malwarfare frame shape; expected "
            f"{NATIVE_FRAME_SHAPE_1920}, {NATIVE_FRAME_SHAPE_2560}, or "
            f"{NATIVE_FRAME_SHAPE_3840}, got {shape}"
        )

    @staticmethod
    def canonicalize_1920(frame_bgr: np.ndarray) -> np.ndarray:
        if not isinstance(frame_bgr, np.ndarray):
            raise TypeError("frame_bgr must be a numpy.ndarray")
        if frame_bgr.dtype != np.uint8 or frame_bgr.shape != NATIVE_FRAME_SHAPE_1920:
            raise ValueError(
                "1920 runtime accepts only native 1920x1080 uint8 BGR frames; "
                f"got {getattr(frame_bgr, 'shape', None)} "
                f"{getattr(frame_bgr, 'dtype', None)}"
            )
        return frame_bgr

    @staticmethod
    def canonicalize_2560(frame_bgr: np.ndarray) -> np.ndarray:
        if not isinstance(frame_bgr, np.ndarray):
            raise TypeError("frame_bgr must be a numpy.ndarray")
        if frame_bgr.dtype != np.uint8:
            raise ValueError(f"frame_bgr must have dtype uint8, got {frame_bgr.dtype}")
        if frame_bgr.shape != NATIVE_FRAME_SHAPE_2560:
            raise ValueError(
                "2560 runtime accepts only native 2560x1440 BGR frames; "
                f"got {frame_bgr.shape}"
            )
        return cv2.resize(
            frame_bgr,
            (CANONICAL_WIDTH, CANONICAL_HEIGHT),
            interpolation=cv2.INTER_AREA,
        )

    def process(
        self,
        native_frame_bgr: np.ndarray,
        *,
        ui_profile: str,
        count_color_profile: str,
    ) -> MalwarfareOcrResult:
        if not isinstance(native_frame_bgr, np.ndarray):
            raise TypeError("native_frame_bgr must be a numpy.ndarray")
        bundle_id = self.runtime_bundle_id_for_shape(native_frame_bgr.shape)
        if bundle_id == BUNDLE_ID_1920:
            result = self.runtime_for_width(1920).process(
                self.canonicalize_1920(native_frame_bgr),
                ui_profile=ui_profile,
                count_color_profile=count_color_profile,
            )
        elif bundle_id == BUNDLE_ID_2560:
            canonical = self.canonicalize_2560(native_frame_bgr)
            result = self.runtime_for_width(2560).process(
                canonical,
                ui_profile=ui_profile,
                count_color_profile=count_color_profile,
            )
        else:
            result = self.runtime_for_width(3840).process(
                native_frame_bgr,
                ui_profile=ui_profile,
                count_color_profile=count_color_profile,
            )
        self._last_runtime_bundle_id = bundle_id
        return result

    def process_diagnostic(
        self,
        native_frame_bgr: np.ndarray,
        *,
        ui_profile: str,
        count_color_profile: str,
    ):
        """Expose the frozen 3840 runtime's read-only inference diagnostics."""

        if not isinstance(native_frame_bgr, np.ndarray):
            raise TypeError("native_frame_bgr must be a numpy.ndarray")
        bundle_id = self.runtime_bundle_id_for_shape(native_frame_bgr.shape)
        if bundle_id != BUNDLE_ID_3840:
            raise ValueError(
                "diagnostic inference is available only for native 3840 frames"
            )
        result = self.runtime_for_width(3840).process_diagnostic(
            native_frame_bgr,
            ui_profile=ui_profile,
            count_color_profile=count_color_profile,
        )
        self._last_runtime_bundle_id = bundle_id
        return result

    def process_canonical_3840(
        self,
        canonical_frame_bgr: np.ndarray,
        *,
        rois: Mapping[str, Rect],
        count_color_profile: str,
    ) -> MalwarfareOcrResult:
        """Run 3840 models on shared-profile canonical geometry."""

        result = self.runtime_for_width(3840).process_canonical(
            canonical_frame_bgr,
            rois=rois,
            count_color_profile=count_color_profile,
        )
        self._last_runtime_bundle_id = BUNDLE_ID_3840
        return result

    def process_canonical_3840_diagnostic(
        self,
        canonical_frame_bgr: np.ndarray,
        *,
        rois: Mapping[str, Rect],
        count_color_profile: str,
    ):
        result = self.runtime_for_width(3840).process_canonical_diagnostic(
            canonical_frame_bgr,
            rois=rois,
            count_color_profile=count_color_profile,
        )
        self._last_runtime_bundle_id = BUNDLE_ID_3840
        return result

    def recognize_count_canonical_3840(
        self,
        canonical_frame_bgr: np.ndarray,
        *,
        count_rect: Rect,
        count_color_profile: str,
    ):
        result = self.runtime_for_width(3840).recognize_count_canonical_details(
            canonical_frame_bgr,
            count_rect=count_rect,
            count_color_profile=count_color_profile,
        )
        self._last_runtime_bundle_id = BUNDLE_ID_3840
        return result

    def recognize_status_canonical_3840(
        self,
        canonical_frame_bgr: np.ndarray,
        *,
        time_rect: Rect,
        paused_rect: Rect,
    ):
        result = self.runtime_for_width(3840).recognize_status_canonical_diagnostic(
            canonical_frame_bgr,
            time_rect=time_rect,
            paused_rect=paused_rect,
        )
        self._last_runtime_bundle_id = BUNDLE_ID_3840
        return result


__all__ = [
    "BUNDLE_ID_1920",
    "BUNDLE_ID_2560",
    "MalwarfareRuntimeRouter",
    "NATIVE_FRAME_SHAPE_1920",
    "NATIVE_FRAME_SHAPE_2560",
    "NATIVE_FRAME_SHAPE_3840",
    "SUPPORTED_MODEL_WIDTHS",
]
