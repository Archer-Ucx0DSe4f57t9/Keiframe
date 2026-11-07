from __future__ import annotations

import unittest
from unittest import mock

import numpy as np

from src import config
from src.game_state_service import _capture_game_screen, state
from src.malwarfare.ocr_processor import MalwarfareOcrResult
from src.map_handlers.malwarfare_map_handler import MalwarfareMapHandler


class FakeOcr:
    def __init__(self, *, count=2, time_value="135", paused=False):
        self.count = count
        self.time_value = time_value
        self.paused = paused
        self.count_calls = []
        self.status_calls = []

    def recognize_count(self, frame, *, ui_profile, count_color_profile):
        self.count_calls.append((frame.shape, ui_profile, count_color_profile))
        return self.count

    def recognize_time_paused(self, frame, *, ui_profile):
        self.status_calls.append((frame.shape, ui_profile))
        return self.time_value, self.paused


class FakeRouter:
    def __init__(self, results=None, error=None):
        self.results = list(
            results or [MalwarfareOcrResult(count=0, time="135", paused=False)]
        )
        self.error = error
        self.calls = []

    def process(
        self,
        frame,
        *,
        ui_profile,
        count_color_profile,
    ):
        self.calls.append((frame.shape, ui_profile, count_color_profile))
        if self.error is not None:
            raise self.error
        if len(self.results) > 1:
            return self.results.pop(0)
        return self.results[0]


