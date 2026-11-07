"""Explicit native-resolution router for Malwarfare 2560 and 3840 OCR."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter

import cv2
import numpy as np

from .ocr_processor import MalwarfareOcrProcessor, MalwarfareOcrResult
from .runtime.geometry import CANONICAL_HEIGHT, CANONICAL_WIDTH
from .runtime_3840 import (
    BUNDLE_ID_3840,
    DEFAULT_RUNTIME_3840_RESOURCE_DIR,
    Malwarfare3840Runtime,
)


BUNDLE_ID_2560 = "malwarfare_ocr_runtime_zh_2560_v1"
NATIVE_FRAME_SHAPE_2560 = (1440, 2560, 3)
NATIVE_FRAME_SHAPE_3840 = (2160, 3840, 3)


class MalwarfareRuntimeRouter:
    """Select exactly one frozen runtime from the native frame dimensions."""

    def __init__(
        self,
        *,
        runtime_2560: MalwarfareOcrProcessor,
        runtime_3840: Malwarfare3840Runtime,
        model_load_ms_2560: float = 0.0,
        model_load_ms_3840: float | None = None,
    ) -> None:
        self._runtime_2560 = runtime_2560
        self._runtime_3840 = runtime_3840
        self._model_load_ms_2560 = float(model_load_ms_2560)
        self._model_load_ms_3840 = (
            runtime_3840.model_load_ms
            if model_load_ms_3840 is None
            else float(model_load_ms_3840)
        )
        self._last_runtime_bundle_id: str | None = None

    @classmethod
    def from_default_resources(
        cls,
        *,
        resource_dir_3840: str | Path = DEFAULT_RUNTIME_3840_RESOURCE_DIR,
    ) -> "MalwarfareRuntimeRouter":
        started = perf_counter()
        runtime_2560 = MalwarfareOcrProcessor.from_default_resources()
        load_2560 = (perf_counter() - started) * 1000.0
        runtime_3840 = Malwarfare3840Runtime.from_default_resources(
            resource_dir=resource_dir_3840
        )
        return cls(
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
            BUNDLE_ID_2560: self._model_load_ms_2560,
            BUNDLE_ID_3840: self._model_load_ms_3840,
        }

    @staticmethod
    def runtime_bundle_id_for_shape(shape: tuple[int, ...]) -> str:
        if tuple(shape) == NATIVE_FRAME_SHAPE_2560:
            return BUNDLE_ID_2560
        if tuple(shape) == NATIVE_FRAME_SHAPE_3840:
            return BUNDLE_ID_3840
        raise ValueError(
            "unsupported native Malwarfare frame shape; expected "
            f"{NATIVE_FRAME_SHAPE_2560} or {NATIVE_FRAME_SHAPE_3840}, got {shape}"
        )

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
        if bundle_id == BUNDLE_ID_2560:
            canonical = self.canonicalize_2560(native_frame_bgr)
            result = self._runtime_2560.process(
                canonical,
                ui_profile=ui_profile,
                count_color_profile=count_color_profile,
            )
        else:
            result = self._runtime_3840.process(
                native_frame_bgr,
                ui_profile=ui_profile,
                count_color_profile=count_color_profile,
            )
        self._last_runtime_bundle_id = bundle_id
        return result


__all__ = [
    "BUNDLE_ID_2560",
    "MalwarfareRuntimeRouter",
    "NATIVE_FRAME_SHAPE_2560",
    "NATIVE_FRAME_SHAPE_3840",
]
