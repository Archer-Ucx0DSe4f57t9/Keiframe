import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from src import config
from src.event_managers_and_notifiers.enemy_composition_notifier import (
    EnemyCompositionNotificationState,
    EnemyCompositionNotifier,
)
from src.game_readers.enemy_composition_recognizer import (
    EnemyCompositionConfig,
    EnemyCompositionRecognition,
    EnemyCompositionRecognizer,
    EnemyCompositionState,
)
from src.game_readers.enemy_composition_scheduler import (
    EnemyCompositionScheduler,
)
from src.recognition_controller import RecognitionController


class _FakePresenter:
    def __init__(self):
        self.messages = []
        self.visible = False
        self.hide_count = 0

    def setAttribute(self, *_args):
        pass

    def move(self, *_args):
        pass

    def resize(self, *_args):
        pass

    def setFixedHeight(self, *_args):
        pass

    def update_message(self, message, color, **kwargs):
        self.messages.append((message, color, kwargs))

    def show(self):
        self.visible = True

    def raise_(self):
        pass

    def hide_alert(self):
        self.visible = False
        self.hide_count += 1


class _ScheduledCallbacks:
    def __init__(self):
        self.calls = []

    def __call__(self, delay_ms, callback):
        self.calls.append((delay_ms, callback))


def _recognition(state, streak=0, composition=None):
    return EnemyCompositionRecognition(
        state=state,
        enemy_composition=composition,
        panel_found_streak=streak,
        collected_crops=streak,
        ocr_results=0,
        valid_results=0,
    )


class EnemyCompositionNotifierTests(unittest.TestCase):
    def setUp(self):
        self.presenter = _FakePresenter()
        self.callbacks = _ScheduledCallbacks()
        self.game_state = SimpleNamespace(enemy_composition=None)
        self.parent = SimpleNamespace(game_state=self.game_state)
        self.notifier = EnemyCompositionNotifier(
            self.parent,
            message_presenter=self.presenter,
            geometry_provider=lambda: (10, 20, 1920, 1080),
            single_shot=self.callbacks,
        )

    def test_no_panel_found_remains_silent(self):
        self.assertEqual(
            self.notifier.state,
            EnemyCompositionNotificationState.IDLE,
        )
        self.assertEqual(self.presenter.messages, [])
        self.assertEqual(self.callbacks.calls, [])

    def test_panel_found_starts_one_non_extending_attempt(self):
        self.assertTrue(self.notifier.handle_panel_found())
        self.assertFalse(self.notifier.handle_panel_found())

        self.assertEqual(
            self.notifier.state,
            EnemyCompositionNotificationState.RECOGNIZING,
        )
        self.assertEqual(self.presenter.messages[-1][0], "正在识别中")
        self.assertEqual(self.presenter.messages[-1][1], "rgb(255,255,255)")
        self.assertIsNone(
            self.presenter.messages[-1][2]["sound_filename"]
        )
        self.assertEqual(self.callbacks.calls[0][0], 8_000)
        self.assertEqual(len(self.callbacks.calls), 1)

    def test_timeout_shows_failure_then_returns_to_idle(self):
        self.notifier.handle_panel_found()
        self.callbacks.calls[0][1]()

        self.assertEqual(
            self.notifier.state,
            EnemyCompositionNotificationState.FAILED,
        )
        self.assertEqual(
            self.presenter.messages[-1][0],
            "识别失败，请将鼠标悬停到敌方位置重试",
        )
        self.assertIsNone(self.game_state.enemy_composition)
        self.assertEqual(self.callbacks.calls[1][0], 5_000)

        self.callbacks.calls[1][1]()
        self.assertEqual(
            self.notifier.state,
            EnemyCompositionNotificationState.IDLE,
        )
        self.assertFalse(self.presenter.visible)

    def test_retry_replaces_failure_and_old_hide_is_ignored(self):
        self.notifier.handle_panel_found()
        self.callbacks.calls[0][1]()
        old_failure_hide = self.callbacks.calls[1][1]

        self.assertTrue(self.notifier.handle_panel_found())
        hide_count = self.presenter.hide_count
        old_failure_hide()

        self.assertEqual(
            self.notifier.state,
            EnemyCompositionNotificationState.RECOGNIZING,
        )
        self.assertEqual(self.presenter.messages[-1][0], "正在识别中")
        self.assertEqual(self.presenter.hide_count, hide_count)
        self.assertTrue(self.presenter.visible)

    def test_success_replaces_status_and_invalidates_old_timeout(self):
        self.notifier.handle_panel_found()
        old_timeout = self.callbacks.calls[0][1]
        self.game_state.enemy_composition = "Disruptive Artillery"

        with patch.object(config, "current_game_language", "zh"):
            self.assertTrue(self.notifier.show("Disruptive Artillery"))
        old_timeout()

        self.assertEqual(
            self.notifier.state,
            EnemyCompositionNotificationState.CONFIRMED,
        )
        self.assertEqual(self.presenter.messages[-1][0], "袭扰炮击")
        self.assertNotEqual(
            self.presenter.messages[-1][0],
            "识别失败，请将鼠标悬停到敌方位置重试",
        )
        self.assertEqual(self.callbacks.calls[1][0], 5_000)

    def test_success_uses_canonical_name_in_english(self):
        self.notifier.handle_panel_found()
        self.game_state.enemy_composition = "Dominion Battlegroup"

        with patch.object(config, "current_game_language", "en"):
            self.assertTrue(self.notifier.show("Dominion Battlegroup"))

        self.assertEqual(
            self.presenter.messages[-1][0],
            "Dominion Battlegroup",
        )

    def test_expiry_and_reset_invalidate_pending_timeout(self):
        self.notifier.handle_panel_found()
        old_timeout = self.callbacks.calls[0][1]

        self.notifier.handle_expired()
        old_timeout()
        self.assertEqual(
            self.notifier.state,
            EnemyCompositionNotificationState.EXPIRED,
        )
        self.assertFalse(self.presenter.visible)

        self.notifier.reset()
        self.assertEqual(
            self.notifier.state,
            EnemyCompositionNotificationState.IDLE,
        )
        self.assertTrue(self.notifier.handle_panel_found())

    def test_timeout_race_with_recognizer_expiry_stays_silent(self):
        self.notifier.handle_panel_found()
        self.parent.enemy_composition_recognizer = SimpleNamespace(
            state=EnemyCompositionState.EXPIRED
        )

        self.callbacks.calls[0][1]()

        self.assertEqual(
            self.notifier.state,
            EnemyCompositionNotificationState.EXPIRED,
        )
        self.assertNotEqual(
            self.presenter.messages[-1][0],
            "识别失败，请将鼠标悬停到敌方位置重试",
        )
        self.assertFalse(self.presenter.visible)

    def test_already_confirmed_never_starts_recognizing(self):
        self.game_state.enemy_composition = "Disruptive Artillery"
        self.assertFalse(self.notifier.handle_panel_found())
        self.assertEqual(self.presenter.messages, [])


