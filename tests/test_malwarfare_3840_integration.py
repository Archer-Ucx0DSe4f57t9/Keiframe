from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

import numpy as np

from src import config
from src.game_state_service import _capture_game_screen, state
from src.game_time_handler import update_game_time
from src.malwarfare.ocr_processor import MalwarfareOcrResult
from src.map_handlers import map_loader
from src.map_handlers.IdentifyMap import identify_map
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

    def process_canonical_3840(
        self,
        frame,
        *,
        rois,
        count_color_profile,
    ):
        self.calls.append((frame.shape, rois, count_color_profile))
        if self.error is not None:
            raise self.error
        if len(self.results) > 1:
            return self.results.pop(0)
        return self.results[0]

    def recognize_count_canonical_3840(
        self,
        frame,
        *,
        count_rect,
        count_color_profile,
    ):
        self.calls.append(
            (frame.shape, count_rect.y, count_color_profile, "count")
        )
        if self.error is not None:
            raise self.error
        result = self.results[0]
        return SimpleNamespace(
            value=result.count,
            present=result.count is not None,
            best_score=1.0 if result.count is not None else 0.0,
            raw_prediction=(
                f"c{result.count}" if result.count is not None else "c0"
            ),
        )

    def recognize_status_canonical_3840(
        self,
        frame,
        *,
        time_rect,
        paused_rect,
    ):
        self.calls.append((frame.shape, time_rect.y, paused_rect.y, "status"))
        if self.error is not None:
            raise self.error
        result = self.results.pop(0) if len(self.results) > 1 else self.results[0]
        return SimpleNamespace(
            raw_time_presence=result.time is not None,
            raw_time_prediction=result.time,
            production_time_first_time=result.time,
            raw_paused_prediction=result.paused,
            production_time_first_paused=result.paused,
        )


class ColorRouter:
    def __init__(self, results_by_color, *, status=None):
        self.results_by_color = dict(results_by_color)
        self.status = status or MalwarfareOcrResult(None, None, False)
        self.calls = []

    def process(self, frame, *, ui_profile, count_color_profile):
        self.calls.append((frame.shape, ui_profile, count_color_profile))
        return self.results_by_color[count_color_profile]

    def recognize_count_canonical_3840(
        self,
        frame,
        *,
        count_rect,
        count_color_profile,
    ):
        result = self.results_by_color[count_color_profile]
        self.calls.append(
            (frame.shape, count_rect.y, count_color_profile, "count")
        )
        return SimpleNamespace(
            value=result.count,
            present=result.count is not None,
            best_score=1.0 if result.count is not None else 0.1,
            raw_prediction=(
                f"c{result.count}" if result.count is not None else "c0"
            ),
        )

    def recognize_status_canonical_3840(
        self,
        frame,
        *,
        time_rect,
        paused_rect,
    ):
        self.calls.append((frame.shape, time_rect.y, paused_rect.y, "status"))
        return SimpleNamespace(
            raw_time_presence=self.status.time is not None,
            raw_time_prediction=self.status.time,
            production_time_first_time=self.status.time,
            raw_paused_prediction=self.status.paused,
            production_time_first_paused=self.status.paused,
        )


