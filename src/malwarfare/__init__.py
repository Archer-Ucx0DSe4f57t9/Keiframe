"""Portable Malwarfare public API.

The production OCR exports remain available from this package, but they are
loaded lazily. Dataset preparation and human-only annotation modules can
therefore import ``src.malwarfare.*`` without importing production inference
as an import-time side effect.
"""

from .profile import MalwarfareProfile, load_profile

__all__ = [
    "Malwarfare3840Runtime",
    "MalwarfareOcrProcessor",
    "MalwarfareOcrResult",
    "MalwarfareProfile",
    "MalwarfareRuntimeRouter",
    "load_profile",
]


def __getattr__(name: str):
    if name in {"MalwarfareOcrProcessor", "MalwarfareOcrResult"}:
        from .ocr_processor import MalwarfareOcrProcessor, MalwarfareOcrResult

        return {
            "MalwarfareOcrProcessor": MalwarfareOcrProcessor,
            "MalwarfareOcrResult": MalwarfareOcrResult,
        }[name]
    if name == "Malwarfare3840Runtime":
        from .runtime_3840 import Malwarfare3840Runtime

        return Malwarfare3840Runtime
    if name == "MalwarfareRuntimeRouter":
        from .runtime_router import MalwarfareRuntimeRouter

        return MalwarfareRuntimeRouter
    raise AttributeError(name)
