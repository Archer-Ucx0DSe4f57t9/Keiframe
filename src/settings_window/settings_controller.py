import json
import os

from src import config, config_hotkeys
from src.settings_window.settings_window import SettingsWindow
from src.ui.main_window_layout import apply_table_row_height, get_control_font_size
from src.utils.fileutil import get_project_root


class SettingsController:
    """Coordinate settings loading, modal display, and immediate UI refresh."""

    def __init__(
        self,
        window,
        settings_window_class=SettingsWindow,
        project_root_getter=get_project_root,
        config_module=config,
        hotkeys_module=config_hotkeys,
    ):
        self.window = window
        self.settings_window_class = settings_window_class
        self.project_root_getter = project_root_getter
        self.config = config_module
        self.hotkeys = hotkeys_module

    def apply_user_settings(self):
        """Read settings.json and overlay matching config module attributes."""

        json_path = os.path.join(self.project_root_getter(), "settings.json")
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as settings_file:
                    user_settings = json.load(settings_file)

                for key, value in user_settings.items():
                    if hasattr(self.config, key):
                        setattr(self.config, key, value)
            except Exception as exc:
                active_logger = getattr(self.window, "logger", None)
                if active_logger:
                    active_logger.error(f"加载用户配置失败: {exc}")

    def open_settings(self):
        """Create and display the settings dialog while hotkeys are paused."""

        window = self.window
        if window.settings_window is not None and window.settings_window.isVisible():
            window.settings_window.raise_()
            window.settings_window.activateWindow()
            return

        window.settings_window = self.settings_window_class(window)
        window.settings_window.settings_saved.connect(window.handle_settings_update)

        self.hotkeys.unhook_global_hotkeys(window)
        try:
            window.settings_window.exec_()
        finally:
            self.hotkeys.init_global_hotkeys(window)
            self.apply_user_settings()
            window.settings_window = None

    def handle_settings_update(self, new_settings):
        """Apply the existing subset of settings that can refresh immediately."""

        window = self.window
        for key, value in new_settings.items():
            setattr(self.config, key, value)

        control_font_size = get_control_font_size()
        if hasattr(window, "search_box"):
            from src.utils.font_uitils import set_font_size

            set_font_size(window.search_box, control_font_size)
        if hasattr(window, "combo_box"):
            from src.utils.font_uitils import set_font_size

            set_font_size(window.combo_box, control_font_size)
            set_font_size(window.combo_box.view(), control_font_size)
        if hasattr(window, "table_area"):
            apply_table_row_height(window.table_area)
        if hasattr(window, "main_menu_controller"):
            window.main_menu_controller.apply_menu_metrics()
            window.main_menu_controller.sync_artifact_menu_state()
        window.logger.info("配置已更新，部分功能已重载")