class _FakeRecognizer:
    def __init__(self, results):
        self.results = list(results)
        self.state = EnemyCompositionState.SEARCHING
        self.reset_count = 0

    def update(self, **_kwargs):
        result = self.results.pop(0)
        self.state = result.state
        return result

    def reset(self):
        self.reset_count += 1
        self.state = EnemyCompositionState.SEARCHING


class EnemyCompositionSchedulerStatusTests(unittest.TestCase):
    def _state(self):
        return SimpleNamespace(
            is_in_game=True,
            enemy_composition=None,
            enemy_race="Protoss",
            screenshot_lock=threading.Lock(),
            latest_screenshot=np.zeros((10, 10, 3), dtype=np.uint8),
            screenshot_timestamp=1.0,
            game_time=20.0,
        )

    def test_no_panel_is_silent_and_continuous_panel_emits_once(self):
        panel_events = []
        recognizer = _FakeRecognizer(
            [
                _recognition(EnemyCompositionState.SEARCHING),
                _recognition(EnemyCompositionState.COLLECTING, streak=1),
                _recognition(EnemyCompositionState.COLLECTING, streak=2),
            ]
        )
        scheduler = EnemyCompositionScheduler(
            recognizer,
            self._state(),
            panel_found_callback=panel_events.append,
        )

        scheduler.update()
        self.assertEqual(panel_events, [])
        scheduler.update()
        scheduler.update()
        self.assertEqual(panel_events, [0])

    def test_new_panel_sequence_after_missing_frame_emits_retry(self):
        panel_events = []
        recognizer = _FakeRecognizer(
            [
                _recognition(EnemyCompositionState.COLLECTING, streak=1),
                _recognition(EnemyCompositionState.SEARCHING),
                _recognition(EnemyCompositionState.COLLECTING, streak=1),
            ]
        )
        scheduler = EnemyCompositionScheduler(
            recognizer,
            self._state(),
            panel_found_callback=panel_events.append,
        )

        scheduler.update()
        scheduler.update()
        scheduler.update()
        self.assertEqual(panel_events, [0, 0])

    def test_expiry_and_confirmation_callbacks_are_lifecycle_events(self):
        order = []
        state = self._state()
        scheduler = EnemyCompositionScheduler(
            _FakeRecognizer(
                [
                    _recognition(
                        EnemyCompositionState.CONFIRMED,
                        streak=1,
                        composition="Disruptive Artillery",
                    )
                ]
            ),
            state,
            panel_found_callback=lambda generation: order.append(
                ("panel", generation)
            ),
            confirmation_callback=lambda composition: order.append(
                ("confirmed", composition)
            ),
        )
        scheduler.update()

        self.assertEqual(
            order,
            [("panel", 0), ("confirmed", "Disruptive Artillery")],
        )
        self.assertEqual(state.enemy_composition, "Disruptive Artillery")

        expiry_events = []
        expiry_scheduler = EnemyCompositionScheduler(
            _FakeRecognizer(
                [_recognition(EnemyCompositionState.EXPIRED)]
            ),
            self._state(),
            expiry_callback=expiry_events.append,
        )
        expiry_scheduler.update()
        self.assertEqual(expiry_events, [0])

    def test_reset_changes_generation_and_rearms_events(self):
        panel_events = []
        recognizer = _FakeRecognizer(
            [_recognition(EnemyCompositionState.COLLECTING, streak=1)]
        )
        scheduler = EnemyCompositionScheduler(
            recognizer,
            self._state(),
            panel_found_callback=panel_events.append,
        )
        scheduler.update()
        scheduler.reset()

        self.assertEqual(panel_events, [0])
        self.assertEqual(scheduler.generation, 1)
        self.assertEqual(recognizer.reset_count, 1)


