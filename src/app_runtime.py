import asyncio
import sys
import threading
import traceback

from PyQt5.QtCore import QPoint, QTimer, Qt
from PyQt5.QtWidgets import QApplication

from src import (
    app_window_manager,
    config_hotkeys,
    game_state_service,
    game_time_handler,
)
from src.control_window import ControlWindow
from src.db.db_manager import DBManager
from src.event_managers_and_notifiers.artifact_notifier import ArtifactNotifier
from src.event_managers_and_notifiers.countdown_manager import CountdownManager
from src.event_managers_and_notifiers.enemy_composition_notifier import (
    EnemyCompositionNotifier,
)
from src.event_managers_and_notifiers.supply_notifier import SupplyNotifier
from src.game_readers.mutator_and_enemy_race_recognizer import (
    Mutator_and_enemy_race_recognizer,
)
from src.map_handlers import map_loader
from src.map_handlers.map_variant_auto_resolver import MapVariantAutoResolver
from src.memo_overlay import MemoOverlay
from src.presentation_modules.toast_manager import ToastManager
from src.recognition_controller import RecognitionController
from src.settings_window.settings_controller import SettingsController
from src.ui.map_selection_controller import MapSelectionController
from src.utils.logging_util import get_logger


class AppRuntime:
    """Assemble and coordinate the runtime owned by ``TimerWindow``."""

    def __init__(self, window):
        self.window = window

    def initialize(self):
        window = self.window

        self._initialize_storage_and_settings()
        self._initialize_recognition()

        window.manual_map_selection = False
        window.toast_manager = ToastManager(window)
        window.map_event_manager = None
        window.is_map_Malwarfare = False
        window.malwarfare_handler = None
        window.auto_map_variant_switching = False
        window.map_selection_controller = MapSelectionController(window)
        window.map_variant_auto_resolver = MapVariantAutoResolver(
            window,
            window.logger,
        )

        window.init_ui()
        self._initialize_timer_and_window_features()
        self._initialize_notifiers_and_hotkeys()
        self._start_game_scheduler()
        self._initialize_control_window_and_connections()
        self._show_initial_window_state()

    def _initialize_storage_and_settings(self):
        window = self.window

        window.db_manager = DBManager()
        window.maps_db = window.db_manager.get_maps_conn()
        window.mutators_db = window.db_manager.get_mutators_conn()

        # moveEvent may run while the rest of the window is still being built.
        window.control_window = None
        window.settings_controller = SettingsController(window)
        window.apply_user_settings()

        window.mutator_and_enemy_race_recognizer = (
            Mutator_and_enemy_race_recognizer(
                recognition_signal=window.mutator_and_enemy_race_recognition_signal
            )
        )

        window.setAttribute(Qt.WA_DontCreateNativeAncestors)
        window.setAttribute(Qt.WA_NativeWindow)

        window.logger = get_logger("src.qt_gui")
        window.logger.info("Keiframe 启动")

        window.current_time = ""
        window._last_dispatch_game_second = None
        window.drag_position = QPoint(0, 0)
        window.game_state = game_state_service.state

    def _initialize_recognition(self):
        window = self.window

        window.recognition_controller = RecognitionController(
            window,
            game_state=window.game_state,
        )

        # Connect the queued UI notification before the perception worker starts.
        window.enemy_composition_notifier = EnemyCompositionNotifier(window)
        window.enemy_composition_confirmed_signal.connect(
            window.handle_enemy_composition_confirmed,
            Qt.QueuedConnection,
        )
        window._initialize_enemy_composition_recognition()
        window.mutator_and_enemy_race_recognizer.reset_and_start()

    def _initialize_timer_and_window_features(self):
        window = self.window

        window.timer = QTimer()
        window.timer.timeout.connect(
            lambda: game_time_handler.update_game_time(window)
        )
        window.timer.start(200)

        window.table_area.mouseDoubleClickEvent = window.on_text_double_click
        window.init_tray()

        if hasattr(window, "map_list"):
            window.setup_search_box_connections(window.map_list)

        window.ctrl_pressed = False
        window.is_temp_unlocked = False

        window.memo_overlay = MemoOverlay()
        if hasattr(window, "memo_btn"):
            window.memo_btn.clicked.connect(lambda: window.show_memo("temp"))

        window.memo_signal.connect(window.show_memo)
        window.countdown_hotkey_signal.connect(
            window.process_countdown_hotkey_logic
        )
        window.map_switch_signal.connect(window.process_map_switch_logic)
        window.lock_signal.connect(window.process_lock_logic)

        window.countdown_manager = CountdownManager(
            window,
            window.toast_manager,
        )
        if hasattr(window, "countdown_btn"):
            window.countdown_btn.clicked.connect(
                window.trigger_countdown_selection
            )

        window.settings_window = None

    def _initialize_notifiers_and_hotkeys(self):
        window = self.window

        config_hotkeys.init_global_hotkeys(window)

        window.artifact_notifier = ArtifactNotifier(window)
        if hasattr(window, "main_menu_controller"):
            window.main_menu_controller.set_artifact_notifier(
                window.artifact_notifier
            )

        window.supply_notifier = SupplyNotifier(window)

    def _start_game_scheduler(self):
        window = self.window

        window.game_check_thread = threading.Thread(
            target=window._run_async_game_scheduler,
            args=(window.progress_signal,),
            daemon=True,
        )
        window.game_check_thread.start()

    def _initialize_control_window_and_connections(self):
        window = self.window

        window.control_window = ControlWindow()
        window.control_window.move(
            window.x(),
            window.y() - window.control_window.height(),
        )
        window.control_window.state_changed.connect(
            lambda unlocked: app_window_manager.on_control_state_changed(
                window,
                unlocked,
            )
        )
        window.windowHandle().windowStateChanged.connect(
            lambda: app_window_manager.update_control_window_position(window)
        )

        window.progress_signal.connect(window.handle_progress_update)
        window.mutator_and_enemy_race_recognition_signal.connect(
            window.handle_mutator_and_enemy_race_recognition_update
        )

        QTimer.singleShot(50, window.show_control_window)

    def _show_initial_window_state(self):
        window = self.window

        if hasattr(window, "map_list") and window.map_list:
            map_loader.handle_map_selection(window, window.map_list[0])

        window.show()
        if sys.platform == "win32":
            import win32con
            import win32gui

            hwnd = int(window.winId())
            win32gui.SetWindowPos(
                hwnd,
                win32con.HWND_TOPMOST,
                0,
                0,
                0,
                0,
                win32con.SWP_NOMOVE
                | win32con.SWP_NOSIZE
                | win32con.SWP_NOACTIVATE,
            )

        QTimer.singleShot(
            100,
            lambda: app_window_manager.on_control_state_changed(window, False),
        )

    def run_async_game_scheduler(self, progress_signal):
        asyncio.run(
            game_state_service.check_for_new_game_scheduler(progress_signal)
        )

    def reset_game_info(self):
        window = self.window

        window.logger.info("收到新游戏信号，正在重置识别器和游戏状态")
        if (
            hasattr(window, "enemy_composition_scheduler")
            and window.enemy_composition_scheduler
        ):
            window.enemy_composition_scheduler.reset()
            window.logger.info("Enemy composition recognizer reset")
        elif (
            hasattr(window, "enemy_composition_recognizer")
            and window.enemy_composition_recognizer
        ):
            window.enemy_composition_recognizer.reset()

        if (
            hasattr(window, "enemy_composition_notifier")
            and window.enemy_composition_notifier
        ):
            window.enemy_composition_notifier.reset()

        if hasattr(window, "mutator_manager") and window.mutator_manager:
            window.mutator_manager.reset()

        game_state_service.state.enemy_race = None
        game_state_service.state.active_mutators = None
        game_state_service.state.enemy_composition = None
        window._last_dispatch_game_second = None

        if (
            hasattr(window, "mutator_and_enemy_race_recognizer")
            and window.mutator_and_enemy_race_recognizer
        ):
            window.mutator_and_enemy_race_recognizer.reset_and_start()

        if hasattr(window, "countdown_manager") and window.countdown_manager:
            window.countdown_manager.clear_all_countdowns()

        if hasattr(window, "map_variant_auto_resolver"):
            window.map_variant_auto_resolver.reset()

        if hasattr(window, "artifact_notifier") and window.artifact_notifier:
            window.artifact_notifier.reset()

        if hasattr(window, "supply_notifier") and window.supply_notifier:
            window.supply_notifier.reset()

        if hasattr(window, "toast_manager") and window.toast_manager:
            window.toast_manager.clear_all_alerts()

    def safe_exit(self):
        window = self.window

        if getattr(window, "_safe_exiting", False):
            return
        window._safe_exiting = True

        try:
            game_state_service.state.app_closing = True

            if hasattr(window, "timer") and window.timer:
                window.timer.stop()

            if hasattr(window, "toast_manager") and window.toast_manager:
                window.toast_manager.shutdown()

            if hasattr(window, "mutator_manager") and window.mutator_manager:
                window.mutator_manager.shutdown()

            if (
                hasattr(window, "malwarfare_handler")
                and window.malwarfare_handler is not None
            ):
                window.logger.info(
                    "应用关闭，正在关闭 MalwarfareMapHandler。"
                )
                window.malwarfare_handler.shutdown()
                window.malwarfare_handler = None

            if (
                hasattr(window, "mutator_and_enemy_race_recognizer")
                and window.mutator_and_enemy_race_recognizer
            ):
                window.mutator_and_enemy_race_recognizer.shutdown()
                window.logger.info("突变因子和种族识别器已关闭。")

            if hasattr(window, "artifact_notifier") and window.artifact_notifier:
                window.artifact_notifier.shutdown()
                window.logger.info("ArtifactNotifier 已关闭。")

            if (
                hasattr(window, "enemy_composition_notifier")
                and window.enemy_composition_notifier
            ):
                window.enemy_composition_notifier.shutdown()
                window.logger.info("EnemyCompositionNotifier 已关闭。")

            if hasattr(window, "supply_notifier") and window.supply_notifier:
                window.supply_notifier.shutdown()
                window.logger.info("SupplyNotifier 已关闭。")

            if hasattr(window, "countdown_manager") and window.countdown_manager:
                window.countdown_manager.clear_all_countdowns()

            config_hotkeys.unhook_global_hotkeys(window)

            if hasattr(window, "tray_manager") and window.tray_manager:
                tray_icon = getattr(window.tray_manager, "tray_icon", None)
                if tray_icon is not None:
                    tray_icon.hide()
                    tray_icon.deleteLater()
                    window.tray_manager.tray_icon = None

            if hasattr(window, "control_window") and window.control_window:
                window.control_window.close()

            if hasattr(window, "db_manager") and window.db_manager:
                window.db_manager.close_all()

            app = QApplication.instance()
            if app is not None:
                app.quit()

        except Exception as error:
            window.logger.error(
                f"清理失败，无法正常退出: {str(error)}"
            )
            window.logger.error(traceback.format_exc())
            window._safe_exiting = False

    def cleanup_on_close(self):
        window = self.window

        try:
            if hasattr(window, "toast_manager") and window.toast_manager:
                window.toast_manager.shutdown()

            if hasattr(window, "mutator_manager") and window.mutator_manager:
                window.mutator_manager.shutdown()

            if window.malwarfare_handler is not None:
                window.logger.info(
                    "应用关闭，正在关闭 MalwarfareMapHandler。"
                )
                window.malwarfare_handler.shutdown()
                window.malwarfare_handler = None

            if (
                hasattr(window, "mutator_and_enemy_race_recognizer")
                and window.mutator_and_enemy_race_recognizer
            ):
                window.mutator_and_enemy_race_recognizer.shutdown()
                window.logger.info("突变因子和种族识别器已关闭。")

            if hasattr(window, "global_listener") and window.global_listener:
                window.global_listener.stop_listening()
                window.logger.info("按键监听已关闭。")

            if hasattr(window, "artifact_notifier") and window.artifact_notifier:
                window.artifact_notifier.shutdown()
                window.logger.info("ArtifactNotifier 已关闭。")

            if (
                hasattr(window, "enemy_composition_notifier")
                and window.enemy_composition_notifier
            ):
                window.enemy_composition_notifier.shutdown()
                window.logger.info("EnemyCompositionNotifier 已关闭。")

            if hasattr(window, "supply_notifier") and window.supply_notifier:
                window.supply_notifier.shutdown()
                window.logger.info("SupplyNotifier 已关闭。")

            config_hotkeys.unhook_global_hotkeys(window)
            window.logger.info("已清理")
        except Exception as error:
            window.logger.error(f"清理失败: {str(error)}")
            window.logger.error(traceback.format_exc())
