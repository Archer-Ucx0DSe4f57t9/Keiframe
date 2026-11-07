from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

import numpy as np

from src.malwarfare.ocr_processor import MalwarfareOcrResult
from src.malwarfare.runtime_3840 import (
    BUNDLE_ID_3840,
    Malwarfare3840Runtime,
    verify_runtime_bundle_3840,
)
from src.malwarfare.runtime_router import (
    BUNDLE_ID_2560,
    MalwarfareRuntimeRouter,
)


ROOT = Path(__file__).resolve().parents[1]
RESOURCE_ROOT = ROOT / "resources" / "malwarfare_3840"


class Runtime3840Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runtime = Malwarfare3840Runtime.from_default_resources()

    def test_bundle_verifies_and_models_match_frozen_sources(self) -> None:
        result = verify_runtime_bundle_3840()
        self.assertTrue(result["verified"])
        self.assertEqual(result["bundle_id"], BUNDLE_ID_3840)
        manifest = json.loads(
            (RESOURCE_ROOT / "runtime_bundle_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        for relative, expected in manifest["model_file_sha256"].items():
            self.assertEqual(
                manifest["resource_file_sha256"][
                    f"resources/malwarfare_3840/{relative}"
                ],
                expected,
            )

    def test_public_contract_and_zero_safe_result(self) -> None:
        result = self.runtime.process(
            np.zeros((2160, 3840, 3), np.uint8),
            ui_profile="Normal",
            count_color_profile="orange",
        )
        self.assertIsInstance(result, MalwarfareOcrResult)
        self.assertEqual(result, MalwarfareOcrResult(None, None, False))

    def test_native_resolution_and_unverified_ui_profile_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "only native 3840x2160"):
            self.runtime.process(
                np.zeros((1440, 2560, 3), np.uint8),
                ui_profile="Normal",
                count_color_profile="orange",
            )
        with self.assertRaisesRegex(ValueError, "only verified UI profile"):
            self.runtime.process(
                np.zeros((2160, 3840, 3), np.uint8),
                ui_profile="Replay",
                count_color_profile="orange",
            )

    def test_model_files_load_only_during_initialization(self) -> None:
        import src.malwarfare.runtime_3840 as runtime_module

        with (
            mock.patch.object(
                runtime_module,
                "load_frozen_count_model",
                wraps=runtime_module.load_frozen_count_model,
            ) as load_count,
            mock.patch.object(
                runtime_module,
                "load_time_3840_model",
                wraps=runtime_module.load_time_3840_model,
            ) as load_time,
            mock.patch.object(
                runtime_module,
                "load_paused_3840_model",
                wraps=runtime_module.load_paused_3840_model,
            ) as load_paused,
        ):
            runtime = Malwarfare3840Runtime.from_default_resources()
            self.assertEqual(load_count.call_count, 3)
            self.assertEqual(load_time.call_count, 1)
            self.assertEqual(load_paused.call_count, 1)
            frame = np.zeros((2160, 3840, 3), np.uint8)
            runtime.process(
                frame, ui_profile="Normal", count_color_profile="orange"
            )
            runtime.process(
                frame, ui_profile="Normal", count_color_profile="orange"
            )
            self.assertEqual(load_count.call_count, 3)
            self.assertEqual(load_time.call_count, 1)
            self.assertEqual(load_paused.call_count, 1)

    def test_tampered_manifest_model_and_missing_resource_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "resources" / "malwarfare_3840"
            shutil.copytree(RESOURCE_ROOT, copied)
            manifest = copied / "runtime_bundle_manifest.json"
            manifest.write_bytes(manifest.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "manifest SHA-256 mismatch"):
                verify_runtime_bundle_3840(copied)
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "resources" / "malwarfare_3840"
            shutil.copytree(RESOURCE_ROOT, copied)
            model = copied / "time" / "model.npz"
            model.write_bytes(model.read_bytes() + b"tamper")
            with self.assertRaisesRegex(ValueError, "resource SHA-256 mismatch"):
                verify_runtime_bundle_3840(copied)
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "resources" / "malwarfare_3840"
            shutil.copytree(RESOURCE_ROOT, copied)
            (copied / "count" / "blue.npz").unlink()
            with self.assertRaisesRegex(ValueError, "missing or escaped"):
                verify_runtime_bundle_3840(copied)


class RuntimeRouterTests(unittest.TestCase):
    def test_routes_before_canonicalization_and_reports_bundle(self) -> None:
        runtime_2560 = mock.Mock()
        runtime_2560.process.return_value = MalwarfareOcrResult(0, "123", False)
        runtime_3840 = mock.Mock()
        runtime_3840.model_load_ms = 1.0
        runtime_3840.process.return_value = MalwarfareOcrResult(2, None, True)
        router = MalwarfareRuntimeRouter(
            runtime_2560=runtime_2560, runtime_3840=runtime_3840
        )
        first = router.process(
            np.zeros((1440, 2560, 3), np.uint8),
            ui_profile="Normal",
            count_color_profile="blue",
        )
        self.assertEqual(first.count, 0)
        runtime_2560.process.assert_called_once()
        self.assertEqual(
            runtime_2560.process.call_args.args[0].shape, (1080, 1920, 3)
        )
        self.assertEqual(router.last_runtime_bundle_id, BUNDLE_ID_2560)
        second = router.process(
            np.zeros((2160, 3840, 3), np.uint8),
            ui_profile="Normal",
            count_color_profile="green",
        )
        self.assertEqual(second.count, 2)
        self.assertEqual(
            runtime_3840.process.call_args.args[0].shape, (2160, 3840, 3)
        )
        self.assertEqual(router.last_runtime_bundle_id, BUNDLE_ID_3840)

    def test_unsupported_resolution_has_no_fallback(self) -> None:
        router = MalwarfareRuntimeRouter(
            runtime_2560=mock.Mock(), runtime_3840=mock.Mock(model_load_ms=0.0)
        )
        with self.assertRaisesRegex(ValueError, "unsupported native"):
            router.process(
                np.zeros((1080, 1920, 3), np.uint8),
                ui_profile="Normal",
                count_color_profile="orange",
            )


if __name__ == "__main__":
    unittest.main()
