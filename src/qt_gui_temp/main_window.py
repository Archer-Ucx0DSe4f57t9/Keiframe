from PyQt5.QtWidgets import QMainWindow
from PyQt5.QtCore import pyqtSignal

from .ui_setup import setup_ui
from .toast_manager_wrap import init_toast, show_toast, hide_toast
from .tray_integration import init_tray
from .mutator_alert import show_mutator_alert, hide_mutator_alert
from .hotkey_manager import setup_hotkeys
from .event_handlers import *
from .utils import get_screen_resolution, get_text

class TimerWindow(QMainWindow):
    progress_signal = pyqtSignal(list)
    toggle_artifact_signal = pyqtSignal()

    def __init__(self):
        super().__init__()

        # 工具函数注入
        self.get_screen_resolution = get_screen_resolution
        self.get_text = get_text.__get__(self)
        self.show_toast = show_toast.__get__(self)
        self.hide_toast = hide_toast.__get__(self)
        self.show_mutator_alert = show_mutator_alert.__get__(self)
        self.hide_mutator_alert = hide_mutator_alert.__get__(self)

        # UI 初始化
        setup_ui(self)

        # 提示与系统托盘
        init_toast(self)
        init_tray(self)

        # 快捷键初始化
        setup_hotkeys(self)

        # 信号绑定等其他初始化逻辑请保留在 event_handlers 或专属模块中
