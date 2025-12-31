# countdown_manager.py
import time
import traceback
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QColor
import config
from logging_util import get_logger
from message_presenter import MessagePresenter
from window_utils import get_sc2_window_geometry

class CountdownSelectionWindow(QWidget):
    """倒计时选择的小弹窗"""
    option_selected = pyqtSignal(int) # 发送选中的秒数

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("""
            QWidget {
                background-color: rgba(30, 30, 30, 220);
                border: 1px solid rgba(100, 100, 100, 150);
                border-radius: 5px;
            }
            QPushButton {
                background-color: rgba(60, 60, 60, 200);
                color: white;
                border: 1px solid gray;
                border-radius: 3px;
                padding: 5px;
                font-family: Arial;
                font-size: 14px;
                font-weight: bold;
                min-width: 50px;
            }
            QPushButton:hover {
                background-color: rgba(80, 80, 80, 255);
                border-color: white;
            }
            QPushButton[current="true"] {
                background-color: rgba(0, 191, 255, 100);
                border: 2px solid rgb(0, 191, 255);
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        self.buttons = []
        for seconds in config.COUNTDOWN_OPTIONS:
            btn = QPushButton(str(seconds))
            btn.clicked.connect(lambda checked, s=seconds: self.option_selected.emit(s))
            layout.addWidget(btn)
            self.buttons.append(btn)
            
    def highlight_button(self, index):
        """高亮显示特定的按钮（用于快捷键循环）"""
        for i, btn in enumerate(self.buttons):
            # 使用 setProperty + unpolish/polish 刷新样式
            is_current = (i == index)
            btn.setProperty("current", str(is_current).lower())
            btn.style().unpolish(btn)
            btn.style().polish(btn)

class CountdownManager(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = get_logger(__name__)
        
        # 状态变量
        self.anchor_game_time = None  # 点击按钮/按下快捷键时的游戏时间
        self.target_game_time = None  # 倒计时结束的目标游戏时间
        self.is_selecting = False     # 是否正在选择中
        self.current_option_index = 0 # 当前快捷键选中的索引
        self.has_played_sound = False
        
        # UI 组件
        self.selection_window = CountdownSelectionWindow()
        self.selection_window.option_selected.connect(self.confirm_selection)
        
        self.display_label = MessagePresenter(parent) # 用于显示倒计时
        
        # 快捷键确认定时器 (Real Time)
        self.hotkey_commit_timer = QTimer()
        self.hotkey_commit_timer.setSingleShot(True)
        self.hotkey_commit_timer.timeout.connect(self.commit_current_hotkey_selection)

    def start_interaction(self, current_game_time):
        """
        开始交互流程：记录当前游戏时间作为锚点，并显示选择UI
        """
        if self.is_selecting:
            # 如果已经在选择中，再次调用视为循环选项（由快捷键触发）
            self.cycle_selection()
            return

        self.logger.info(f"开始倒计时选择流程，锚点时间: {current_game_time}")
        self.anchor_game_time = current_game_time
        self.is_selecting = True
        self.current_option_index = 0 # 重置为第一个
        
        # 显示选择窗口
        self.show_selection_ui()
        
        # 如果是由快捷键触发的，开启自动确认计时器
        # (注意：如果是点击按钮触发，用户手动点击选项，不会受此计时器影响，
        # 但为了逻辑统一，我们假设点击按钮后，如果用户随后按键盘，也能接管)
        self.hotkey_commit_timer.start(5000) 

    def show_selection_ui(self):
        """显示选择窗口，位置在鼠标附近或屏幕中央"""
        # 简单处理：显示在主窗口上方一点
        if self.parent():
            geo = self.parent().geometry()
            x = geo.x()
            y = geo.y() - 80 
            self.selection_window.move(x, y)
        self.selection_window.highlight_button(0)
        self.selection_window.show()

    def cycle_selection(self):
        """快捷键循环选择"""
        if not self.is_selecting:
            return

        self.current_option_index = (self.current_option_index + 1) % len(config.COUNTDOWN_OPTIONS)
        self.logger.debug(f"快捷键切换选项至: {config.COUNTDOWN_OPTIONS[self.current_option_index]}")
        
        # 更新UI高亮
        self.selection_window.highlight_button(self.current_option_index)
        
        # 重置5秒计时器
        self.hotkey_commit_timer.start(5000)

    def commit_current_hotkey_selection(self):
        """5秒超时后自动确认当前高亮的选项"""
        if self.is_selecting:
            selected_seconds = config.COUNTDOWN_OPTIONS[self.current_option_index]
            self.logger.info(f"快捷键超时自动确认: {selected_seconds}")
            self.confirm_selection(selected_seconds)

    def confirm_selection(self, duration_seconds):
        """确认选择，计算目标时间并开始倒计时"""
        if self.anchor_game_time is None:
            self.logger.error("尝试确认选择，但没有锚点时间")
            self.cancel_selection()
            return

        # 计算目标时间 = 锚点时间 + 持续时间
        # 逻辑：倒计时应该等于 (Duration - (Current - Anchor))
        # 实际上目标时刻就是 Anchor + Duration
        self.target_game_time = self.anchor_game_time + duration_seconds
        
        self.logger.info(f"倒计时确认: 持续{duration_seconds}秒, 目标游戏时间: {self.target_game_time}")
        
        self.is_selecting = False
        self.selection_window.hide()
        self.hotkey_commit_timer.stop()
        self.has_played_sound = False
        
        # 立即更新一次显示
        # 注意：这里我们无法立即获取最新的 game_time，只能等待下一次 update_game_time 调用
        # 或者我们传入 current_time 到 confirm_selection，但这增加了耦合。
        # 稍微的延迟是可以接受的。

    def cancel_selection(self):
        self.is_selecting = False
        self.selection_window.hide()
        self.hotkey_commit_timer.stop()
        self.anchor_game_time = None

    def update_game_time(self, current_seconds):
        """
        每帧调用，更新倒计时状态
        """
        if not self.target_game_time:
            return

        remaining = self.target_game_time - current_seconds
        
        if remaining <= 0:
            # 倒计时结束
            self.display_label.hide()
            self.target_game_time = None
            self.anchor_game_time = None
            return

        # 准备显示文本
        message = f"倒计时: {int(remaining)}秒"
        
        # 计算颜色
        color = config.COUNTDOWN_DISPLAY_COLOR
        sound_to_play = None
        
        if remaining <= config.COUNTDOWN_WARNING_THRESHOLD_SECONDS:
            color = "rgb(255, 50, 50)" # 红色警告
            if not self.has_played_sound:
                sound_to_play = config.COUNTDOWN_SOUND_FILE
                self.has_played_sound = True

        # 计算显示位置 (基于SC2窗口)
        sc2_rect = get_sc2_window_geometry()
        if sc2_rect:
            x, y, w, h = sc2_rect
            # 显示在上方指定百分比位置
            target_y = y + int(h * getattr(config, 'COUNTDOWN_DISPLAY_Y_PERCENT', 0.15))
            
            # 使用 MessagePresenter 显示
            self.display_label.update_message(
                message, 
                color, 
                x=x, y=target_y, width=w, height=50, # 高度随便给一个足够的值
                font_size=config.COUNTDOWN_DISPLAY_FONT_SIZE,
                sound_filename=sound_to_play
            )
        else:
            self.display_label.hide()

    def handle_hotkey_trigger(self, current_game_seconds):
        """外部快捷键调用的入口"""
        if not self.is_selecting:
            # 第一次按下：开始交互
            self.start_interaction(current_game_seconds)
        else:
            # 已经在交互中：循环选项
            self.cycle_selection()