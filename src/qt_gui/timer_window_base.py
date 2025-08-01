# timer_window_base.py

import ctypes
from ctypes import windll
from PyQt5.QtWidgets import QMainWindow, QApplication
from PyQt5.QtCore import Qt, pyqtSignal, QRect
import config

# 将 Qt GUI 中的一些基础帮助函数移到这里
def get_current_screen(self):
    """获取当前窗口所在的显示器"""
    window_geometry = self.geometry()
    window_center = window_geometry.center()
    
    # 获取所有显示器
    screens = QApplication.screens()
    
    # 遍历所有显示器，检查窗口中心点是否在显示器范围内
    for screen in screens:
        screen_geometry = screen.geometry()
        if screen_geometry.contains(window_center):
            return screen
    
    # 如果没有找到，返回主显示器
    return QApplication.primaryScreen()

class TimerWindowBase(QMainWindow):
    """
    TimerWindow 的基础类，包含窗口的初始化和核心属性。
    """
    # 创建信号用于地图更新
    progress_signal = pyqtSignal(list)
    toggle_artifact_signal = pyqtSignal()

    def __init__(self, parent=None):
        """
        初始化窗口的基本设置。
        """
        super().__init__(parent)
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool |
            Qt.SubWindow
        )

        # 加载配置
        self.config = config
        self.is_dragging = False
        self.is_locked = self.config.get("lock_window", False)
        self.drag_position = None
        self.is_always_on_top = self.config.get("always_on_top", True)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, self.is_always_on_top)
        self.progress_signal.connect(self.handle_progress_update)

        self.screen_width, self.screen_height = self.get_screen_resolution()
        self.screen_rect = QRect(0, 0, self.screen_width, self.screen_height)
        self.window_width = self.config.get("window_width", 320)
        self.window_height = self.config.get("window_height", 450)
        self.setFixedSize(self.window_width, self.window_height)

    def get_screen_resolution(self):
        """
        获取主屏幕分辨率。
        """
        user32 = ctypes.windll.user32
        width = user32.GetSystemMetrics(0)
        height = user32.GetSystemMetrics(1)
        return width, height
