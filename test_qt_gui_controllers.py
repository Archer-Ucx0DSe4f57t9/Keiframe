import inspect
import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.settings_window.settings_controller import SettingsController
from src.ui.map_selection_controller import MapSelectionController


class FakeSignal:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)

    def emit(self, *args):
        for callback in list(self.callbacks):
            if len(inspect.signature(callback).parameters) == 0:
                callback()
            else:
                callback(*args)


class FakeLineEdit:
    def __init__(self):
        self.textChanged = FakeSignal()
        self._text = ""
        self._signals_blocked = False
        self.block_history = []

    def text(self):
        return self._text

    def setText(self, text):
        self._text = text
        if not self._signals_blocked:
            self.textChanged.emit(text)

    def blockSignals(self, blocked):
        self._signals_blocked = blocked
        self.block_history.append(blocked)


class FakeComboBox:
    def __init__(self, items):
        self.currentTextChanged = FakeSignal()
        self.items = list(items)
        self.current_index = 0 if self.items else -1
        self._signals_blocked = False
        self.block_history = []
        self._view = object()

    def currentText(self):
        if 0 <= self.current_index < len(self.items):
            return self.items[self.current_index]
        return ""

    def blockSignals(self, blocked):
        self._signals_blocked = blocked
        self.block_history.append(blocked)

    def clear(self):
        previous = self.currentText()
        self.items = []
        self.current_index = -1
        if previous and not self._signals_blocked:
            self.currentTextChanged.emit("")

    def addItems(self, items):
        previous = self.currentText()
        self.items.extend(items)
        if self.current_index < 0 and self.items:
            self.current_index = 0
        current = self.currentText()
        if current != previous and not self._signals_blocked:
            self.currentTextChanged.emit(current)

    def findText(self, text):
        try:
            return self.items.index(text)
        except ValueError:
            return -1

    def setCurrentIndex(self, index):
        previous = self.currentText()
        self.current_index = index
        current = self.currentText()
        if current != previous and not self._signals_blocked:
            self.currentTextChanged.emit(current)

    def view(self):
        return self._view


class FakeTimer:
    def __init__(self):
        self.timeout = FakeSignal()
        self.stop_calls = 0
        self.start_calls = []

    def stop(self):
        self.stop_calls += 1

    def start(self, interval):
        self.start_calls.append(interval)


class FakeLabel:
    def __init__(self):
        self.geometry = None

    def setGeometry(self, *geometry):
        self.geometry = geometry


class FakeLogger:
    def __init__(self):
        self.infos = []
        self.warnings = []
        self.errors = []

    def info(self, message):
        self.infos.append(message)

    def warning(self, message):
        self.warnings.append(message)

    def error(self, message):
        self.errors.append(message)


class FakeVersionGroup:
    def __init__(self, visible=True):
        self.visible = visible

    def isVisible(self):
        return self.visible


class FakeButton:
    def __init__(self, text, checked=False):
        self._text = text
        self._checked = checked
        self.click_calls = 0

    def text(self):
        return self._text

    def isChecked(self):
        return self._checked

    def click(self):
        self.click_calls += 1


