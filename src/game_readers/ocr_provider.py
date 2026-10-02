"""OCR provider abstractions and OCR engine adapters.

The recognizer depends on the small ``OCRProvider`` protocol only. Tesseract
and PP-OCRv5 are implementation details of their respective providers and can
be replaced by a deterministic mock or another engine without changing
recognition logic.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, List, Optional, Protocol, Union

import cv2
import numpy as np

from src.utils.fileutil import get_resources_dir
from src.utils.logging_util import get_logger


logger = get_logger(__name__)


class OCRProvider(Protocol):
    """Minimal OCR interface consumed by ``EnemyCompositionRecognizer``."""

    def recognize(self, image: np.ndarray) -> List[str]:
        """Return raw OCR lines in source order."""


def resolve_tesseract_executable(
    executable: Optional[Union[str, os.PathLike[str]]] = None,
) -> Optional[str]:
    """Resolve Tesseract from an explicit path, environment, or PATH.

    No developer-machine installation path is embedded here. ``TESSERACT_CMD``
    is kept compatible with the Phase C1 offline harness; PATH is the normal
    deployment mechanism.
    """

    candidates: List[str] = []
    if executable is not None:
        candidates.append(os.fspath(executable))
    configured = os.environ.get("TESSERACT_CMD")
    if configured:
        candidates.append(configured)
    path_candidate = shutil.which("tesseract")
    if path_candidate:
        candidates.append(path_candidate)

    for candidate in candidates:
        if not candidate:
            continue
        candidate_path = Path(candidate)
        if candidate_path.is_file():
            return str(candidate_path)
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


class TesseractOCRProvider:
    """Run the verified Phase C1 Tesseract CLI configuration."""

    def __init__(
        self,
        language: str,
        executable: Optional[Union[str, os.PathLike[str]]] = None,
        psm: str = "6",
        timeout_seconds: Optional[float] = None,
    ) -> None:
        self.language = str(language).strip()
        self.psm = str(psm).strip()
        self.timeout_seconds = timeout_seconds
        if not self.language:
            raise ValueError("Tesseract language cannot be empty")
        if not self.psm:
            raise ValueError("Tesseract page segmentation mode cannot be empty")

        resolved = resolve_tesseract_executable(executable)
        if resolved is None:
            raise FileNotFoundError(
                "Tesseract executable was not found; set TESSERACT_CMD or add "
                "tesseract to PATH"
            )
        self.executable = resolved

    def recognize(self, image: np.ndarray) -> List[str]:
        """OCR one BGR/greyscale image and return its raw output lines."""

        if not isinstance(image, np.ndarray) or image.size == 0:
            raise ValueError("OCR input must be a non-empty numpy image")

        success, encoded = cv2.imencode(".png", image)
        if not success:
            raise RuntimeError("failed to encode OCR input as PNG")

        completed = subprocess.run(
            [
                self.executable,
                "stdin",
                "stdout",
                "-l",
                self.language,
                "--psm",
                self.psm,
            ],
            input=encoded.tobytes(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=self.timeout_seconds,
        )
        if completed.returncode != 0:
            error = completed.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(error or f"tesseract exited with {completed.returncode}")

        raw_text = (
            completed.stdout.decode("utf-8", errors="replace")
            .replace("\r\n", "\n")
            .replace("\r", "\n")
        )
        return raw_text.splitlines()


class PPOCRv5OCRProvider:
    """Run PP-OCRv5 Mobile recognition on an existing text crop.

    The panel detector already supplies a title crop, so this provider
    deliberately configures RapidOCR for recognition only.  RapidOCR and
    ONNX Runtime are imported lazily after the local model files have been
    validated; a missing optional dependency or resource therefore becomes a
    clear provider initialization error instead of breaking the main app at
    import time.

    ``RapidOCR`` loads the ONNX session lazily on the first call.  The provider
    instance is retained and reused for every subsequent crop, which makes the
    first inference and warm inference costs observable separately.  The
    existing title crop contains two known horizontal lines, so a title-sized
    crop is split by its fixed midpoint before recognition; this is geometry
    preprocessing, not text detection.
    """

    MODEL_FILENAME = "ch_PP-OCRv5_rec_mobile.onnx"
    DICT_FILENAME = "ppocrv5_dict.txt"
    TITLE_CROP_MIN_HEIGHT = 40
    TITLE_CROP_TOP_WIDTH = 240
    TITLE_CROP_RECOGNITION_WIDTHS = (180, 200, 220, 240, 260, 280)

    def __init__(
        self,
        model_path: Optional[Union[str, os.PathLike[str]]] = None,
        dict_path: Optional[Union[str, os.PathLike[str]]] = None,
        provider_logger: Optional[Any] = None,
    ) -> None:
        self._logger = provider_logger or logger
        self.model_path = self._resolve_existing_path(
            model_path,
            self.MODEL_FILENAME,
            "PP-OCRv5 model",
        )
        self.dict_path = self._resolve_existing_path(
            dict_path,
            self.DICT_FILENAME,
            "PP-OCRv5 dictionary",
        )

        try:
            import onnxruntime  # noqa: F401
            from rapidocr import EngineType, ModelType, OCRVersion, RapidOCR
            from rapidocr.utils.typings import LangRec
        except ImportError as exc:
            raise RuntimeError(
                "PP-OCRv5 requires the optional 'rapidocr' and "
                "'onnxruntime' packages"
            ) from exc

        self.backend = "onnxruntime"
        self.use_det = False
        self.use_cls = False
        self.use_rec = True
        self.inference_count = 0
        self.initialization_elapsed_ms: Optional[float] = None
        self.first_inference_elapsed_ms: Optional[float] = None
        self.last_inference_elapsed_ms: Optional[float] = None
        self.execution_providers: List[str] = []
        self._engine_lock = threading.RLock()

        params = {
            "Global.use_det": False,
            "Global.use_cls": False,
            "Global.use_rec": True,
            "Global.log_level": "error",
            "Rec.engine_type": EngineType.ONNXRUNTIME,
            "Rec.lang_type": LangRec.CH,
            "Rec.model_type": ModelType.MOBILE,
            "Rec.ocr_version": OCRVersion.PPOCRV5,
            "Rec.model_path": str(self.model_path),
            "Rec.rec_keys_path": str(self.dict_path),
            "EngineConfig.onnxruntime.use_cuda": False,
            "EngineConfig.onnxruntime.use_dml": False,
            "EngineConfig.onnxruntime.use_cann": False,
            "EngineConfig.onnxruntime.use_coreml": False,
        }

        initialization_started = time.perf_counter()
        try:
            self._engine = RapidOCR(params=params)
        except Exception as exc:
            raise RuntimeError(
                "PP-OCRv5 RapidOCR initialization failed for "
                f"{self.model_path}"
            ) from exc
        self.initialization_elapsed_ms = (
            time.perf_counter() - initialization_started
        ) * 1000.0
        self._logger.info(
            "[PPOCR] INIT elapsed_ms=%.1f model_path=%s",
            self.initialization_elapsed_ms,
            self.model_path,
        )

    @classmethod
    def default_model_path(cls) -> Path:
        """Return the local PP-OCRv5 model path in source/PyInstaller layouts."""

        resources_dir = get_resources_dir("ocr", "ppocrv5")
        if not resources_dir:
            raise FileNotFoundError(
                "PP-OCRv5 resource directory could not be resolved"
            )
        return Path(resources_dir) / cls.MODEL_FILENAME

    @classmethod
    def default_dict_path(cls) -> Path:
        """Return the local PP-OCRv5 dictionary path."""

        resources_dir = get_resources_dir("ocr", "ppocrv5")
        if not resources_dir:
            raise FileNotFoundError(
                "PP-OCRv5 resource directory could not be resolved"
            )
        return Path(resources_dir) / cls.DICT_FILENAME

    @classmethod
    def _resolve_existing_path(
        cls,
        explicit_path: Optional[Union[str, os.PathLike[str]]],
        default_filename: str,
        description: str,
    ) -> Path:
        path = (
            Path(explicit_path)
            if explicit_path is not None
            else (
                cls.default_model_path()
                if default_filename == cls.MODEL_FILENAME
                else cls.default_dict_path()
            )
        ).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(
                f"{description} was not found: {path}. "
                "Place the model and dictionary under resources\\ocr\\ppocrv5."
            )
        return path

    @staticmethod
    def _extract_texts(result: Any) -> List[str]:
        """Convert RapidOCR recognition output into raw OCR lines."""

        texts = getattr(result, "txts", None)
        if texts is None:
            text = getattr(result, "text", None)
            if text is None:
                return []
            texts = [text]
        if isinstance(texts, str):
            return [texts]
        return [str(text) for text in texts]

    @staticmethod
    def _first_text_and_score(result: Any) -> tuple[str, float]:
        texts = PPOCRv5OCRProvider._extract_texts(result)
        if not texts:
            return "", 0.0
        scores = getattr(result, "scores", None)
        try:
            score = float(scores[0]) if scores else 0.0
        except (TypeError, ValueError, IndexError):
            score = 0.0
        return texts[0], score

    @staticmethod
    def _candidate_quality(text: str, score: float) -> tuple[float, float, int]:
        """Prefer confident results, with a small tie-break for completeness."""

        stripped = text.strip()
        if not stripped:
            return (-1.0, score, 0)
        # Narrower input windows can improve recognition but occasionally drop
        # the final character.  A bounded length tie-break keeps a complete
        # result when confidence is effectively the same without consulting
        # the composition catalog.
        completeness_bonus = min(len(stripped), 32) * 0.015
        return (score + completeness_bonus, score, len(stripped))

    @classmethod
    def _recognition_segments(cls, image: np.ndarray) -> List[np.ndarray]:
        """Return one segment per known title-crop text line.

        Phase B emits a 46px-high crop with the category on the upper half and
        the composition on the lower half.  Shorter images are treated as a
        single line so the provider remains useful for direct callers too.
        """

        if image.ndim < 2 or image.shape[0] < cls.TITLE_CROP_MIN_HEIGHT:
            return [image]
        split_at = image.shape[0] // 2
        if split_at <= 0 or split_at >= image.shape[0]:
            return [image]
        # Keep a small overlap at the line boundary.  The Phase B crop has a
        # dark gap between lines, and the lower line starts around row 22.
        return [image[:split_at], image[max(0, split_at - 1) : -1]]

    @classmethod
    def _recognition_inputs(
        cls,
        segment: np.ndarray,
        segment_index: int,
    ) -> List[np.ndarray]:
        if segment_index == 0:
            width = min(cls.TITLE_CROP_TOP_WIDTH, segment.shape[1])
            return [segment[:, :width]]

        inputs = []
        for width in cls.TITLE_CROP_RECOGNITION_WIDTHS:
            if width <= segment.shape[1]:
                inputs.append(segment[:, :width])
        return inputs or [segment]

    def recognize(self, image: np.ndarray) -> List[str]:
        """Recognize raw text from one non-empty BGR/greyscale title crop."""

        if not isinstance(image, np.ndarray) or image.size == 0:
            raise ValueError("OCR input must be a non-empty numpy image")

        started = time.perf_counter()
        texts: List[str] = []
        with self._engine_lock:
            for segment_index, segment in enumerate(
                self._recognition_segments(image)
            ):
                best_text = ""
                best_quality = self._candidate_quality(best_text, 0.0)
                for recognition_input in self._recognition_inputs(
                    segment,
                    segment_index,
                ):
                    # Pass the switches on every call as well as in the
                    # constructor.  This keeps the recognition-only contract
                    # explicit and prevents a future caller/config mutation
                    # from enabling det/cls implicitly.
                    result = self._engine(
                        recognition_input,
                        use_det=False,
                        use_cls=False,
                        use_rec=True,
                    )
                    text, score = self._first_text_and_score(result)
                    quality = self._candidate_quality(text, score)
                    if quality > best_quality:
                        best_text = text
                        best_quality = quality
                texts.append(best_text)

            text_rec = getattr(self._engine, "text_rec", None)
            ort_session = getattr(text_rec, "session", None)
            ort_session = getattr(ort_session, "session", None)
            get_providers = getattr(ort_session, "get_providers", None)
            if callable(get_providers):
                self.execution_providers = list(get_providers())

        elapsed_ms = (time.perf_counter() - started) * 1000.0
        self.inference_count += 1
        self.last_inference_elapsed_ms = elapsed_ms
        if self.inference_count == 1:
            self.first_inference_elapsed_ms = elapsed_ms
            self._logger.info(
                "[PPOCR] OCR_FIRST elapsed_ms=%.1f",
                elapsed_ms,
            )
        else:
            self._logger.debug(
                "[PPOCR] OCR_WARM elapsed_ms=%.1f",
                elapsed_ms,
            )
        return texts


__all__ = [
    "OCRProvider",
    "PPOCRv5OCRProvider",
    "TesseractOCRProvider",
    "resolve_tesseract_executable",
]
