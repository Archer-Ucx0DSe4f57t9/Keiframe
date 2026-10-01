"""OCR provider abstractions and the production Tesseract adapter.

The recognizer depends on the small ``OCRProvider`` protocol only. Tesseract
is an implementation detail of ``TesseractOCRProvider`` and can be replaced by
a deterministic mock or another engine without changing recognition logic.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Protocol, Union

import cv2
import numpy as np


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


__all__ = [
    "OCRProvider",
    "TesseractOCRProvider",
    "resolve_tesseract_executable",
]