class MapSelectionControllerTest(unittest.TestCase):
    def make_search_window(self, map_list):
        window = SimpleNamespace()
        window.maps_db = object()
        window.search_box = FakeLineEdit()
        window.combo_box = FakeComboBox(map_list)
        window.clear_search_timer = FakeTimer()
        window.time_label = FakeLabel()
        window.selected_calls = []
        window.on_map_selected = window.selected_calls.append
        return window

    def test_search_preserves_matching_order_and_selects_first_result(self):
        map_list = ["Alpha", "Beta", "Gamma"]
        window = self.make_search_window(map_list)
        search_calls = []
        load_calls = []

        def keyword_search(connection, keyword):
            search_calls.append((connection, keyword))
            return ["Gamma", "Alpha"] if keyword == "needle" else []

        controller = MapSelectionController(
            window,
            keyword_search=keyword_search,
            map_selection_handler=lambda current_window, map_name: load_calls.append(
                (current_window, map_name)
            ),
        )
        controller.setup_search_box_connections(map_list)

        window.search_box.setText("  NEEDLE  ")

        self.assertEqual(window.combo_box.items, ["Gamma", "Alpha"])
        self.assertEqual(load_calls, [(window, "Gamma")])
        self.assertEqual(search_calls, [(window.maps_db, "needle")])
        self.assertEqual(window.combo_box.block_history, [True, False])
        self.assertEqual(len(window.search_box.textChanged.callbacks), 2)
        self.assertEqual(len(window.clear_search_timer.timeout.callbacks), 1)
        self.assertEqual(len(window.combo_box.currentTextChanged.callbacks), 1)
        self.assertEqual(window.clear_search_timer.stop_calls, 1)
        self.assertEqual(window.clear_search_timer.start_calls, [30000])
        self.assertEqual(window.time_label.geometry, (10, 40, 100, 20))

    def test_automatic_search_clear_restores_list_without_loading_another_map(self):
        map_list = ["Alpha", "Beta", "Gamma"]
        window = self.make_search_window(map_list)
        window.combo_box.setCurrentIndex(1)
        load_calls = []
        controller = MapSelectionController(
            window,
            keyword_search=lambda connection, keyword: [],
            map_selection_handler=lambda current_window, map_name: load_calls.append(map_name),
        )
        controller.setup_search_box_connections(map_list)

        window.search_box.setText("beta")
        self.assertEqual(load_calls, ["Beta"])
        load_calls.clear()

        window.clear_search_timer.timeout.emit()

        self.assertEqual(window.search_box.text(), "")
        self.assertEqual(window.combo_box.items, map_list)
        self.assertEqual(window.combo_box.currentText(), "Beta")
        self.assertEqual(load_calls, [])
        self.assertEqual(window.selected_calls, [])
        self.assertEqual(window.search_box.block_history, [True, False])

    def test_automatic_map_update_keeps_signal_then_explicit_load_order(self):
        window = SimpleNamespace()
        window.combo_box = FakeComboBox(["Old", "Target"])
        window.manual_map_selection = True
        window.logger = FakeLogger()
        events = []

        def on_map_selected(map_name):
            events.append(("signal", map_name, window.manual_map_selection))

        window.combo_box.currentTextChanged.connect(on_map_selected)
        controller = MapSelectionController(
            window,
            map_selection_handler=lambda current_window, map_name: events.append(
                ("explicit", map_name, current_window.manual_map_selection)
            ),
        )

        controller.handle_map_update("Target")

        self.assertEqual(
            events,
            [
                ("signal", "Target", False),
                ("explicit", "Target", False),
            ],
        )
        self.assertEqual(window.combo_box.currentText(), "Target")

    def test_version_cycle_uses_next_buttons_click(self):
        first = FakeButton("A", checked=True)
        second = FakeButton("B")
        window = SimpleNamespace(
            logger=FakeLogger(),
            map_version_group=FakeVersionGroup(visible=True),
            version_buttons=[first, second],
        )

        MapSelectionController(window).process_map_switch_logic()

        self.assertEqual(first.click_calls, 0)
        self.assertEqual(second.click_calls, 1)


class FakeSettingsDialog:
    def __init__(self, parent, events, error=None, visible=False):
        self.parent = parent
        self.events = events
        self.error = error
        self.visible = visible
        self.settings_saved = FakeSignal()
        self.raise_calls = 0
        self.activate_calls = 0

    def isVisible(self):
        return self.visible

    def raise_(self):
        self.raise_calls += 1

    def activateWindow(self):
        self.activate_calls += 1

    def exec_(self):
        self.events.append("exec")
        if self.error:
            raise self.error


class FakeHotkeys:
    def __init__(self, events):
        self.events = events

    def unhook_global_hotkeys(self, window):
        self.events.append("unhook")

    def init_global_hotkeys(self, window):
        self.events.append("init")


