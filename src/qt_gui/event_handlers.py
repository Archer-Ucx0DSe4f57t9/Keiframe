import keyboard
from PyQt5.QtWidgets import QAction, QSystemTrayIcon
from PyQt5.QtCore import Qt, QPoint, QTimer
import win32gui
from control_window import ControlWindow

class EventHandlers:
    """
    负责处理所有鼠标、键盘和 UI 交互事件。
    """
    def mousePressEvent(self, event):
        """
        处理鼠标按下事件。
        """
        if event.button() == Qt.LeftButton:
            self.is_dragging = True
            self.drag_position = event.globalPos() - self.pos()
            event.accept()

    def mouseMoveEvent(self, event):
        """
        处理鼠标移动事件。
        """
        if Qt.LeftButton and self.is_dragging:
            if not self.is_locked:
                self.move(event.globalPos() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        """
        处理鼠标释放事件。
        """
        self.is_dragging = False
        event.accept()

    def init_global_hotkeys(self):
        """
        初始化全局快捷键。
        """
        try:
            keyboard.add_hotkey(self.config.get("toggle_hotkey", "ctrl+alt+z"), self.handle_map_switch_hotkey)
            keyboard.add_hotkey(self.config.get("lock_hotkey", "ctrl+alt+l"), self.handle_lock_shortcut)
            keyboard.add_hotkey(self.config.get("quit_hotkey", "ctrl+alt+q"), self.quit_app)
        except Exception as e:
            print(f"初始化快捷键失败: {e}")

    def handle_map_switch_hotkey(self):
        """
        处理地图切换快捷键。
        """
        self.toggle_artifact_signal.emit()

    def handle_lock_shortcut(self):
        """
        处理锁定窗口快捷键。
        """
        self.toggle_lock()

    def quit_app(self):
        """
        退出应用程序。
        """
        QApplication.quit()
