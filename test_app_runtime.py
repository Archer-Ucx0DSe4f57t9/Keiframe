import os
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QMainWindow

from src.app_runtime import AppRuntime
from src.qt_gui import TimerWindow


class FakeSignal:
    def __init__(self, name, events):
        self.name = name
        self.events = events
        self.connections = []

    def connect(self, callback, *args):
        self.connections.append((callback, args))
        self.events.append(("connect", self.name, callback, args))


class FakeButton:
    def __init__(self, name, events):
        self.clicked = FakeSignal(name, events)


class FakeTimer:
    instances = []
    single_shots = []
    events = None

    def __init__(self):
        self.timeout = FakeSignal("timer.timeout", self.events)
        self.start_calls = []
        FakeTimer.instances.append(self)
        self.events.append(("create", "timer"))

    def start(self, interval):
        self.start_calls.append(interval)
        self.events.append(("timer.start", interval))

    @staticmethod
    def singleShot(interval, callback):
        FakeTimer.single_shots.append((interval, callback))
        FakeTimer.events.append(("singleShot", interval, callback))


class FakeThread:
    def __init__(self, events, target, args, daemon):
        self.events = events
        self.target = target
        self.args = args
        self.daemon = daemon
        self.events.append(("thread.create", target, args, daemon))

    def start(self):
        self.events.append(("thread.start",))


class FakeLogger:
    def __init__(self, events):
        self.events = events

    def info(self, message):
        self.events.append(("log.info", message))

    def warning(self, *args):
        self.events.append(("log.warning",) + args)

    def error(self, message):
        self.events.append(("log.error", message))


class FakeComponent:
    def __init__(self, name, events):
        self.name = name
        self.events = events

    def reset(self):
        self.events.append(f"{self.name}.reset")

    def reset_and_start(self):
        self.events.append(("component", f"{self.name}.reset_and_start"))

    def shutdown(self):
        self.events.append(f"{self.name}.shutdown")

    def clear_all_countdowns(self):
        self.events.append(f"{self.name}.clear_all_countdowns")

    def clear_all_alerts(self):
        self.events.append(f"{self.name}.clear_all_alerts")


class AppRuntimeInitializationTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        FakeTimer.instances = []
        FakeTimer.single_shots = []
        FakeTimer.events = self.events

    def make_window(self):
        events = self.events
        window = SimpleNamespace()
        window.progress_signal = FakeSignal("progress", events)
        window.mutator_and_enemy_race_recognition_signal = FakeSignal(
            "race_mutator",
            events,
        )
        window.enemy_composition_confirmed_signal = FakeSignal(
            "composition",
            events,
        )
        window.memo_signal = FakeSignal("memo", events)
        window.countdown_hotkey_signal = FakeSignal("countdown_hotkey", events)
        window.map_switch_signal = FakeSignal("map_switch", events)
        window.lock_signal = FakeSignal("lock", events)

        for name in (
            "handle_enemy_composition_confirmed",
            "on_text_double_click",
            "show_memo",
            "process_countdown_hotkey_logic",
            "process_map_switch_logic",
            "process_lock_logic",
            "trigger_countdown_selection",
            "_run_async_game_scheduler",
            "handle_progress_update",
            "handle_mutator_and_enemy_race_recognition_update",
            "show_control_window",
        ):
            setattr(window, name, Mock(name=name))

        def apply_user_settings():
            events.append(("window", "apply_user_settings"))

        def initialize_composition():
            events.append(("window", "initialize_composition"))
            window.ocr_initializations += 1

        def init_ui():
            events.append(("window", "init_ui"))
            window.table_area = SimpleNamespace(mouseDoubleClickEvent=None)
            window.map_list = ["First Map", "Second Map"]
            window.memo_btn = FakeButton("memo_button", events)
            window.countdown_btn = FakeButton("countdown_button", events)

        window.apply_user_settings = apply_user_settings
        window._initialize_enemy_composition_recognition = initialize_composition
        window.ocr_initializations = 0
        window.setAttribute = lambda attribute: events.append(
            ("window.setAttribute", attribute)
        )
        window.init_ui = init_ui
        window.init_tray = lambda: events.append(("window", "init_tray"))
        window.setup_search_box_connections = lambda maps: events.append(
            ("window", "setup_search", tuple(maps))
        )
        window.x = lambda: 10
        window.y = lambda: 20
        window.windowHandle = lambda: SimpleNamespace(
            windowStateChanged=FakeSignal("window_state", events)
        )
        window.show = lambda: events.append(("window", "show"))
        return window

    def component_factory(self, name, component=None):
        def factory(*args, **kwargs):
            self.events.append(("create", name, args, kwargs))
            return component or FakeComponent(name, self.events)

        return factory

    def test_constructor_only_saves_window(self):
        window = object()
        runtime = AppRuntime(window)

        self.assertIs(runtime.window, window)
        self.assertEqual(vars(runtime), {"window": window})

    def test_initialize_preserves_order_parents_connections_and_thread_parameters(self):
        window = self.make_window()
        logger = FakeLogger(self.events)
        db = SimpleNamespace(
            get_maps_conn=lambda: self.events.append(("db", "maps")) or "maps",
            get_mutators_conn=lambda: self.events.append(("db", "mutators"))
            or "mutators",
        )
        recognizer = FakeComponent("recognizer", self.events)
        control_signal = FakeSignal("control_state", self.events)
        control = SimpleNamespace(
            state_changed=control_signal,
            height=lambda: 30,
            move=lambda *position: self.events.append(
                ("control.move", position)
            ),
        )
        thread_instances = []

        def thread_factory(*, target, args, daemon):
            thread = FakeThread(self.events, target, args, daemon)
            thread_instances.append(thread)
            return thread

        factories = {
            "DBManager": self.component_factory("db", db),
            "SettingsController": self.component_factory("settings"),
            "Mutator_and_enemy_race_recognizer": self.component_factory(
                "recognizer",
                recognizer,
            ),
            "RecognitionController": self.component_factory("recognition_controller"),
            "EnemyCompositionNotifier": self.component_factory("composition_notifier"),
            "ToastManager": self.component_factory("toast"),
            "MapSelectionController": self.component_factory("map_selection"),
            "MapVariantAutoResolver": self.component_factory("map_variant"),
            "MemoOverlay": self.component_factory("memo"),
            "CountdownManager": self.component_factory("countdown"),
            "ArtifactNotifier": self.component_factory("artifact"),
            "SupplyNotifier": self.component_factory("supply"),
            "ControlWindow": self.component_factory("control", control),
            "QTimer": FakeTimer,
        }

        with ExitStack() as stack:
            for name, replacement in factories.items():
                stack.enter_context(patch(f"src.app_runtime.{name}", replacement))
            stack.enter_context(patch("src.app_runtime.get_logger", return_value=logger))
            stack.enter_context(
                patch("src.app_runtime.threading.Thread", side_effect=thread_factory)
            )
            stack.enter_context(
                patch(
                    "src.app_runtime.config_hotkeys.init_global_hotkeys",
                    side_effect=lambda owner: self.events.append(("hotkeys", owner)),
                )
            )
            stack.enter_context(
                patch(
                    "src.app_runtime.map_loader.handle_map_selection",
                    side_effect=lambda owner, name: self.events.append(
                        ("map.load", owner, name)
                    ),
                )
            )
            stack.enter_context(patch("src.app_runtime.sys.platform", "test"))

            AppRuntime(window).initialize()

        self.assertEqual(window.maps_db, "maps")
        self.assertEqual(window.mutators_db, "mutators")
        self.assertEqual(window.ocr_initializations, 1)
        self.assertEqual(FakeTimer.instances[0].start_calls, [200])
        self.assertEqual([interval for interval, _ in FakeTimer.single_shots], [50, 100])
        self.assertEqual(len(thread_instances), 1)
        self.assertIs(thread_instances[0].target, window._run_async_game_scheduler)
        self.assertEqual(thread_instances[0].args, (window.progress_signal,))
        self.assertTrue(thread_instances[0].daemon)

        created = {
            event[1]: event
            for event in self.events
            if isinstance(event, tuple) and event[:1] == ("create",)
        }
        for name in (
            "settings",
            "recognition_controller",
            "composition_notifier",
            "toast",
            "map_selection",
            "artifact",
            "supply",
        ):
            self.assertIs(created[name][2][0], window, name)
        self.assertEqual(created["recognizer"][3]["recognition_signal"], window.mutator_and_enemy_race_recognition_signal)
        self.assertEqual(created["map_variant"][2], (window, logger))
        self.assertEqual(created["countdown"][2], (window, window.toast_manager))
        self.assertEqual(created["memo"][2], ())
        self.assertEqual(created["control"][2], ())

        composition_connect = next(
            index
            for index, event in enumerate(self.events)
            if isinstance(event, tuple) and event[:2] == ("connect", "composition")
        )
        worker_start = self.events.index(
            ("component", "recognizer.reset_and_start")
        )
        notifier_creation = next(
            index
            for index, event in enumerate(self.events)
            if isinstance(event, tuple)
            and event[:2] == ("create", "composition_notifier")
        )
        self.assertLess(notifier_creation, composition_connect)
        self.assertLess(composition_connect, worker_start)
        self.assertLess(
            self.events.index(("window", "initialize_composition")),
            worker_start,
        )
        self.assertLess(
            self.events.index(("window", "init_ui")),
            self.events.index(("create", "timer")),
        )

        thread_start = self.events.index(("thread.start",))
        progress_connect = next(
            index
            for index, event in enumerate(self.events)
            if isinstance(event, tuple) and event[:2] == ("connect", "progress")
        )
        self.assertLess(thread_start, progress_connect)
        self.assertLess(
            self.events.index(("hotkeys", window)),
            self.events.index(("create", "artifact", (window,), {})),
        )
        self.assertLess(
            self.events.index(("map.load", window, "First Map")),
            self.events.index(("window", "show")),
        )


