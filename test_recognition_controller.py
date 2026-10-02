from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from src.game_readers.enemy_composition_recognizer import EnemyCompositionRecognizer
from src.game_readers.enemy_composition_scheduler import EnemyCompositionScheduler
from src.recognition_controller import (
    RecognitionController,
    create_production_enemy_composition_ocr_provider,
)
from src.app_runtime import AppRuntime
from src.qt_gui import (
    TimerWindow,
    create_production_enemy_composition_ocr_provider as qt_gui_provider_factory,
)


class TrackingState:
    def __init__(self, events, active_mutators=None):
        self.events = events
        self._enemy_race = None
        self._active_mutators = active_mutators
        self.enemy_composition = None

    @property
    def enemy_race(self):
        return self._enemy_race

    @enemy_race.setter
    def enemy_race(self, value):
        self._enemy_race = value
        self.events.append(("enemy_race", value))

    @property
    def active_mutators(self):
        return self._active_mutators

    @active_mutators.setter
    def active_mutators(self, value):
        self._active_mutators = value
        self.events.append(("active_mutators", value))


class RecognitionControllerTests(unittest.TestCase):
    def make_window(self, state=None):
        state = state or SimpleNamespace(
            enemy_race=None,
            active_mutators=None,
            enemy_composition=None,
        )
        signal = SimpleNamespace(emit=Mock())
        window = SimpleNamespace(
            logger=Mock(),
            game_state=state,
            enemy_composition_confirmed_signal=signal,
            enemy_composition_notifier=Mock(),
            mutator_and_enemy_race_recognizer=Mock(),
        )
        controller = RecognitionController(window, game_state=state)
        window.recognition_controller = controller
        return window, controller

    def test_constructor_only_saves_dependencies(self):
        window, _controller = self.make_window()

        self.assertFalse(hasattr(window, "enemy_composition_ocr_provider"))
        self.assertFalse(hasattr(window, "enemy_composition_scheduler"))

    def test_provider_success_is_injected_and_scheduler_attached(self):
        window, controller = self.make_window()
        provider = object()

        with patch(
            "src.recognition_controller.OpenCVDNNPPOCRv5Provider",
            return_value=provider,
        ) as provider_constructor:
            controller.initialize_enemy_composition_recognition()

        provider_constructor.assert_called_once_with()
        self.assertIs(window.enemy_composition_ocr_provider, provider)
        self.assertIsInstance(
            window.enemy_composition_recognizer,
            EnemyCompositionRecognizer,
        )
        self.assertIs(window.enemy_composition_recognizer._ocr_provider, provider)
        self.assertIsInstance(
            window.enemy_composition_scheduler,
            EnemyCompositionScheduler,
        )
        self.assertIs(window.enemy_composition_scheduler._game_state, window.game_state)
        window.mutator_and_enemy_race_recognizer.set_enemy_composition_scheduler.assert_called_once_with(
            window.enemy_composition_scheduler
        )

    def test_provider_failure_disables_only_composition_pipeline(self):
        window, controller = self.make_window()

        with patch(
            "src.recognition_controller.OpenCVDNNPPOCRv5Provider",
            side_effect=FileNotFoundError("model missing"),
        ):
            controller.initialize_enemy_composition_recognition()

        self.assertIsNone(window.enemy_composition_ocr_provider)
        self.assertIsNone(window.enemy_composition_recognizer)
        self.assertIsNone(window.enemy_composition_scheduler)
        window.mutator_and_enemy_race_recognizer.set_enemy_composition_scheduler.assert_called_once_with(
            None
        )
        window.logger.warning.assert_called_once_with(
            "Enemy Composition OCR addon unavailable: %s",
            "model missing",
        )

    def test_scheduler_confirmation_callback_uses_signal_emit(self):
        window, controller = self.make_window()

        with patch(
            "src.recognition_controller.OpenCVDNNPPOCRv5Provider",
            return_value=object(),
        ):
            controller.initialize_enemy_composition_recognition()

        window.enemy_composition_scheduler._confirmation_callback("Machines of War")

        window.enemy_composition_confirmed_signal.emit.assert_called_once_with(
            "Machines of War"
        )
        window.enemy_composition_notifier.show.assert_not_called()

    def test_reset_game_info_reuses_provider_instance(self):
        state = SimpleNamespace(
            enemy_race="Terran",
            active_mutators=["SpeedFreaks"],
            enemy_composition="Machines of War",
        )
        window, controller = self.make_window(state)
        provider = object()

        with patch(
            "src.recognition_controller.OpenCVDNNPPOCRv5Provider",
            return_value=provider,
        ) as provider_constructor:
            controller.initialize_enemy_composition_recognition()
            recognizer = window.enemy_composition_recognizer
            scheduler = window.enemy_composition_scheduler
            window._last_dispatch_game_second = 42
            window.app_runtime = AppRuntime(window)
            with patch("src.app_runtime.game_state_service.state", state):
                TimerWindow.handle_progress_update(window, ["reset_game_info"])

        provider_constructor.assert_called_once_with()
        self.assertIs(window.enemy_composition_ocr_provider, provider)
        self.assertIs(window.enemy_composition_recognizer, recognizer)
        self.assertIs(window.enemy_composition_scheduler, scheduler)
        self.assertIs(recognizer._ocr_provider, provider)
        self.assertIsNone(state.enemy_composition)

    def test_valid_composition_result_triggers_notifier(self):
        state = SimpleNamespace(enemy_composition="Machines of War")
        window, controller = self.make_window(state)

        controller.handle_enemy_composition_confirmed("Machines of War")

        window.enemy_composition_notifier.show.assert_called_once_with(
            "Machines of War"
        )

    def test_empty_stale_and_exiting_composition_results_are_filtered(self):
        cases = (
            ("empty", "Machines of War", "", False),
            ("stale", "Shadow Tech", "Machines of War", False),
            ("exiting", "Machines of War", "Machines of War", True),
        )
        for case_name, published, result, exiting in cases:
            with self.subTest(case=case_name):
                state = SimpleNamespace(enemy_composition=published)
                window, controller = self.make_window(state)
                window._safe_exiting = exiting

                controller.handle_enemy_composition_confirmed(result)

                window.enemy_composition_notifier.show.assert_not_called()

    def make_result_controller(self, active_mutators):
        events = []
        state = TrackingState(events, active_mutators=active_mutators)
        mutator_manager = SimpleNamespace(
            sync_mutator_toggles=lambda mutators: events.append(
                ("sync", list(mutators))
            )
        )
        window = SimpleNamespace(
            logger=Mock(),
            game_state=state,
            combo_box=SimpleNamespace(currentText=lambda: "Void Launch"),
            mutator_manager=mutator_manager,
        )

        def handle_map_selection(owner, map_name):
            self.assertIs(owner, window)
            events.append(
                (
                    "map",
                    map_name,
                    state.enemy_race,
                    state.active_mutators,
                )
            )

        controller = RecognitionController(
            window,
            game_state=state,
            map_loader_module=SimpleNamespace(
                handle_map_selection=handle_map_selection
            ),
        )
        return events, state, controller

    def test_race_update_loads_map_then_syncs_existing_mutators(self):
        events, state, controller = self.make_result_controller(["old"])

        controller.handle_mutator_and_enemy_race_recognition_update(
            {"race": "Terran", "mutators": None}
        )

        self.assertEqual(state.enemy_race, "Terran")
        self.assertEqual(
            events,
            [
                ("enemy_race", "Terran"),
                ("map", "Void Launch", "Terran", ["old"]),
                ("sync", ["old"]),
            ],
        )

    def test_mutators_none_is_incomplete_but_empty_list_is_confirmed(self):
        events, state, controller = self.make_result_controller(["old"])

        controller.handle_mutator_and_enemy_race_recognition_update(
            {"race": None, "mutators": None}
        )
        self.assertEqual(events, [])
        self.assertEqual(state.active_mutators, ["old"])

        controller.handle_mutator_and_enemy_race_recognition_update(
            {"race": None, "mutators": []}
        )
        self.assertEqual(
            events,
            [("active_mutators", []), ("sync", [])],
        )
        self.assertEqual(state.active_mutators, [])

    def test_race_and_mutators_preserve_original_processing_order(self):
        events, _state, controller = self.make_result_controller(["old"])

        controller.handle_mutator_and_enemy_race_recognition_update(
            {"race": "Zerg", "mutators": ["new"]}
        )

        self.assertEqual(
            events,
            [
                ("enemy_race", "Zerg"),
                ("map", "Void Launch", "Zerg", ["old"]),
                ("sync", ["old"]),
                ("active_mutators", ["new"]),
                ("sync", ["new"]),
            ],
        )

    def test_timer_window_entries_delegate_synchronously(self):
        controller = Mock()
        window = SimpleNamespace(recognition_controller=controller)

        TimerWindow._initialize_enemy_composition_recognition(window)
        TimerWindow.handle_enemy_composition_confirmed(window, "Machines of War")
        TimerWindow.handle_mutator_and_enemy_race_recognition_update(
            window,
            {"race": "Terran", "mutators": []},
        )

        controller.initialize_enemy_composition_recognition.assert_called_once_with()
        controller.handle_enemy_composition_confirmed.assert_called_once_with(
            "Machines of War"
        )
        controller.handle_mutator_and_enemy_race_recognition_update.assert_called_once_with(
            {"race": "Terran", "mutators": []}
        )

    def test_qt_gui_keeps_provider_factory_compatibility_import(self):
        self.assertIs(
            qt_gui_provider_factory,
            create_production_enemy_composition_ocr_provider,
        )


if __name__ == "__main__":
    unittest.main()
