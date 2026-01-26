# global_key_listener.py

import threading
from pynput import keyboard
from PyQt5.QtCore import QObject, pyqtSignal, QTimer, Qt
from src.logging_util import get_logger

class GlobalKeyListener(QObject):
    """
    全局键盘监听器，用于监听特定的按键状态（如Ctrl）。
    通过 pyqtSignal 将状态安全地传递回 Qt 主线程。
    """
    
    # 定义信号：发送布尔值 (True/False) 表示 L-Ctrl 键的状态
    ctrl_state_changed = pyqtSignal(bool)

    def __init__(self, target_key=keyboard.Key.ctrl_l, parent=None):
        super().__init__(parent)
        self._target_key = target_key
        self._is_ctrl_pressed = False
        self._listener_thread = None
        self._listener = None
        self.logger = get_logger(__name__)
        
        # 引入一个标志，确保状态更新在主线程中完成，避免重复发送信号
        self._pending_update = False 

    def _on_key_press(self, key):
        """pynput 回调：在工作线程中运行"""
        if key == self._target_key:
            self._safe_emit_state(True)

    def _on_key_release(self, key):
        """pynput 回调：在工作线程中运行"""
        if key == self._target_key:
            self._safe_emit_state(False)

    def _safe_emit_state(self, new_state):
        """
        在工作线程中调用，将状态改变调度到 Qt 主线程中发送信号。
        使用 QTimer.singleShot(0) 确保信号在主线程发出，保证线程安全。
        """
        if self._is_ctrl_pressed != new_state and not self._pending_update:
            self._is_ctrl_pressed = new_state
            self._pending_update = True
            
            # 使用 Qt 的机制将信号发射调度到主线程
            QTimer.singleShot(0, self._emit_state_and_reset_flag)

    def _emit_state_and_reset_flag(self):
        """在 Qt 主线程中发送信号并重置标志"""
        self.ctrl_state_changed.emit(self._is_ctrl_pressed)
        self._pending_update = False

    def start_listening(self):
        """启动监听器线程"""
        if self._listener is None:
            self._listener = keyboard.Listener(
                on_press=self._on_key_press,
                on_release=self._on_key_release
            )
            self._listener.daemon = True
            self._listener.start()
            self.logger.info("Global L-Ctrl Listener started.") # 调试信息

    def stop_listening(self):
        """停止监听器线程"""
        if self._listener:
            self._listener.stop()
            self._listener = None
            self.logger.info("Global L-Ctrl Listener stopped.") # 调试信息