class EnemyCompositionRecognizerRetryTests(unittest.TestCase):
    def test_failed_hover_is_discarded_before_a_new_panel_sequence(self):
        detections = iter(
            [
                {"found": True, "title_crop": np.ones((4, 4, 3))},
                {"found": True, "title_crop": np.ones((4, 4, 3))},
                {"found": True, "title_crop": np.ones((4, 4, 3))},
                {"found": False},
                {"found": True, "title_crop": np.ones((4, 4, 3))},
            ]
        )
        recognizer = EnemyCompositionRecognizer(
            panel_detector=lambda _image: next(detections),
            ocr_provider=lambda _crop: "unmatched text",
            matcher=lambda _query, _race: None,
            config=EnemyCompositionConfig(),
        )
        frame = np.zeros((10, 10, 3), dtype=np.uint8)

        for timestamp in range(1, 4):
            result = recognizer.update(frame, timestamp, 20, "Protoss")
        self.assertEqual(result.state, EnemyCompositionState.CONFIRMING)

        result = recognizer.update(frame, 4, 20, "Protoss")
        self.assertEqual(result.state, EnemyCompositionState.SEARCHING)
        self.assertEqual(result.panel_found_streak, 0)
        self.assertEqual(result.ocr_results, 0)

        result = recognizer.update(frame, 5, 20, "Protoss")
        self.assertEqual(result.state, EnemyCompositionState.COLLECTING)
        self.assertEqual(result.panel_found_streak, 1)

    def test_default_expiry_is_after_300_seconds(self):
        recognizer = EnemyCompositionRecognizer(
            panel_detector=lambda _image: {"found": False},
        )
        frame = np.zeros((10, 10, 3), dtype=np.uint8)

        at_limit = recognizer.update(frame, 1, 300, "Protoss")
        self.assertEqual(at_limit.state, EnemyCompositionState.SEARCHING)
        expired = recognizer.update(frame, 2, 300.01, "Protoss")
        self.assertEqual(expired.state, EnemyCompositionState.EXPIRED)


class _ControllerNotifier:
    def __init__(self):
        self.panel_found_count = 0
        self.expired_count = 0

    def handle_panel_found(self):
        self.panel_found_count += 1

    def handle_expired(self):
        self.expired_count += 1


class RecognitionControllerStatusTests(unittest.TestCase):
    def _window(self):
        notifier = _ControllerNotifier()
        scheduler = SimpleNamespace(generation=4)
        game_state = SimpleNamespace(
            enemy_composition=None,
            enemy_race="Protoss",
        )
        return SimpleNamespace(
            _safe_exiting=False,
            game_state=game_state,
            enemy_composition_scheduler=scheduler,
            enemy_composition_ocr_provider=object(),
            enemy_composition_notifier=notifier,
        )

    def test_only_current_enabled_unconfirmed_event_reaches_notifier(self):
        window = self._window()
        controller = RecognitionController(window, game_state=window.game_state)

        controller.handle_enemy_composition_panel_found(3)
        self.assertEqual(
            window.enemy_composition_notifier.panel_found_count,
            0,
        )

        window.enemy_composition_ocr_provider = None
        controller.handle_enemy_composition_panel_found(4)
        self.assertEqual(
            window.enemy_composition_notifier.panel_found_count,
            0,
        )

        window.enemy_composition_ocr_provider = object()
        controller.handle_enemy_composition_panel_found(4)
        self.assertEqual(
            window.enemy_composition_notifier.panel_found_count,
            1,
        )

        window.game_state.enemy_composition = "Disruptive Artillery"
        controller.handle_enemy_composition_panel_found(4)
        self.assertEqual(
            window.enemy_composition_notifier.panel_found_count,
            1,
        )

        controller.handle_enemy_composition_expired(4)
        self.assertEqual(window.enemy_composition_notifier.expired_count, 1)


if __name__ == "__main__":
    unittest.main()
