import json
import logging
import os
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PyQt5.QtWidgets import (
    QApplication,
    QGroupBox,
    QTableWidget,
    QTableWidgetItem,
)

from src import config, game_state_service
from src.event_managers_and_notifiers.mutator_manager import MutatorManager
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
from src.game_readers.enemy_composition_unit_advisor import (
    EnemyCompositionUnitAdvisor,
)
from src.map_handlers.map_event_manager import MapEventManager
from src.map_handlers.malwarfare.malwarfare_event_manager import (
    MapwarfareEventManager,
)
from src.recognition_controller import RecognitionController
from src.settings_window.setting_data_handler import SettingsHandler
from src.settings_window.settings_controller import SettingsController
from src.settings_window.settings_window import SettingsWindow


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
        self.previous_enabled = config.ENEMY_COMPOSITION_ENABLED
        config.ENEMY_COMPOSITION_ENABLED = True
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

    def tearDown(self):
        config.ENEMY_COMPOSITION_ENABLED = self.previous_enabled

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

    def test_disable_hides_status_and_old_timeout_stays_silent(self):
        self.assertTrue(self.notifier.handle_panel_found())
        old_timeout = self.callbacks.calls[0][1]

        config.ENEMY_COMPOSITION_ENABLED = False
        self.notifier.reset()
        old_timeout()

        self.assertEqual(
            self.notifier.state,
            EnemyCompositionNotificationState.IDLE,
        )
        self.assertFalse(self.presenter.visible)
        self.assertEqual(
            [message for message, _color, _kwargs in self.presenter.messages],
            ["正在识别中"],
        )
        self.assertFalse(self.notifier.handle_panel_found())
        self.assertFalse(self.notifier.show("Disruptive Artillery"))


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
    def setUp(self):
        self.previous_enabled = config.ENEMY_COMPOSITION_ENABLED
        config.ENEMY_COMPOSITION_ENABLED = True

    def tearDown(self):
        config.ENEMY_COMPOSITION_ENABLED = self.previous_enabled

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

    def test_disabled_gate_precedes_screenshot_lock_and_recognizer(self):
        class _ForbiddenLock:
            def __enter__(self):
                raise AssertionError("disabled scheduler acquired screenshot lock")

            def __exit__(self, *_args):
                return False

        state = self._state()
        state.screenshot_lock = _ForbiddenLock()
        recognizer = _FakeRecognizer([])
        scheduler = EnemyCompositionScheduler(recognizer, state)
        config.ENEMY_COMPOSITION_ENABLED = False

        self.assertFalse(scheduler.update())
        self.assertEqual(recognizer.reset_count, 0)
        self.assertIsNone(state.enemy_composition)


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
    def setUp(self):
        self.previous_enabled = config.ENEMY_COMPOSITION_ENABLED
        config.ENEMY_COMPOSITION_ENABLED = True

    def tearDown(self):
        config.ENEMY_COMPOSITION_ENABLED = self.previous_enabled

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

    def test_disabled_queued_events_never_reach_notifier(self):
        window = self._window()
        window.game_state.enemy_composition = "Disruptive Artillery"
        window.enemy_composition_notifier.show = Mock()
        controller = RecognitionController(window, game_state=window.game_state)
        config.ENEMY_COMPOSITION_ENABLED = False

        controller.handle_enemy_composition_confirmed(
            "Disruptive Artillery"
        )
        controller.handle_enemy_composition_panel_found(4)
        controller.handle_enemy_composition_expired(4)

        window.enemy_composition_notifier.show.assert_not_called()
        self.assertEqual(
            window.enemy_composition_notifier.panel_found_count,
            0,
        )
        self.assertEqual(window.enemy_composition_notifier.expired_count, 0)


class _Signal:
    def __init__(self):
        self.emit = Mock()


class _PerceptionRecognizer:
    def __init__(self):
        self._running = False
        self.attached_scheduler = None
        self.start_count = 0

    def set_enemy_composition_scheduler(self, scheduler):
        self.attached_scheduler = scheduler

    def start(self):
        self._running = True
        self.start_count += 1


