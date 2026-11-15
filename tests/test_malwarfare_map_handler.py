import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from src.malwarfare import MalwarfareOcrProcessor
from src.map_handlers.malwarfare_map_handler import MalwarfareMapHandler
from src.map_handlers.malwarfare_map_handler_legacy import (
    MalwarfareMapHandler as LegacyMalwarfareMapHandler,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEGACY_HANDLER_SHA256 = (
    "b33774e12e667227c897924cd402bec29fad38c8a218f6af9ec24c671065be52"
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
            PROJECT_ROOT / "src" / "map_handlers" / "malwarfare_map_handler_legacy.py"
        )
        digest = hashlib.sha256(legacy_path.read_bytes()).hexdigest()

        self.assertEqual(LEGACY_HANDLER_SHA256, digest)
        self.assertEqual("MalwarfareMapHandler", LegacyMalwarfareMapHandler.__name__)

    def test_new_handler_has_no_old_ocr_or_executor_dependency(self):
        source = (
            PROJECT_ROOT / "src" / "map_handlers" / "malwarfare_map_handler.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("malwarfate_ocr_processor", source)
        self.assertNotIn("ThreadPoolExecutor", source)
        self.assertNotIn("_post_process_n_value", source)

    def test_runtime_manifest_files_exist_and_default_engine_loads(self):
        manifest_path = (
            PROJECT_ROOT / "resources" / "malwarfare" / "runtime_bundle_manifest.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for relative_path in manifest["python_files"] + manifest["resource_files"]:
            self.assertTrue((PROJECT_ROOT / relative_path).is_file(), relative_path)

        engine = MalwarfareOcrProcessor.from_default_resources()
        self.assertIsInstance(engine, MalwarfareOcrProcessor)

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


if __name__ == "__main__":
    unittest.main()
