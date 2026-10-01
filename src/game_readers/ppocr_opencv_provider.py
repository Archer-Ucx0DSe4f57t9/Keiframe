"""OpenCV DNN PP-OCRv5 recognition-only provider.

This module is intentionally independent from RapidOCR and ONNX Runtime. It
is the production adapter for the optional PP-OCRv5 recognition addon.

The image normalization and CTC decoding below mirror the implementations
installed with RapidOCR 3.9.2:

* ``rapidocr.ch_ppocr_rec.main.TextRecognizer.resize_norm_img``
* ``rapidocr.ch_ppocr_rec.utils.CTCLabelDecode``

Keeping those details local makes it possible to benchmark OpenCV DNN without
importing either of the production OCR dependencies.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, List, Optional, Tuple, Union

import cv2
import numpy as np

from src.utils.fileutil import get_resources_dir
from src.utils.logging_util import get_logger


logger = get_logger(__name__)


class OpenCVDNNPPOCRv5Provider:
    """Run the local PP-OCRv5 recognition model through OpenCV DNN.

    The provider accepts a title crop and returns one raw OCR line for each
    known line in that crop.  It deliberately does not perform text detection,
    composition matching, race filtering, screenshot access, or Qt work.
    """

    MODEL_FILENAME = "ch_PP-OCRv5_rec_mobile.onnx"
    DICT_FILENAME = "ppocrv5_dict.txt"

    # These values are the effective PP-OCRv5 mobile recognition config
    # validated against the reference implementation.
    REC_IMAGE_SHAPE = (3, 48, 320)

    # Phase B emits a 46px title crop with category and composition on two
    # horizontal lines.  Keep this geometry aligned with PPOCRv5OCRProvider;
    # it is crop handling, not matching or business logic.
    TITLE_CROP_MIN_HEIGHT = 40
    TITLE_CROP_TOP_WIDTH = 240
    TITLE_CROP_RECOGNITION_WIDTHS = (180, 200, 220, 240, 260, 280)

    def __init__(
        self,
        model_path: Optional[Union[str, Path]] = None,
        dict_path: Optional[Union[str, Path]] = None,
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
        self.character = self._load_character_dict(self.dict_path)

        self.backend = "opencv-dnn"
        self.target = "cpu"
        self.inference_count = 0
        self.initialization_elapsed_ms: Optional[float] = None
        self.model_load_elapsed_ms: Optional[float] = None
        self.first_inference_elapsed_ms: Optional[float] = None
        self.last_inference_elapsed_ms: Optional[float] = None
        self.input_tensor_shape = (1, *self.REC_IMAGE_SHAPE)
        self.output_shape: Optional[Tuple[int, ...]] = None
        self._engine_lock = threading.RLock()

        initialization_started = time.perf_counter()
        model_started = time.perf_counter()
        try:
            self._net = cv2.dnn.readNetFromONNX(str(self.model_path))
            self._net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
            self._net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
        except Exception as exc:
            raise RuntimeError(
                "OpenCV DNN PP-OCRv5 initialization failed for "
                f"{self.model_path}: {exc}"
            ) from exc
        self.model_load_elapsed_ms = (time.perf_counter() - model_started) * 1000.0
        self.initialization_elapsed_ms = (
            time.perf_counter() - initialization_started
        ) * 1000.0
        self._logger.info(
            "[OpenCV-PPOCR] INIT elapsed_ms=%.1f model_load_ms=%.1f model_path=%s",
            self.initialization_elapsed_ms,
            self.model_load_elapsed_ms,
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
        explicit_path: Optional[Union[str, Path]],
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
    def _load_character_dict(dict_path: Path) -> List[str]:
        """Load characters with RapidOCR's space and blank token placement."""

        character_list: List[str] = []
        with dict_path.open("rb") as handle:
            for line in handle.readlines():
                # This mirrors RapidOCR 3.9.2 CTCLabelDecode.read_character_file.
                character_list.append(
                    line.decode("utf-8").strip("\n").strip("\r\n")
                )

        # RapidOCR inserts the ordinary space at the end, then CTC blank at 0.
        character_list.insert(len(character_list), " ")
        character_list.insert(0, "blank")
        return character_list

    @classmethod
    def _recognition_segments(cls, image: np.ndarray) -> List[np.ndarray]:
        """Split the known two-line title crop into recognition segments."""

        if image.ndim < 2 or image.shape[0] < cls.TITLE_CROP_MIN_HEIGHT:
            return [image]
        split_at = image.shape[0] // 2
        if split_at <= 0 or split_at >= image.shape[0]:
            return [image]
        return [image[:split_at], image[max(0, split_at - 1) : -1]]

    @classmethod
    def _recognition_inputs(
        cls,
        segment: np.ndarray,
        segment_index: int,
    ) -> List[np.ndarray]:
        """Use the same title-line width candidates as the production provider."""

        if segment_index == 0:
            width = min(cls.TITLE_CROP_TOP_WIDTH, segment.shape[1])
            return [segment[:, :width]]

        inputs = []
        for width in cls.TITLE_CROP_RECOGNITION_WIDTHS:
            if width <= segment.shape[1]:
                inputs.append(segment[:, :width])
        return inputs or [segment]

    @classmethod
    def _resize_norm_img(cls, image: np.ndarray) -> np.ndarray:
        """Match RapidOCR 3.9.2 ``TextRecognizer.resize_norm_img`` exactly."""

        img_channel, img_height, img_width = cls.REC_IMAGE_SHAPE
        if image.ndim != 3 or image.shape[2] != img_channel:
            raise ValueError(
                "PP-OCRv5 input must be a three-channel BGR image after conversion"
            )

        # RapidOCR uses max_wh_ratio from rec_img_shape for this recognition-only
        # call.  With [3, 48, 320], this keeps the input width at 320 and pads
        # narrower title crops on the right.
        max_wh_ratio = img_width / img_height
        effective_width = int(img_height * max_wh_ratio)

        height, width = image.shape[:2]
        ratio = width / float(height)
        if int(np.ceil(img_height * ratio)) > effective_width:
            resized_width = effective_width
        else:
            resized_width = int(np.ceil(img_height * ratio))

        resized_image = cv2.resize(image, (resized_width, img_height))
        resized_image = resized_image.astype("float32")
        resized_image = resized_image.transpose((2, 0, 1)) / 255
        resized_image -= 0.5
        resized_image /= 0.5

        padding_image = np.zeros(
            (img_channel, img_height, effective_width), dtype=np.float32
        )
        padding_image[:, :, 0:resized_width] = resized_image
        return padding_image

    def _forward_decode(self, image: np.ndarray) -> Tuple[str, float]:
        """Preprocess, run one OpenCV forward pass, and CTC-decode it."""

        normalized = self._resize_norm_img(image)
        blob = np.ascontiguousarray(normalized[np.newaxis, :], dtype=np.float32)
        self._net.setInput(blob)
        predictions = np.asarray(self._net.forward())
        self.output_shape = tuple(int(value) for value in predictions.shape)

        if predictions.ndim == 2:
            predictions = predictions[np.newaxis, :]
        if predictions.ndim != 3:
            raise RuntimeError(
                "unexpected PP-OCRv5 output rank: "
                f"{predictions.ndim} ({self.output_shape})"
            )
        if predictions.shape[0] != 1:
            raise RuntimeError(
                "unexpected PP-OCRv5 batch size: "
                f"{predictions.shape[0]} ({self.output_shape})"
            )
        if predictions.shape[2] != len(self.character):
            raise RuntimeError(
                "PP-OCRv5 dictionary/output mismatch: "
                f"output classes={predictions.shape[2]}, "
                f"dictionary classes={len(self.character)}"
            )

        # This is RapidOCR 3.9.2 CTCLabelDecode.__call__/decode: argmax,
        # remove adjacent duplicates, ignore token 0 (blank), and average the
        # retained per-timestep maximum probabilities.
        token_indices = predictions.argmax(axis=2)[0]
        token_probabilities = predictions.max(axis=2)[0]
        selection = np.ones(len(token_indices), dtype=bool)
        selection[1:] = token_indices[1:] != token_indices[:-1]
        selection &= token_indices != 0

        confidence_values = token_probabilities[selection].tolist()
        if not confidence_values:
            confidence_values = [0]

        text = "".join(
            self.character[int(token_id)]
            for token_id in token_indices[selection]
        )
        score = float(np.mean(confidence_values).round(5).tolist())
        return text, score

    @staticmethod
    def _candidate_quality(text: str, score: float) -> Tuple[float, float, int]:
        """Use the same confidence/completeness tie-break as production OCR."""

        stripped = text.strip()
        if not stripped:
            return (-1.0, score, 0)
        completeness_bonus = min(len(stripped), 32) * 0.015
        return (score + completeness_bonus, score, len(stripped))

    def recognize(self, image: np.ndarray) -> List[str]:
        """Return raw OCR lines from one non-empty BGR or greyscale crop."""

        if not isinstance(image, np.ndarray) or image.size == 0:
            raise ValueError("OCR input must be a non-empty numpy image")

        if image.ndim == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        elif image.ndim != 3 or image.shape[2] != 3:
            raise ValueError("OCR input must be a BGR or greyscale image")

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
                    text, score = self._forward_decode(recognition_input)
                    quality = self._candidate_quality(text, score)
                    if quality > best_quality:
                        best_text = text
                        best_quality = quality
                texts.append(best_text)

        elapsed_ms = (time.perf_counter() - started) * 1000.0
        self.inference_count += 1
        self.last_inference_elapsed_ms = elapsed_ms
        if self.inference_count == 1:
            self.first_inference_elapsed_ms = elapsed_ms
            self._logger.info(
                "[OpenCV-PPOCR] OCR_FIRST elapsed_ms=%.1f",
                elapsed_ms,
            )
        else:
            self._logger.debug(
                "[OpenCV-PPOCR] OCR_WARM elapsed_ms=%.1f",
                elapsed_ms,
            )
        return texts


__all__ = ["OpenCVDNNPPOCRv5Provider"]