class AppRuntimeLifecycleTests(unittest.TestCase):
    def make_component(self, events, name, method, error=None):
        def callback():
            events.append(name)
            if error:
                raise error

        return SimpleNamespace(**{method: callback})

    def make_reset_window(self, events, with_scheduler=True):
        window = SimpleNamespace(
            logger=FakeLogger(events),
            _last_dispatch_game_second=42,
            enemy_composition_notifier=self.make_component(
                events, "composition_notifier", "reset"
            ),
            mutator_manager=self.make_component(events, "mutator", "reset"),
            mutator_and_enemy_race_recognizer=self.make_component(
                events,
                "race_recognizer",
                "reset_and_start",
            ),
            countdown_manager=self.make_component(
                events,
                "countdown",
                "clear_all_countdowns",
            ),
            map_variant_auto_resolver=self.make_component(
                events,
                "map_variant",
                "reset",
            ),
            artifact_notifier=self.make_component(events, "artifact", "reset"),
            supply_notifier=self.make_component(events, "supply", "reset"),
            toast_manager=self.make_component(
                events,
                "toast",
                "clear_all_alerts",
            ),
        )
        if with_scheduler:
            window.enemy_composition_scheduler = self.make_component(
                events,
                "scheduler",
                "reset",
            )
        else:
            window.enemy_composition_scheduler = None
            window.enemy_composition_recognizer = self.make_component(
                events,
                "composition_recognizer",
                "reset",
            )
        return window

    def test_reset_order_state_clear_provider_reuse_and_repeat(self):
        events = []

        class TrackingState:
            def __setattr__(self, name, value):
                if name != "events":
                    self.events.append(f"state.{name}")
                object.__setattr__(self, name, value)

        state = TrackingState()
        state.events = events
        events.clear()
        state.enemy_race = "Terran"
        state.active_mutators = ["SpeedFreaks"]
        state.enemy_composition = "Machines of War"
        events.clear()
        window = self.make_reset_window(events)
        provider = object()
        window.enemy_composition_ocr_provider = provider
        runtime = AppRuntime(window)

        with patch("src.app_runtime.game_state_service.state", state):
            runtime.reset_game_info()
            first_events = list(events)
            events.clear()
            runtime.reset_game_info()

        expected = [
            "scheduler",
            "composition_notifier",
            "mutator",
            "state.enemy_race",
            "state.active_mutators",
            "state.enemy_composition",
            "race_recognizer",
            "countdown",
            "map_variant",
            "artifact",
            "supply",
            "toast",
        ]
        self.assertEqual(
            [event for event in first_events if isinstance(event, str)],
            expected,
        )
        self.assertEqual(
            [event for event in events if isinstance(event, str)],
            expected,
        )
        self.assertIs(window.enemy_composition_ocr_provider, provider)
        self.assertIsNone(window._last_dispatch_game_second)
        self.assertIsNone(state.enemy_race)
        self.assertIsNone(state.active_mutators)
        self.assertIsNone(state.enemy_composition)

    def test_reset_falls_back_to_recognizer_without_scheduler(self):
        events = []
        state = SimpleNamespace(
            enemy_race="Terran",
            active_mutators=[],
            enemy_composition="Shadow Tech",
        )
        window = self.make_reset_window(events, with_scheduler=False)

        with patch("src.app_runtime.game_state_service.state", state):
            AppRuntime(window).reset_game_info()

        self.assertIn("composition_recognizer", events)
        self.assertNotIn("scheduler", events)

    def make_exit_window(self, events, failing_mutator=False):
        tray_icon = SimpleNamespace(
            hide=lambda: events.append("tray.hide"),
            deleteLater=lambda: events.append("tray.delete"),
        )
        mutator_error = RuntimeError("mutator failed") if failing_mutator else None
        return SimpleNamespace(
            logger=FakeLogger(events),
            timer=self.make_component(events, "timer", "stop"),
            toast_manager=self.make_component(events, "toast", "shutdown"),
            mutator_manager=self.make_component(
                events,
                "mutator",
                "shutdown",
                mutator_error,
            ),
            malwarfare_handler=self.make_component(
                events,
                "malwarfare",
                "shutdown",
            ),
            mutator_and_enemy_race_recognizer=self.make_component(
                events,
                "race_recognizer",
                "shutdown",
            ),
            artifact_notifier=self.make_component(events, "artifact", "shutdown"),
            enemy_composition_notifier=self.make_component(
                events,
                "composition_notifier",
                "shutdown",
            ),
            supply_notifier=self.make_component(events, "supply", "shutdown"),
            countdown_manager=self.make_component(
                events,
                "countdown",
                "clear_all_countdowns",
            ),
            tray_manager=SimpleNamespace(tray_icon=tray_icon),
            control_window=self.make_component(events, "control", "close"),
            db_manager=self.make_component(events, "db", "close_all"),
        )

    def test_safe_exit_sets_flag_then_cleans_in_original_order(self):
        events = []

        class State:
            @property
            def app_closing(self):
                return False

            @app_closing.setter
            def app_closing(self, value):
                events.append("state.app_closing")

        app = self.make_component(events, "app", "quit")
        window = self.make_exit_window(events)

        with (
            patch("src.app_runtime.game_state_service.state", State()),
            patch(
                "src.app_runtime.config_hotkeys.unhook_global_hotkeys",
                side_effect=lambda owner: events.append("hotkeys"),
            ),
            patch("src.app_runtime.QApplication.instance", return_value=app),
        ):
            AppRuntime(window).safe_exit()

        self.assertEqual(
            [event for event in events if isinstance(event, str)],
            [
                "state.app_closing",
                "timer",
                "toast",
                "mutator",
                "malwarfare",
                "race_recognizer",
                "artifact",
                "composition_notifier",
                "supply",
                "countdown",
                "hotkeys",
                "tray.hide",
                "tray.delete",
                "control",
                "db",
                "app",
            ],
        )
        self.assertTrue(window._safe_exiting)
        self.assertIsNone(window.malwarfare_handler)
        self.assertIsNone(window.tray_manager.tray_icon)

    def test_safe_exit_reentry_is_ignored(self):
        events = []
        window = SimpleNamespace(_safe_exiting=True)

        AppRuntime(window).safe_exit()

        self.assertEqual(events, [])
        self.assertTrue(window._safe_exiting)

    def test_safe_exit_exception_stops_at_failure_and_restores_guard(self):
        events = []
        state = SimpleNamespace(app_closing=False)
        window = self.make_exit_window(events, failing_mutator=True)

        with (
            patch("src.app_runtime.game_state_service.state", state),
            patch("src.app_runtime.config_hotkeys.unhook_global_hotkeys") as unhook,
            patch("src.app_runtime.QApplication.instance") as app_instance,
        ):
            AppRuntime(window).safe_exit()

        self.assertEqual(
            [event for event in events if isinstance(event, str)],
            ["timer", "toast", "mutator"],
        )
        self.assertFalse(window._safe_exiting)
        self.assertTrue(state.app_closing)
        unhook.assert_not_called()
        app_instance.assert_not_called()

    def test_cleanup_on_close_keeps_its_distinct_scope_and_listener_branch(self):
        events = []
        state = SimpleNamespace(app_closing=False)
        window = self.make_exit_window(events)
        window.global_listener = self.make_component(
            events,
            "global_listener",
            "stop_listening",
        )

        with (
            patch("src.app_runtime.game_state_service.state", state),
            patch(
                "src.app_runtime.config_hotkeys.unhook_global_hotkeys",
                side_effect=lambda owner: events.append("hotkeys"),
            ),
            patch("src.app_runtime.QApplication.instance") as app_instance,
        ):
            AppRuntime(window).cleanup_on_close()

        self.assertEqual(
            [event for event in events if isinstance(event, str)],
            [
                "toast",
                "mutator",
                "malwarfare",
                "race_recognizer",
                "global_listener",
                "artifact",
                "composition_notifier",
                "supply",
                "hotkeys",
            ],
        )
        self.assertFalse(state.app_closing)
        self.assertNotIn("timer", events)
        self.assertNotIn("countdown", events)
        self.assertNotIn("tray.hide", events)
        self.assertNotIn("control", events)
        self.assertNotIn("db", events)
        self.assertFalse(hasattr(window, "_safe_exiting"))
        app_instance.assert_not_called()

    def test_cleanup_on_close_exception_keeps_original_interruption_boundary(self):
        events = []
        window = self.make_exit_window(events, failing_mutator=True)

        with patch(
            "src.app_runtime.config_hotkeys.unhook_global_hotkeys"
        ) as unhook:
            AppRuntime(window).cleanup_on_close()

        self.assertEqual(
            [event for event in events if isinstance(event, str)],
            ["toast", "mutator"],
        )
        self.assertIsNotNone(window.malwarfare_handler)
        self.assertFalse(hasattr(window, "_safe_exiting"))
        unhook.assert_not_called()


class TimerWindowRuntimeEntryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_constructor_assigns_runtime_before_initialize(self):
        observations = []

        class FakeRuntime:
            def __init__(self, window):
                self.window = window

            def initialize(self):
                observations.append(self.window.app_runtime is self)

        with patch("src.qt_gui.AppRuntime", FakeRuntime):
            window = TimerWindow()

        self.assertEqual(observations, [True])
        window.deleteLater()

    def test_runtime_entries_delegate_synchronously(self):
        runtime = Mock()
        window = SimpleNamespace(
            app_runtime=runtime,
            map_selection_controller=Mock(),
        )
        signal = object()

        TimerWindow._run_async_game_scheduler(window, signal)
        TimerWindow.handle_progress_update(window, ["reset_game_info"])
        TimerWindow.handle_progress_update(window, ["update_map", "Void Launch"])
        TimerWindow.safe_exit(window)

        runtime.run_async_game_scheduler.assert_called_once_with(signal)
        runtime.reset_game_info.assert_called_once_with()
        window.map_selection_controller.handle_map_update.assert_called_once_with(
            "Void Launch"
        )
        runtime.safe_exit.assert_called_once_with()

    def test_close_event_runs_runtime_cleanup_then_parent_close(self):
        events = []
        runtime = SimpleNamespace(
            cleanup_on_close=lambda: events.append("runtime.cleanup")
        )

        class FakeRuntime:
            def __init__(self, _window):
                pass

            def initialize(self):
                pass

        with patch("src.qt_gui.AppRuntime", FakeRuntime):
            window = TimerWindow()
        window.app_runtime = runtime
        event = object()

        with patch.object(
            QMainWindow,
            "closeEvent",
            side_effect=lambda received: events.append(("parent.close", received)),
        ):
            window.closeEvent(event)

        self.assertEqual(events, ["runtime.cleanup", ("parent.close", event)])
        window.deleteLater()

    def test_close_event_reaches_parent_after_runtime_handles_cleanup_failure(self):
        events = []

        class FakeRuntime:
            def __init__(self, _window):
                pass

            def initialize(self):
                pass

        with patch("src.qt_gui.AppRuntime", FakeRuntime):
            window = TimerWindow()

        window.logger = FakeLogger(events)
        window.toast_manager = SimpleNamespace(
            shutdown=lambda: (_ for _ in ()).throw(RuntimeError("failed"))
        )
        window.malwarfare_handler = None
        window.app_runtime = AppRuntime(window)
        event = object()

        with patch.object(
            QMainWindow,
            "closeEvent",
            side_effect=lambda received: events.append(("parent.close", received)),
        ):
            window.closeEvent(event)

        self.assertIn(("parent.close", event), events)
        window.deleteLater()


if __name__ == "__main__":
    unittest.main()