class Malwarfare3840IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.canonical = np.zeros((1080, 1920, 3), dtype=np.uint8)
        cls.native_2560 = np.broadcast_to(
            np.zeros((1, 1, 3), dtype=np.uint8),
            (1440, 2560, 3),
        )
        cls.native_3840 = np.broadcast_to(
            np.zeros((1, 1, 3), dtype=np.uint8),
            (2160, 3840, 3),
        )

    @staticmethod
    def _known_handler(old_ocr, *, enabled, router=None):
        handler = MalwarfareMapHandler(
            ocr_processor=old_ocr,
            runtime_router=router,
            enable_3840_runtime=enabled,
        )
        handler._current_ui_profile = "Normal"
        handler._detected_count_color = "green"
        handler._latest_count = 2
        return handler

    def test_default_disabled_keeps_old_path_even_with_native_3840(self):
        old = FakeOcr()
        router = FakeRouter()
        handler = self._known_handler(old, enabled=False, router=router)

        handler._process_frame(
            self.canonical,
            native_frame=self.native_3840,
            now=0.0,
        )

        self.assertEqual([], router.calls)
        self.assertEqual(1, len(old.count_calls))
        self.assertEqual(1, len(old.status_calls))

    def test_enabled_native_3840_routes_and_count_zero_is_preserved(self):
        old = FakeOcr()
        router = FakeRouter(
            [MalwarfareOcrResult(count=0, time="135", paused=False)]
        )
        handler = self._known_handler(old, enabled=True, router=router)

        handler._process_frame(
            self.canonical,
            native_frame=self.native_3840,
            now=0.0,
        )

        self.assertEqual([], old.count_calls)
        self.assertEqual([], old.status_calls)
        self.assertEqual((2160, 3840, 3), router.calls[0][0])
        self.assertEqual(
            {"lang": handler.lang, "n": 0, "time": "1:35", "is_paused": False},
            handler.get_latest_data(),
        )

    def test_enabled_native_2560_and_other_sizes_keep_old_path(self):
        for native in (
            self.native_2560,
            np.zeros((1080, 1920, 3), dtype=np.uint8),
            np.zeros((720, 1280, 3), dtype=np.uint8),
        ):
            with self.subTest(shape=native.shape):
                old = FakeOcr()
                router = FakeRouter()
                handler = self._known_handler(old, enabled=True, router=router)
                handler._process_frame(
                    self.canonical,
                    native_frame=native,
                    now=0.0,
                )
                self.assertEqual([], router.calls)
                self.assertEqual(1, len(old.count_calls))
                self.assertEqual(1, len(old.status_calls))

    def test_3840_pause_resume_retains_state_machine_contract(self):
        router = FakeRouter(
            [
                MalwarfareOcrResult(2, "135", False),
                MalwarfareOcrResult(2, None, True),
                MalwarfareOcrResult(2, "134", False),
            ]
        )
        handler = self._known_handler(FakeOcr(), enabled=True, router=router)
        expected = [("1:35", False), ("1:35", True), ("1:34", False)]

        for now, (expected_time, expected_paused) in zip(
            (0.0, 0.13, 0.26),
            expected,
        ):
            handler._process_frame(
                self.canonical,
                native_frame=self.native_3840,
                now=now,
            )
            result = handler.get_latest_data()
            self.assertEqual(expected_time, result["time"])
            self.assertEqual(expected_paused, result["is_paused"])

    def test_3840_execution_error_does_not_call_old_ocr(self):
        old = FakeOcr()
        handler = self._known_handler(
            old,
            enabled=True,
            router=FakeRouter(error=ValueError("corrupt runtime")),
        )

        handler._process_frame(
            self.canonical,
            native_frame=self.native_3840,
            now=0.0,
        )

        self.assertEqual([], old.count_calls)
        self.assertEqual([], old.status_calls)

    def test_missing_native_3840_frame_does_not_fall_back(self):
        old = FakeOcr()
        handler = self._known_handler(
            old,
            enabled=True,
            router=FakeRouter(),
        )

        handler._process_frame(
            self.canonical,
            native_frame=None,
            native_shape=(2160, 3840, 3),
            now=0.0,
        )

        self.assertEqual([], old.count_calls)
        self.assertEqual([], old.status_calls)

    def test_3840_initialization_failure_is_explicit(self):
        with mock.patch(
            "src.map_handlers.malwarfare_map_handler."
            "Malwarfare3840Runtime.from_default_resources",
            side_effect=ValueError("bundle missing"),
        ):
            with self.assertRaisesRegex(RuntimeError, "不会静默回退"):
                MalwarfareMapHandler(
                    ocr_processor=FakeOcr(),
                    enable_3840_runtime=True,
                )

    def test_capture_preserves_native_3840_only_when_enabled(self):
        fake_sct = mock.Mock()
        fake_sct.grab.return_value = object()
        native = np.broadcast_to(
            np.zeros((1, 1, 3), dtype=np.uint8),
            (2160, 3840, 3),
        )
        canonical = np.zeros((1080, 1920, 3), dtype=np.uint8)
        with (
            mock.patch("src.game_state_service.is_game_active", return_value=True),
            mock.patch(
                "src.game_state_service.get_sc2_window_geometry",
                return_value=(10, 20, 3840, 2160),
            ),
            mock.patch(
                "src.game_state_service.np.array",
                return_value=np.zeros((1, 1, 4), dtype=np.uint8),
            ),
            mock.patch(
                "src.game_state_service.cv2.cvtColor",
                return_value=native,
            ),
            mock.patch(
                "src.game_state_service.cv2.resize",
                return_value=canonical,
            ),
            mock.patch.object(config, "enable_malwarfare_3840_runtime", True),
        ):
            _capture_game_screen(fake_sct)
        self.assertEqual((1080, 1920, 3), state.latest_screenshot.shape)
        self.assertEqual(
            (2160, 3840, 3),
            state.latest_malwarfare_native_screenshot.shape,
        )
        self.assertEqual(
            (2160, 3840, 3),
            state.latest_screenshot_native_shape,
        )

        with (
            mock.patch("src.game_state_service.is_game_active", return_value=True),
            mock.patch(
                "src.game_state_service.get_sc2_window_geometry",
                return_value=(10, 20, 3840, 2160),
            ),
            mock.patch(
                "src.game_state_service.np.array",
                return_value=np.zeros((1, 1, 4), dtype=np.uint8),
            ),
            mock.patch(
                "src.game_state_service.cv2.cvtColor",
                return_value=native,
            ),
            mock.patch(
                "src.game_state_service.cv2.resize",
                return_value=canonical,
            ),
            mock.patch.object(config, "enable_malwarfare_3840_runtime", False),
        ):
            _capture_game_screen(fake_sct)
        self.assertIsNone(state.latest_malwarfare_native_screenshot)


if __name__ == "__main__":
    unittest.main()