class ProfileRouter:
    def __init__(self, count_results=None, status_results=None):
        self.count_results = dict(count_results or {})
        self.status_results = dict(status_results or {})
        self.count_calls = []
        self.status_calls = []

    def recognize_count_canonical_3840(
        self,
        frame,
        *,
        count_rect,
        count_color_profile,
    ):
        key = (count_rect.y, count_color_profile)
        self.count_calls.append(key)
        return self.count_results.get(
            key,
            SimpleNamespace(
                value=None,
                present=False,
                best_score=0.05,
                raw_prediction="c0",
            ),
        )

    def recognize_status_canonical_3840(
        self,
        frame,
        *,
        time_rect,
        paused_rect,
    ):
        self.status_calls.append((time_rect.y, paused_rect.y))
        result = self.status_results.get(
            time_rect.y,
            MalwarfareOcrResult(None, None, False),
        )
        return SimpleNamespace(
            raw_time_presence=result.time is not None,
            raw_time_prediction=result.time,
            production_time_first_time=result.time,
            raw_paused_prediction=result.paused,
            production_time_first_paused=result.paused,
        )


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

    @classmethod
    def _probe_frame(cls, color, *, tied_color=None):
        frame = cls.canonical.copy()
        bgr_colors = {
            "green": (0, 255, 0),
            "blue": (255, 0, 0),
            "orange": (0, 128, 255),
        }
        x0, y0, x1, y1 = MalwarfareMapHandler.COUNT_PROBE_ROI
        if tied_color is None:
            frame[y0:y1, x0:x1] = bgr_colors[color]
        else:
            midpoint = x0 + (x1 - x0) // 2
            frame[y0:y1, x0:midpoint] = bgr_colors[color]
            frame[y0:y1, midpoint:x1] = bgr_colors[tied_color]
        return frame

    @staticmethod
    def _color_router(*, green=None, blue=None, orange=None, status=None):
        return ColorRouter(
            {
                "green": green or MalwarfareOcrResult(None, None, False),
                "blue": blue or MalwarfareOcrResult(None, None, False),
                "orange": orange or MalwarfareOcrResult(None, None, False),
            },
            status=status,
        )

    def test_fresh_3840_start_does_not_use_hsv_to_resolve_multiple_counts(self):
        router = self._color_router(
            blue=MalwarfareOcrResult(0, "135", False),
            orange=MalwarfareOcrResult(2, "135", False),
        )
        handler = MalwarfareMapHandler(
            ocr_processor=FakeOcr(),
            runtime_router=router,
            enable_3840_runtime=True,
        )
        self.assertIsNone(handler._current_ui_profile)
        self.assertIsNone(handler._detected_count_color)

        handler._process_frame(
            self._probe_frame("blue"),
            native_frame=self.native_3840,
            now=0.0,
        )

        self.assertIsNone(handler._current_ui_profile)
        self.assertIsNone(handler._detected_count_color)
        self.assertIsNone(handler.get_latest_data())
        diagnostics = handler.get_runtime_diagnostics()
        self.assertTrue(diagnostics["normal_hsv_candidate"])
        self.assertFalse(diagnostics["normal_ui_accepted"])
        self.assertIsNone(diagnostics["selected_count_color"])
        self.assertEqual(0, diagnostics["per_color_count_results"]["blue"]["count"])
        self.assertEqual(2, diagnostics["per_color_count_results"]["orange"]["count"])
        self.assertEqual("ui_profile_ambiguous", diagnostics["first_blocking_condition"])

    def test_3840_scans_all_profiles_and_selects_replay_from_count_evidence(self):
        normal_count_y = 72
        replay_count_y = normal_count_y + 49
        replay_time_y = 73 + 49
        router = ProfileRouter(
            count_results={
                (normal_count_y, "blue"): SimpleNamespace(
                    value=None,
                    present=False,
                    best_score=0.117,
                    raw_prediction="c0",
                ),
                (replay_count_y, "green"): SimpleNamespace(
                    value=0,
                    present=True,
                    best_score=0.99,
                    raw_prediction="c0",
                ),
            },
            status_results={
                replay_time_y: MalwarfareOcrResult(None, "135", False),
            },
        )
        handler = MalwarfareMapHandler(
            ocr_processor=FakeOcr(),
            runtime_router=router,
            enable_3840_runtime=True,
        )
        frame = self._probe_frame("blue")
        x0, y0, x1, y1 = MalwarfareMapHandler.COUNT_PROBE_ROI
        replay_offset = MalwarfareMapHandler.UI_PROFILE_OFFSETS["Replay"]
        frame[y0 + replay_offset : y1 + replay_offset, x0:x1] = (0, 255, 0)

        handler._process_frame(
            frame,
            native_frame=self.native_3840,
            now=0.0,
        )

        diagnostics = handler.get_runtime_diagnostics()
        self.assertEqual("Replay", diagnostics["selected_ui_profile"])
        self.assertEqual(49, diagnostics["selected_y_offset"])
        self.assertEqual("green", diagnostics["selected_count_color"])
        self.assertEqual(0, diagnostics["raw_count"])
        self.assertEqual((172, 121, 219, 152), diagnostics["selected_rois"]["count"])
        self.assertEqual((232, 122, 285, 151), diagnostics["selected_rois"]["time"])
        self.assertEqual((204, 120, 257, 152), diagnostics["selected_rois"]["paused"])
        self.assertEqual(6, len(router.status_calls))
        self.assertEqual(
            {"lang": handler.lang, "n": 0, "time": "1:35", "is_paused": False},
            handler.get_latest_data(),
        )
        normal_blue = diagnostics["profile_scans"]["Normal"][
            "per_color_count_results"
        ]["blue"]
        self.assertFalse(normal_blue["present"])
        self.assertEqual("c0", normal_blue["raw_prediction"])

    def test_3840_multiple_profile_count_hits_remain_unknown(self):
        router = ProfileRouter(
            count_results={
                (72, "blue"): SimpleNamespace(
                    value=1,
                    present=True,
                    best_score=0.9,
                    raw_prediction="c1",
                ),
                (121, "green"): SimpleNamespace(
                    value=2,
                    present=True,
                    best_score=0.9,
                    raw_prediction="c2",
                ),
            }
        )
        handler = MalwarfareMapHandler(
            ocr_processor=FakeOcr(),
            runtime_router=router,
            enable_3840_runtime=True,
        )
        frame = self._probe_frame("blue")
        x0, y0, x1, y1 = MalwarfareMapHandler.COUNT_PROBE_ROI
        offset = MalwarfareMapHandler.UI_PROFILE_OFFSETS["Replay"]
        frame[y0 + offset : y1 + offset, x0:x1] = (0, 255, 0)

        handler._process_frame(frame, native_frame=self.native_3840, now=0.0)

        diagnostics = handler.get_runtime_diagnostics()
        self.assertIsNone(diagnostics["selected_ui_profile"])
        self.assertEqual(2, len(diagnostics["candidate_results"]))
        self.assertEqual("ui_profile_ambiguous", diagnostics["first_blocking_condition"])
        self.assertIsNone(handler.get_latest_data())

    def test_fresh_3840_start_exposes_zero_hsv_and_runs_time_diagnostic(self):
        router = self._color_router(
            status=MalwarfareOcrResult(None, "135", False)
        )
        handler = MalwarfareMapHandler(
            ocr_processor=FakeOcr(),
            runtime_router=router,
            enable_3840_runtime=True,
        )

        handler._process_frame(
            self.canonical,
            native_frame=self.native_3840,
            now=0.0,
        )

        diagnostics = handler.get_runtime_diagnostics()
        self.assertEqual(
            {"green": 0, "blue": 0, "orange": 0},
            diagnostics["hsv_count_probe_pixels"],
        )
        self.assertFalse(diagnostics["normal_ui_accepted"])
        self.assertFalse(diagnostics["normal_hsv_candidate"])
        self.assertEqual("135", diagnostics["raw_time"])
        self.assertTrue(diagnostics["raw_time_present"])
        self.assertIsNone(diagnostics["latest_time"])
        self.assertEqual("ui_profile_not_confirmed", diagnostics["first_blocking_condition"])
        self.assertIsNone(handler.get_latest_data())

    def test_fresh_3840_start_exposes_zero_count_candidates_without_fake_count(self):
        router = self._color_router(
            status=MalwarfareOcrResult(None, None, True)
        )
        handler = MalwarfareMapHandler(
            ocr_processor=FakeOcr(),
            runtime_router=router,
            enable_3840_runtime=True,
        )

        handler._process_frame(
            self._probe_frame("blue"),
            native_frame=self.native_3840,
            now=0.0,
        )

        diagnostics = handler.get_runtime_diagnostics()
        self.assertIsNone(diagnostics["ui_profile"])
        self.assertIsNone(diagnostics["count_color"])
        self.assertIsNone(diagnostics["latest_count"])
        self.assertTrue(diagnostics["raw_paused"])
        self.assertIsNone(diagnostics["latest_paused"])
        self.assertEqual("ui_profile_not_confirmed", diagnostics["first_blocking_condition"])
        self.assertIsNone(handler.get_latest_data())

    def test_fresh_3840_start_exposes_ambiguous_hsv_and_runs_paused_diagnostic(self):
        router = self._color_router(
            green=MalwarfareOcrResult(1, None, True),
            blue=MalwarfareOcrResult(3, None, True),
            status=MalwarfareOcrResult(None, None, True),
        )
        handler = MalwarfareMapHandler(
            ocr_processor=FakeOcr(),
            runtime_router=router,
            enable_3840_runtime=True,
        )
        tied = self._probe_frame("green", tied_color="blue")
        x0, y0, x1, y1 = MalwarfareMapHandler.COUNT_PROBE_ROI
        tied[y0:y1, x1 - 1] = (0, 0, 0)

        handler._process_frame(
            tied,
            native_frame=self.native_3840,
            now=0.0,
        )

        diagnostics = handler.get_runtime_diagnostics()
        self.assertTrue(diagnostics["normal_hsv_candidate"])
        self.assertFalse(diagnostics["normal_ui_accepted"])
        self.assertIsNone(diagnostics["selected_count_color"])
        self.assertEqual("ui_profile_ambiguous", diagnostics["first_blocking_condition"])
        self.assertTrue(diagnostics["raw_paused"])
        self.assertIsNone(handler.get_latest_data())

    def test_diagnostic_overrides_are_explicit_and_do_not_guess_count(self):
        router = self._color_router(
            status=MalwarfareOcrResult(None, "120", False)
        )
        handler = MalwarfareMapHandler(
            ocr_processor=FakeOcr(),
            runtime_router=router,
            enable_3840_runtime=True,
            diagnostic_ui_profile_override="Normal",
            diagnostic_count_color_override="orange",
        )

        handler._process_frame(
            self.canonical,
            native_frame=self.native_3840,
            now=0.0,
        )

        diagnostics = handler.get_runtime_diagnostics()
        self.assertIsNone(diagnostics["ui_profile"])
        self.assertIsNone(diagnostics["count_color"])
        self.assertIsNone(diagnostics["latest_count"])
        self.assertEqual("120", diagnostics["raw_time"])
        self.assertIsNone(handler.get_latest_data())

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
        self.assertEqual((1080, 1920, 3), router.calls[0][0])
        self.assertEqual("green", router.calls[0][2])
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
        self.assertEqual(1, sum(call[-1] == "count" for call in router.calls))
        self.assertEqual(3, sum(call[-1] == "status" for call in router.calls))

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

    def test_3840_count_failure_does_not_block_status_diagnostic(self):
        router = ProfileRouter(
            status_results={73: MalwarfareOcrResult(None, "135", False)}
        )
        handler = self._known_handler(FakeOcr(), enabled=True, router=router)

        with mock.patch.object(
            router,
            "recognize_count_canonical_3840",
            side_effect=ValueError("count failed"),
        ):
            handler._process_frame(
                self.canonical,
                native_frame=self.native_3840,
                now=0.0,
            )

        self.assertEqual(1, len(router.status_calls))
        self.assertEqual(
            {"lang": handler.lang, "n": 2, "time": "1:35", "is_paused": False},
            handler.get_latest_data(),
        )

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

    def test_capture_pauses_when_game_loses_focus_and_resumes_after_focus(self):
        fake_sct = mock.Mock()
        fake_sct.grab.return_value = object()
        canonical = np.zeros((1080, 1920, 3), dtype=np.uint8)
        state.screenshot_timestamp = 123.0

        with mock.patch(
            "src.game_state_service.is_game_active",
            return_value=False,
        ):
            _capture_game_screen(fake_sct)

        fake_sct.grab.assert_not_called()
        self.assertEqual(123.0, state.screenshot_timestamp)

        with (
            mock.patch("src.game_state_service.is_game_active", return_value=True),
            mock.patch(
                "src.game_state_service.get_sc2_window_geometry",
                return_value=(10, 20, 2560, 1440),
            ),
            mock.patch(
                "src.game_state_service.np.array",
                return_value=np.zeros((1, 1, 4), dtype=np.uint8),
            ),
            mock.patch(
                "src.game_state_service.cv2.cvtColor",
                return_value=np.zeros((1440, 2560, 3), dtype=np.uint8),
            ),
            mock.patch(
                "src.game_state_service.cv2.resize",
                return_value=canonical,
            ),
            mock.patch.object(config, "enable_malwarfare_3840_runtime", True),
        ):
            _capture_game_screen(fake_sct)

        fake_sct.grab.assert_called_once()
        self.assertGreater(state.screenshot_timestamp, 123.0)
        self.assertEqual((1080, 1920, 3), state.latest_screenshot.shape)
        self.assertIsNone(state.latest_malwarfare_native_screenshot)

    def test_observed_five_player_editor_signature_identifies_malwarfare(self):
        players = [
            {"id": 1, "name": "本地玩家", "type": "user"},
            {"id": 3, "name": "净化者全息投影", "type": "computer"},
            {"id": 4, "name": "净化者全息投影", "type": "computer"},
            {"id": 5, "name": "麦加利斯", "type": "computer"},
            {"id": 6, "name": "中立奖励", "type": "computer"},
        ]

        self.assertEqual("净网行动", identify_map(players))

    def test_standard_six_player_malwarfare_rule_is_preserved(self):
        players = [
            {"id": 1, "name": "玩家一", "type": "user"},
            {"id": 2, "name": "玩家二", "type": "user"},
            {"id": 3, "name": "净化者全息投影", "type": "computer"},
            {"id": 4, "name": "净化者全息投影", "type": "computer"},
            {"id": 5, "name": "麦加利斯", "type": "computer"},
            {"id": 6, "name": "中立奖励", "type": "computer"},
        ]

        self.assertEqual("净网行动", identify_map(players))

    def test_arbitrary_or_reordered_five_player_game_does_not_match(self):
        arbitrary = [
            {"id": 1, "name": "玩家一", "type": "user"},
            {"id": 2, "name": "玩家二", "type": "user"},
            {"id": 3, "name": "Amon", "type": "computer"},
            {"id": 4, "name": "Amon", "type": "computer"},
            {"id": 5, "name": "Neutral", "type": "computer"},
        ]
        self.assertIsNone(identify_map(arbitrary))

        reordered = [
            {"id": 1, "name": "本地玩家", "type": "user"},
            {"id": 3, "name": "净化者全息投影", "type": "computer"},
            {"id": 4, "name": "麦加利斯", "type": "computer"},
            {"id": 5, "name": "净化者全息投影", "type": "computer"},
            {"id": 6, "name": "中立奖励", "type": "computer"},
        ]
        self.assertIsNone(identify_map(reordered))

    def test_manual_malwarfare_selection_creates_and_starts_handler(self):
        class Handler:
            def __init__(self, game_state):
                self.game_state = game_state
                self.reset_called = False
                self.start_called = False

            def reset(self):
                self.reset_called = True

            def start(self):
                self.start_called = True

            def get_runtime_diagnostics(self):
                return {
                    "runtime_enabled": True,
                    "handler_running_flag": self.start_called,
                    "worker_alive": self.start_called,
                }

        class Widget:
            def __init__(self):
                self.visible = False

            def show(self):
                self.visible = True

            def hide(self):
                self.visible = False

            def setText(self, _value):
                pass

        combo_box = mock.Mock()
        combo_box.currentText.return_value = "净网行动"
        combo_box.count.return_value = 0
        logger = mock.Mock()
        previous_map = state.current_selected_map
        window = SimpleNamespace(
            toast_manager=SimpleNamespace(clear_all_alerts=lambda: None),
            manual_map_selection=True,
            auto_map_variant_switching=False,
            combo_box=combo_box,
            logger=logger,
            malwarfare_handler=None,
            game_state=SimpleNamespace(),
            table_area=SimpleNamespace(),
            countdown_label=Widget(),
            map_version_group=Widget(),
            version_buttons=[],
            maps_db=object(),
        )

        try:
            with (
                mock.patch.object(map_loader, "MalwarfareMapHandler", Handler),
                mock.patch.object(
                    map_loader,
                    "MapwarfareEventManager",
                    return_value=object(),
                ),
                mock.patch.object(map_loader, "apply_malwarfare_table_columns"),
                mock.patch.object(map_loader, "load_map_by_name", return_value=[]),
            ):
                map_loader.handle_map_selection(window, "净网行动")
                selected_map = state.current_selected_map
        finally:
            state.current_selected_map = previous_map

        self.assertEqual("净网行动", selected_map)
        self.assertTrue(window.is_map_Malwarfare)
        self.assertTrue(window.malwarfare_handler.reset_called)
        self.assertTrue(window.malwarfare_handler.start_called)

    def test_published_count_time_and_pause_state_enters_event_manager(self):
        class Label:
            def __init__(self):
                self.visible = False
                self.text = None

            def isVisible(self):
                return self.visible

            def show(self):
                self.visible = True

            def hide(self):
                self.visible = False

            def setText(self, value):
                self.text = value

        event_manager = mock.Mock()
        handler = mock.Mock()
        handler.get_latest_data.return_value = {
            "lang": "zh",
            "n": 0,
            "time": "2:53",
            "is_paused": False,
        }
        window = SimpleNamespace(
            logger=mock.Mock(),
            game_state=SimpleNamespace(game_time=10, is_in_game=True),
            time_label=Label(),
            countdown_label=Label(),
            current_time="",
            _last_dispatch_game_second=None,
            map_event_manager=event_manager,
            is_map_Malwarfare=True,
            malwarfare_handler=handler,
        )

        update_game_time(window)

        self.assertEqual("(2:53)", window.countdown_label.text)
        event_manager.update_events.assert_called_once_with(0, 173, True)


if __name__ == "__main__":
    unittest.main()
