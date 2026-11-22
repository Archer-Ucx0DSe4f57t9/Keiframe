import hashlib
import importlib
import json
from pathlib import Path
import re
from types import SimpleNamespace
import unittest
from unittest import mock
from unittest.mock import patch

import numpy as np

from src import game_state_service
from src.game_time_handler import _log_malwarfare_event_diagnostic
from src.map_handlers.malwarfare import MalwarfareOcrProcessor
from src.map_handlers.IdentifyMap import identify_map
from src.map_handlers.malwarfare.malwarfare_map_handler import MalwarfareMapHandler
from src.map_handlers.malwarfare.malwarfare_map_handler_legacy import (
    MalwarfareMapHandler as LegacyMalwarfareMapHandler,
)
from src.map_handlers.malwarfare.malwarfate_ocr_processor import (
    MalwarfareOcrProcessor as LegacyOcrProcessor,
)
from src.map_handlers.malwarfare.runtime_router import MalwarfareRuntimeRouter


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEGACY_HANDLER_SHA256 = (
    "85a99999206d61d35d08bf0b9c81c25c63be7992d2ac55b7686a3af8396179c3"
)


class FakeOcr:
    def __init__(self, count_result=2, status_results=None, count_callback=None):
        self.count_result = count_result
        self.status_results = list(status_results or [("135", False)])
        self.count_callback = count_callback
        self.count_calls = []
        self.status_calls = []

    def recognize_count(self, frame, *, ui_profile, count_color_profile):
        self.count_calls.append((ui_profile, count_color_profile))
        if self.count_callback is not None:
            return self.count_callback(ui_profile, count_color_profile)
        if isinstance(self.count_result, list):
            return self.count_result.pop(0)
        return self.count_result

    def recognize_time_paused(self, frame, *, ui_profile):
        self.status_calls.append(ui_profile)
        if len(self.status_results) > 1:
            return self.status_results.pop(0)
        return self.status_results[0]


class MalwarfareMapHandlerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

    @staticmethod
    def _known_handler(fake_ocr):
        handler = MalwarfareMapHandler(ocr_processor=fake_ocr)
        handler._current_ui_profile = "Normal"
        handler._detected_count_color = "green"
        handler._latest_count = 2
        return handler

    @classmethod
    def _probe_frame(cls, ui_profile, color_profile):
        frame = cls.frame.copy()
        bgr_colors = {
            "green": (0, 255, 0),
            "blue": (255, 0, 0),
            "orange": (0, 128, 255),
        }
        x0, y0, x1, y1 = MalwarfareMapHandler.COUNT_PROBE_ROI
        offset = MalwarfareMapHandler.UI_PROFILE_OFFSETS[ui_profile]
        frame[y0 + offset : y1 + offset, x0:x1] = bgr_colors[color_profile]
        return frame

    def test_legacy_backup_integrity_and_import(self):
        legacy_path = (
            PROJECT_ROOT
            / "src"
            / "map_handlers"
            / "malwarfare"
            / "malwarfare_map_handler_legacy.py"
        )
        digest = hashlib.sha256(legacy_path.read_bytes()).hexdigest()

        self.assertEqual(LEGACY_HANDLER_SHA256, digest)
        self.assertEqual("MalwarfareMapHandler", LegacyMalwarfareMapHandler.__name__)

    def test_new_handler_has_no_old_ocr_or_executor_dependency(self):
        source = (
            PROJECT_ROOT
            / "src"
            / "map_handlers"
            / "malwarfare"
            / "malwarfare_map_handler.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("malwarfate_ocr_processor", source)
        self.assertNotIn("ThreadPoolExecutor", source)
        self.assertNotIn("_post_process_n_value", source)

    def test_runtime_manifest_files_exist_and_default_engine_loads(self):
        manifest_path = (
            PROJECT_ROOT
            / "resources"
            / "templates"
            / "malwarfare"
            / "runtime_1920_2560"
            / "runtime_bundle_manifest.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for relative_path in manifest["python_files"] + manifest["resource_files"]:
            self.assertTrue((PROJECT_ROOT / relative_path).is_file(), relative_path)

        engine = MalwarfareOcrProcessor.from_default_resources()
        self.assertIsInstance(engine, MalwarfareOcrProcessor)

    def test_new_package_imports_and_all_default_runtimes_load(self):
        modules = (
            "src.map_handlers.malwarfare.ocr_processor",
            "src.map_handlers.malwarfare.paused_recognizer",
            "src.map_handlers.malwarfare.profile",
            "src.map_handlers.malwarfare.runtime_1920",
            "src.map_handlers.malwarfare.runtime_3840",
            "src.map_handlers.malwarfare.runtime_router",
            "src.map_handlers.malwarfare.malwarfare_event_manager",
            "src.map_handlers.malwarfare.malwarfare_map_handler",
            "src.map_handlers.malwarfare.malwarfare_map_handler_legacy",
            "src.map_handlers.malwarfare.malwarfate_ocr_processor",
        )
        for module_name in modules:
            with self.subTest(module_name=module_name):
                self.assertIsNotNone(importlib.import_module(module_name))

        router = MalwarfareRuntimeRouter.from_default_resources()
        for model_width in (1920, 2560, 3840):
            with self.subTest(model_width=model_width):
                self.assertIsNotNone(router.runtime_for_width(model_width))

    def test_legacy_english_templates_load_from_consolidated_directory(self):
        processor = LegacyOcrProcessor(lang="en")
        for color in ("yellow", "green", "blue", "orange"):
            with self.subTest(color=color):
                self.assertTrue(processor.templates[color])

    def test_old_code_and_resource_roots_are_absent(self):
        old_paths = (
            PROJECT_ROOT / "src" / "malwarfare",
            PROJECT_ROOT / "resources" / "malwarfare",
            PROJECT_ROOT / "resources" / "malwarfare_3840",
        )
        for path in old_paths:
            with self.subTest(path=path):
                self.assertFalse(path.exists())

    def test_pyinstaller_spec_uses_consolidated_paths(self):
        spec = (PROJECT_ROOT / "Keiframe.spec").read_text(encoding="utf-8")
        self.assertIn("'src', 'map_handlers', 'malwarfare'", spec)
        self.assertIn("'runtime_1920_2560'", spec)
        self.assertIn("'malwarfare', 'runtime_3840'", spec)
        self.assertNotIn("'resources', 'malwarfare_3840'", spec)
        self.assertNotIn("'src', 'malwarfare'", spec)

    def test_runtime_initialization_errors_fail_fast(self):
        with patch.object(
            MalwarfareOcrProcessor,
            "from_default_resources",
            side_effect=ValueError("manifest invalid"),
        ):
            with self.assertRaisesRegex(ValueError, "manifest invalid"):
                MalwarfareMapHandler()

    def test_independent_count_and_status_cadence(self):
        fake = FakeOcr()
        handler = self._known_handler(fake)

        handler._process_frame(self.frame, now=0.0)
        self.assertEqual(1, len(fake.count_calls))
        self.assertEqual(1, len(fake.status_calls))

        handler._process_frame(self.frame, now=0.13)
        self.assertEqual(1, len(fake.count_calls))
        self.assertEqual(2, len(fake.status_calls))

        handler._process_frame(self.frame, now=0.26)
        self.assertEqual(1, len(fake.count_calls))
        self.assertEqual(3, len(fake.status_calls))

        handler._process_frame(self.frame, now=1.0)
        self.assertEqual(2, len(fake.count_calls))
        self.assertEqual(4, len(fake.status_calls))

    def test_time_above_25_seconds_is_preserved_on_neither(self):
        fake = FakeOcr(status_results=[("058", False), (None, False)])
        handler = self._known_handler(fake)

        handler._ocr_and_process_time_and_paused(self.frame)
        handler._update_latest_result()
        self.assertEqual("0:58", handler.get_latest_data()["time"])

        handler._ocr_and_process_time_and_paused(self.frame)
        handler._update_latest_result()
        self.assertEqual(
            {"lang": handler.lang, "n": 2, "time": "0:58", "is_paused": False},
            handler.get_latest_data(),
        )

    def test_time_at_or_below_25_seconds_enters_no_timer_state(self):
        fake = FakeOcr(status_results=[("020", False), (None, False)])
        handler = self._known_handler(fake)

        handler._ocr_and_process_time_and_paused(self.frame)
        handler._update_latest_result()
        self.assertEqual("0:20", handler.get_latest_data()["time"])

        handler._ocr_and_process_time_and_paused(self.frame)
        handler._update_latest_result()
        self.assertEqual(
            {"lang": handler.lang, "n": 2, "time": None, "is_paused": False},
            handler.get_latest_data(),
        )

    def test_paused_sequence_retains_historical_time(self):
        fake = FakeOcr(
            status_results=[
                ("135", False),
                (None, True),
                (None, True),
                ("134", False),
            ]
        )
        handler = self._known_handler(fake)
        expected = [
            ("1:35", False),
            ("1:35", True),
            ("1:35", True),
            ("1:34", False),
        ]

        for expected_time, expected_paused in expected:
            handler._ocr_and_process_time_and_paused(self.frame)
            handler._update_latest_result()
            result = handler.get_latest_data()
            self.assertEqual(expected_time, result["time"])
            self.assertEqual(expected_paused, result["is_paused"])

    def test_neither_after_pause_clears_pause_but_keeps_time_above_25(self):
        fake = FakeOcr(
            status_results=[("135", False), (None, True), (None, False)]
        )
        handler = self._known_handler(fake)

        for _ in range(3):
            handler._ocr_and_process_time_and_paused(self.frame)
            handler._update_latest_result()

        self.assertEqual(
            {"lang": handler.lang, "n": 2, "time": "1:35", "is_paused": False},
            handler.get_latest_data(),
        )

    def test_count_accepts_only_integer_zero_through_four(self):
        fake = FakeOcr(count_result=[8, "3", 3])
        handler = self._known_handler(fake)

        handler._ocr_and_process_count(self.frame)
        self.assertIsNone(handler._latest_count)
        handler._ocr_and_process_count(self.frame)
        self.assertIsNone(handler._latest_count)
        handler._ocr_and_process_count(self.frame)
        self.assertEqual(3, handler._latest_count)

    def test_all_ui_profiles_are_passed_to_new_count_api(self):
        for expected_profile in MalwarfareMapHandler.UI_PROFILES:
            with self.subTest(ui_profile=expected_profile):
                fake = FakeOcr(
                    count_callback=lambda profile, color, expected=expected_profile: (
                        2 if profile == expected and color == "green" else None
                    )
                )
                handler = MalwarfareMapHandler(ocr_processor=fake)

                frame = self._probe_frame(expected_profile, "green")
                self.assertTrue(handler._detect_and_set_ui_state(frame))
                self.assertEqual(expected_profile, handler._current_ui_profile)
                self.assertEqual("green", handler._detected_count_color)

    def test_all_count_colors_are_discovered_and_cached(self):
        for expected_color in MalwarfareMapHandler.COUNT_COLOR_PROFILES:
            with self.subTest(color=expected_color):
                fake = FakeOcr(
                    count_callback=lambda profile, color, expected=expected_color: (
                        1 if profile == "Hero" and color == expected else None
                    )
                )
                handler = MalwarfareMapHandler(ocr_processor=fake)

                frame = self._probe_frame("Hero", expected_color)
                self.assertTrue(handler._detect_and_set_ui_state(frame))
                self.assertEqual("Hero", handler._current_ui_profile)
                self.assertEqual(expected_color, handler._detected_count_color)

    def test_time_api_receives_detected_ui_profile(self):
        fake = FakeOcr()
        handler = self._known_handler(fake)
        handler._current_ui_profile = "ZweihakaReplay"

        handler._ocr_and_process_time_and_paused(self.frame)

        self.assertEqual(["ZweihakaReplay"], fake.status_calls)

    def test_invalid_frame_is_not_resized_or_sent_to_ocr(self):
        fake = FakeOcr()
        handler = self._known_handler(fake)
        invalid_frame = np.zeros((720, 1280, 3), dtype=np.uint8)

        handler._process_frame(invalid_frame, now=0.0)

        self.assertEqual([], fake.count_calls)
        self.assertEqual([], fake.status_calls)

    def test_reset_reuses_loaded_ocr_engine(self):
        fake = FakeOcr()
        handler = self._known_handler(fake)

        handler.reset()

        self.assertIs(fake, handler.ocr)
        self.assertIsNone(handler._current_ui_profile)
        self.assertIsNone(handler._detected_count_color)
        self.assertIsNone(handler.get_latest_data())

    def test_consecutive_count_failures_reset_detection_with_recent_profile_hint(self):
        fake = FakeOcr()
        handler = self._known_handler(fake)
        handler._current_ui_profile = "HeroReplay"
        handler._latest_count = None

        for _ in range(handler.FAILURE_RELOCATION_THRESHOLD + 1):
            handler._update_latest_result()

        self.assertIsNone(handler._current_ui_profile)
        self.assertIsNone(handler._detected_count_color)
        self.assertEqual("HeroReplay", handler._last_successful_ui_profile)

    def test_same_count_rejects_abnormal_upward_time_jump(self):
        fake = FakeOcr(status_results=[("100", False), ("110", False)])
        handler = self._known_handler(fake)

        handler._ocr_and_process_time_and_paused(self.frame)
        handler._update_latest_result()
        handler._ocr_and_process_time_and_paused(self.frame)
        handler._update_latest_result()

        self.assertEqual("1:00", handler.get_latest_data()["time"])


class LoggingSemanticsTest(unittest.TestCase):
    def test_event_diagnostic_uses_debug(self):
        window = SimpleNamespace(logger=mock.Mock())

        with mock.patch("src.game_time_handler.time.monotonic", return_value=1.0):
            _log_malwarfare_event_diagnostic(
                window,
                "state",
                "normal state=%s",
                "ready",
            )

        window.logger.debug.assert_called_once_with(
            "[EventDiag] normal state=%s",
            "ready",
        )
        window.logger.warning.assert_not_called()

    def test_normal_map_signature_diagnostic_uses_debug(self):
        players = [
            {"id": 1, "name": "local", "type": "user"},
            {"id": 3, "name": "Purifier Hologram", "type": "computer"},
            {"id": 4, "name": "Purifier Hologram", "type": "computer"},
            {"id": 5, "name": "Megalith", "type": "computer"},
            {"id": 6, "name": "Neutral Reward", "type": "computer"},
        ]

        with mock.patch("src.map_handlers.IdentifyMap.logger") as logger:
            self.assertEqual("净网行动", identify_map(players))

        logger.debug.assert_called_once()
        logger.warning.assert_not_called()

    def test_normal_malwarfare_publish_diagnostic_uses_debug(self):
        handler = MalwarfareMapHandler(ocr_processor=object())
        handler.logger = mock.Mock()
        handler._latest_count = 2
        handler._latest_time = "135"
        handler._latest_paused = False

        handler._update_latest_result()

        handler.logger.debug.assert_called_once_with(
            "[PublishDiag] 最新状态已生成: %s",
            {"lang": handler.lang, "n": 2, "time": "1:35", "is_paused": False},
        )
        handler.logger.warning.assert_not_called()

    def test_normal_capture_pause_diagnostic_uses_debug(self):
        game_state_service._capture_log_times.clear()
        logger = mock.Mock()

        with (
            mock.patch.object(game_state_service, "logger", logger),
            mock.patch.object(
                game_state_service,
                "is_game_active",
                return_value=False,
            ),
        ):
            game_state_service._capture_game_screen(mock.Mock())

        logger.debug.assert_called_once()
        logger.warning.assert_not_called()

    def test_direct_normal_diagnostic_tags_are_not_warning_calls(self):
        normal_tags = (
            "RuntimeDiag",
            "MapDiag",
            "CaptureDiag",
            "PublishDiag",
            "EventDiag",
        )
        direct_warning = re.compile(
            r"\.warning\s*\(\s*[\"']\[(?:"
            + "|".join(normal_tags)
            + r")\]",
            re.MULTILINE,
        )
        dynamic_warning = re.compile(
            r"_log_diagnostic\s*\(\s*[\"'][^\"']+[\"']\s*,\s*"
            r"[\"']warning[\"']\s*,\s*[\"']\[(?:"
            + "|".join(normal_tags)
            + r")\]",
            re.MULTILINE,
        )

        offenders = []
        for path in (PROJECT_ROOT / "src").rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            if direct_warning.search(source) or dynamic_warning.search(source):
                offenders.append(str(path.relative_to(PROJECT_ROOT)))

        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