def _controller_window(game_state):
    return SimpleNamespace(
        _safe_exiting=False,
        game_state=game_state,
        logger=Mock(),
        mutator_and_enemy_race_recognizer=_PerceptionRecognizer(),
        enemy_composition_notifier=Mock(),
        enemy_composition_confirmed_signal=_Signal(),
        enemy_composition_panel_found_signal=_Signal(),
        enemy_composition_expired_signal=_Signal(),
    )


class RecognitionFeatureToggleTests(unittest.TestCase):
    def setUp(self):
        self.previous_enabled = config.ENEMY_COMPOSITION_ENABLED
        config.ENEMY_COMPOSITION_ENABLED = True

    def tearDown(self):
        config.ENEMY_COMPOSITION_ENABLED = self.previous_enabled

    def test_startup_disabled_skips_provider_without_touching_race_or_mutators(self):
        state = SimpleNamespace(
            enemy_composition=None,
            enemy_race="Protoss",
            active_mutators=["AggressiveDeployment"],
        )
        window = _controller_window(state)
        controller = RecognitionController(window, game_state=state)
        config.ENEMY_COMPOSITION_ENABLED = False

        with patch(
            "src.recognition_controller.create_production_enemy_composition_ocr_provider"
        ) as create_provider:
            self.assertFalse(
                controller.initialize_enemy_composition_recognition()
            )

        create_provider.assert_not_called()
        self.assertIsNone(window.enemy_composition_ocr_provider)
        self.assertIsNone(window.enemy_composition_recognizer)
        self.assertIsNone(window.enemy_composition_scheduler)
        self.assertIsNone(
            window.mutator_and_enemy_race_recognizer.attached_scheduler
        )
        self.assertEqual(state.enemy_race, "Protoss")
        self.assertEqual(state.active_mutators, ["AggressiveDeployment"])

    def test_disable_enable_reuses_provider_and_preserves_confirmed_fact(self):
        state = SimpleNamespace(enemy_composition=None)
        window = _controller_window(state)
        controller = RecognitionController(window, game_state=state)
        provider = object()

        with patch(
            "src.recognition_controller.create_production_enemy_composition_ocr_provider",
            return_value=provider,
        ) as create_provider:
            self.assertTrue(
                controller.initialize_enemy_composition_recognition()
            )
            original_scheduler = window.enemy_composition_scheduler
            state.enemy_composition = "Disruptive Artillery"

            self.assertFalse(controller.set_enemy_composition_enabled(False))
            self.assertEqual(
                state.enemy_composition,
                "Disruptive Artillery",
            )
            self.assertIsNone(
                window.mutator_and_enemy_race_recognizer.attached_scheduler
            )
            window.enemy_composition_notifier.reset.assert_called_once_with()

            self.assertTrue(controller.set_enemy_composition_enabled(True))

        create_provider.assert_called_once_with(window.logger)
        self.assertIs(window.enemy_composition_ocr_provider, provider)
        self.assertIs(window.enemy_composition_scheduler, original_scheduler)
        self.assertIs(
            window.mutator_and_enemy_race_recognizer.attached_scheduler,
            original_scheduler,
        )
        self.assertEqual(window.mutator_and_enemy_race_recognizer.start_count, 0)

    def test_reenable_initializes_missing_pipeline_and_restarts_shared_loop(self):
        state = SimpleNamespace(enemy_composition=None)
        window = _controller_window(state)
        controller = RecognitionController(window, game_state=state)
        provider = object()

        config.ENEMY_COMPOSITION_ENABLED = False
        controller.initialize_enemy_composition_recognition()

        with patch(
            "src.recognition_controller.create_production_enemy_composition_ocr_provider",
            return_value=provider,
        ) as create_provider:
            self.assertTrue(controller.set_enemy_composition_enabled(True))

        create_provider.assert_called_once_with(window.logger)
        self.assertIs(window.enemy_composition_ocr_provider, provider)
        self.assertIsNotNone(window.enemy_composition_recognizer)
        self.assertIsNotNone(window.enemy_composition_scheduler)
        self.assertIs(
            window.mutator_and_enemy_race_recognizer.attached_scheduler,
            window.enemy_composition_scheduler,
        )
        self.assertEqual(window.mutator_and_enemy_race_recognizer.start_count, 1)


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeMutatorsDb:
    def execute(self, _sql, _params=()):
        return _FakeCursor(
            [
                ("AggressiveDeployment",),
                ("AggressiveDeploymentProtoss",),
            ]
        )