class SettingsControllerTest(unittest.TestCase):
    def make_window(self):
        return SimpleNamespace(
            settings_window=None,
            handle_settings_update=lambda settings: None,
            logger=FakeLogger(),
        )

    def make_controller(self, window, events, error=None):
        def dialog_factory(parent):
            return FakeSettingsDialog(parent, events, error=error)

        controller = SettingsController(
            window,
            settings_window_class=dialog_factory,
            project_root_getter=lambda: os.devnull,
            hotkeys_module=FakeHotkeys(events),
        )
        controller.apply_user_settings = lambda: events.append("apply")
        return controller

    def test_settings_close_restores_hotkeys_and_reloads_configuration(self):
        events = []
        window = self.make_window()
        controller = self.make_controller(window, events)

        controller.open_settings()

        self.assertEqual(events, ["unhook", "exec", "init", "apply"])
        self.assertIsNone(window.settings_window)

    def test_settings_exception_still_restores_hotkeys_and_reloads_configuration(self):
        events = []
        window = self.make_window()
        controller = self.make_controller(window, events, error=RuntimeError("dialog failed"))

        with self.assertRaisesRegex(RuntimeError, "dialog failed"):
            controller.open_settings()

        self.assertEqual(events, ["unhook", "exec", "init", "apply"])
        self.assertIsNone(window.settings_window)

    def test_visible_settings_window_is_activated_without_recreating_it(self):
        events = []
        window = self.make_window()
        existing = FakeSettingsDialog(window, events, visible=True)
        window.settings_window = existing
        controller = self.make_controller(window, events)

        controller.open_settings()

        self.assertEqual(existing.raise_calls, 1)
        self.assertEqual(existing.activate_calls, 1)
        self.assertEqual(events, [])
        self.assertIs(window.settings_window, existing)

    def test_missing_old_config_fields_keep_defaults(self):
        fake_config = SimpleNamespace(EXISTING="default", MISSING="keep-default")
        window = self.make_window()

        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = os.path.join(temp_dir, "settings.json")
            with open(settings_path, "w", encoding="utf-8") as settings_file:
                json.dump(
                    {"EXISTING": "overridden", "REMOVED_SETTING": "ignored"},
                    settings_file,
                )

            controller = SettingsController(
                window,
                project_root_getter=lambda: temp_dir,
                config_module=fake_config,
            )
            controller.apply_user_settings()

        self.assertEqual(fake_config.EXISTING, "overridden")
        self.assertEqual(fake_config.MISSING, "keep-default")
        self.assertFalse(hasattr(fake_config, "REMOVED_SETTING"))

    def test_settings_update_keeps_existing_immediate_refresh_scope(self):
        fake_config = SimpleNamespace(TABLE_FONT_SIZE=12)
        menu = SimpleNamespace(
            metrics_calls=0,
            sync_calls=0,
            apply_menu_metrics=lambda: setattr(menu, "metrics_calls", menu.metrics_calls + 1),
            sync_artifact_menu_state=lambda: setattr(menu, "sync_calls", menu.sync_calls + 1),
        )
        window = self.make_window()
        window.search_box = object()
        window.combo_box = FakeComboBox([])
        window.table_area = object()
        window.main_menu_controller = menu
        controller = SettingsController(window, config_module=fake_config)

        with (
            patch(
                "src.settings_window.settings_controller.get_control_font_size",
                return_value=17,
            ),
            patch(
                "src.settings_window.settings_controller.apply_table_row_height"
            ) as apply_row_height,
            patch("src.utils.font_uitils.set_font_size") as set_font_size,
        ):
            controller.handle_settings_update({"TABLE_FONT_SIZE": 20})

        self.assertEqual(fake_config.TABLE_FONT_SIZE, 20)
        self.assertEqual(
            set_font_size.call_args_list,
            [
                unittest.mock.call(window.search_box, 17),
                unittest.mock.call(window.combo_box, 17),
                unittest.mock.call(window.combo_box.view(), 17),
            ],
        )
        apply_row_height.assert_called_once_with(window.table_area)
        self.assertEqual(menu.metrics_calls, 1)
        self.assertEqual(menu.sync_calls, 1)


if __name__ == "__main__":
    unittest.main()