class _FakeButton:
    def __init__(self, mutator_name):
        self._mutator_name = mutator_name
        self._checked = False
        self.original_icon = object()
        self.gray_icon = object()

    def blockSignals(self, _blocked):
        pass

    def property(self, name):
        return self._mutator_name if name == "mutator_name" else None

    def setChecked(self, checked):
        self._checked = bool(checked)

    def isChecked(self):
        return self._checked

    def setIcon(self, _icon):
        pass

    def setGraphicsEffect(self, _effect):
        pass


class _FakeToastManager:
    def __init__(self):
        self.messages = []
        self.alerts = set()

    def show_map_countdown_alert(
        self,
        event_id,
        _time_diff,
        message,
        _is_in_game,
        sound_filename=None,
        default_color=None,
    ):
        del sound_filename, default_color
        self.messages.append(message)
        self.alerts.add(event_id)

    def has_alert(self, event_id):
        return event_id in self.alerts

    def remove_alert(self, event_id):
        self.alerts.discard(event_id)


class EnemyCompositionAdviceToggleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.previous_enabled = config.ENEMY_COMPOSITION_ENABLED
        self.previous_composition = game_state_service.state.enemy_composition
        self.previous_enemy_race = game_state_service.state.enemy_race
        config.ENEMY_COMPOSITION_ENABLED = True
        game_state_service.state.enemy_composition = "Disruptive Artillery"

    def tearDown(self):
        config.ENEMY_COMPOSITION_ENABLED = self.previous_enabled
        game_state_service.state.enemy_composition = self.previous_composition
        game_state_service.state.enemy_race = self.previous_enemy_race

    def _advisor(self):
        return EnemyCompositionUnitAdvisor()

    def test_advisor_gate_disables_all_three_consumer_enrichments(self):
        advisor = self._advisor()
        self.assertEqual(
            advisor.get_attention_units("Disruptive Artillery", "t2"),
            "哨兵",
        )
        config.ENEMY_COMPOSITION_ENABLED = False
        self.assertIsNone(
            advisor.get_attention_units("Disruptive Artillery", "t2")
        )

        with patch.object(MutatorManager, "init_mutator_ui"), patch.object(
            MutatorManager,
            "init_mutator_alerts",
        ):
            mutator_manager = MutatorManager(
                mutators_db=_FakeMutatorsDb(),
                advisor=advisor,
            )
        mutator_manager.active_mutator_time_points = {
            "AggressiveDeployment": [(60, "t2", "")]
        }
        try:
            with patch(
                "src.event_managers_and_notifiers.mutator_manager.get_sc2_window_geometry",
                return_value=(0, 0, 1920, 1080),
            ), patch.object(
                mutator_manager,
                "show_mutator_alert",
            ) as show_alert:
                mutator_manager.check_alerts(30, True)
            mutator_message = show_alert.call_args.args[0]
        finally:
            mutator_manager.deleteLater()

        map_table = QTableWidget(1, 5)
        for column, value in enumerate(("01:00", "地图事件", "t2", "", "")):
            map_table.setItem(0, column, QTableWidgetItem(value))
        map_toasts = _FakeToastManager()
        MapEventManager(
            map_table,
            map_toasts,
            logging.getLogger(__name__),
            advisor=advisor,
        ).update_events(30, True)

        malwarfare_table = QTableWidget(1, 4)
        for column, value in enumerate(("2", "00:30", "净网事件", "t2")):
            malwarfare_table.setItem(0, column, QTableWidgetItem(value))
        malwarfare_toasts = _FakeToastManager()
        MapwarfareEventManager(
            malwarfare_table,
            malwarfare_toasts,
            logging.getLogger(__name__),
            advisor=advisor,
        ).update_events(2, 50, True)

        self.assertIn("强度：t2", mutator_message)
        self.assertNotIn("注意单位:", mutator_message)
        self.assertIn("地图事件\tt2", map_toasts.messages[0])
        self.assertNotIn("注意单位:", map_toasts.messages[0])
        self.assertEqual(
            malwarfare_toasts.messages,
            ["余20秒    00:30\t净网事件\tt2"],
        )

    def test_protoss_deployment_variant_is_unchanged_while_disabled(self):
        config.ENEMY_COMPOSITION_ENABLED = False
        game_state_service.state.enemy_race = "Protoss"
        with patch.object(MutatorManager, "init_mutator_ui"), patch.object(
            MutatorManager,
            "init_mutator_alerts",
        ):
            manager = MutatorManager(mutators_db=_FakeMutatorsDb())
        manager.mutator_names = [
            "AggressiveDeployment",
            "AggressiveDeploymentProtoss",
        ]
        manager.notify_mutator_names = set(manager.mutator_names)
        manager.active_mutator_time_points = {}
        manager.mutator_buttons = [
            _FakeButton("AggressiveDeployment"),
            _FakeButton("AggressiveDeploymentProtoss"),
        ]

        try:
            with patch.object(
                manager,
                "load_mutator_config",
                return_value=[(60, "t2", "")],
            ) as load_config:
                manager.sync_mutator_toggles(["AggressiveDeployment"])

            self.assertFalse(manager.mutator_buttons[0].isChecked())
            self.assertTrue(manager.mutator_buttons[1].isChecked())
            load_config.assert_called_once_with(
                "AggressiveDeploymentProtoss"
            )
        finally:
            manager.deleteLater()


class SettingsFeatureToggleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.previous_enabled = config.ENEMY_COMPOSITION_ENABLED
        config.ENEMY_COMPOSITION_ENABLED = True

    def tearDown(self):
        config.ENEMY_COMPOSITION_ENABLED = self.previous_enabled

    def test_settings_persist_reload_and_apply_immediately(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = os.path.join(temp_dir, "settings.json")
            handler = SettingsHandler(settings_path)
            success, _message = handler.save_all(
                {"ENEMY_COMPOSITION_ENABLED": False}
            )
            self.assertTrue(success)
            with open(settings_path, "r", encoding="utf-8") as settings_file:
                self.assertFalse(
                    json.load(settings_file)["ENEMY_COMPOSITION_ENABLED"]
                )
            self.assertFalse(
                handler.load_config()["ENEMY_COMPOSITION_ENABLED"]
            )

        runtime_controller = Mock()
        fake_config = SimpleNamespace(ENEMY_COMPOSITION_ENABLED=True)
        window = SimpleNamespace(
            recognition_controller=runtime_controller,
            logger=Mock(),
        )
        settings_controller = SettingsController(
            window,
            project_root_getter=lambda: "unused",
            config_module=fake_config,
            hotkeys_module=Mock(),
        )
        settings_controller.handle_settings_update(
            {"ENEMY_COMPOSITION_ENABLED": False}
        )
        self.assertFalse(fake_config.ENEMY_COMPOSITION_ENABLED)
        runtime_controller.set_enemy_composition_enabled.assert_called_once_with(
            False
        )

    def test_auto_alert_group_order_switch_label_and_default(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "src.settings_window.settings_window.get_project_root",
            return_value=temp_dir,
        ), patch.object(
            SettingsHandler,
            "get_names_by_type",
            return_value=[],
        ):
            settings_window = SettingsWindow()

        try:
            relevant_titles = [
                group.title()
                for group in settings_window.findChildren(QGroupBox)
                if group.title()
                in {
                    "神器提醒设置 (Artifact Alert)",
                    "敌方特殊单位识别与提醒 (Enemy Composition)",
                    "人口提醒设置 (Supply Alert)",
                }
            ]
            self.assertEqual(
                relevant_titles,
                [
                    "神器提醒设置 (Artifact Alert)",
                    "敌方特殊单位识别与提醒 (Enemy Composition)",
                    "人口提醒设置 (Supply Alert)",
                ],
            )
            switch_data = settings_window.widgets[
                "ENEMY_COMPOSITION_ENABLED"
            ]
            self.assertEqual(switch_data["type"], "switch")
            self.assertEqual(
                switch_data["label"],
                "启用敌方特殊单位识别和提醒:",
            )
            self.assertTrue(switch_data["widget"].isChecked())
        finally:
            settings_window.close()
            settings_window.deleteLater()


if __name__ == "__main__":
    unittest.main()
