# countdown_manager.py
# 倒计时管理器，处理用户交互和倒计时逻辑
import time
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QPushButton
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from src import config
from src.utils.logging_util import get_logger
from src.utils.window_utils import get_sc2_window_geometry

class CountdownSelectionWindow(QWidget):
    """倒计时选择的小弹窗"""
    option_selected = pyqtSignal(dict) # 修改：发送整个配置字典

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("""
            QWidget {
                background-color: rgba(30, 30, 30, 240);
                border: 1px solid rgba(100, 100, 100, 150);
                border-radius: 5px;
            }
            QPushButton {
                background-color: rgba(60, 60, 60, 200);
                color: white;
                border: 1px solid gray;
                border-radius: 3px;
                padding: 5px;
                font-size: 13px;
                font-weight: bold;
                min-width: 60px;
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
        
        # 根据新的 config 结构生成按钮
        for idx, opt in enumerate(config.COUNTDOWN_OPTIONS):
            # 显示文本类似于 "机制 (60s)"
            text = f"{opt.get('label', '未命名')} ({opt.get('time')}s)"
            btn = QPushButton(text)
            # 使用 lambda 捕获当前的 opt 对象
            btn.clicked.connect(lambda checked, o=opt: self.option_selected.emit(o))
            layout.addWidget(btn)
            self.buttons.append(btn)
    
        # 2. 添加 "清除最近" 按钮
        clear_btn = QPushButton("清除最近")
        # 发送特殊动作字典
        clear_btn.clicked.connect(lambda: self.option_selected.emit({'action': 'clear_recent'}))
        layout.addWidget(clear_btn)
        self.buttons.append(clear_btn)

        # 3. 添加 "(X)" 关闭按钮
        close_btn = QPushButton("(X)")
        close_btn.clicked.connect(lambda: self.option_selected.emit({'action': 'close'}))
        layout.addWidget(close_btn)
        self.buttons.append(close_btn)
            
    def highlight_button(self, index):
        for i, btn in enumerate(self.buttons):
            is_current = (i == index)
            btn.setProperty("current", str(is_current).lower())
            btn.style().unpolish(btn)
            btn.style().polish(btn)

class CountdownManager(QWidget):
    def __init__(self, parent=None, toast_manager=None):
        super().__init__(parent)
        self.logger = get_logger(__name__)
        self.toast_manager = toast_manager # 依赖 ToastManager 进行显示
        
        # 状态变量
        self.anchor_game_time = None 
        self.is_selecting = False
        self.current_option_index = 0
        
        # 活动倒计时列表，存储结构:
        # [{'id': 'custom_cd_1', 'target': 1234.5, 'label': 'Name', 'sound': 'x.wav', 'warned': False}, ...]
        self.active_countdowns = [] 
        self.id_counter = 0 # 用于生成唯一ID
        
        # UI 组件
        self.selection_window = CountdownSelectionWindow()
        self.selection_window.option_selected.connect(self.confirm_selection)
        
        # 快捷键确认定时器
        self.hotkey_commit_timer = QTimer()
        self.hotkey_commit_timer.setSingleShot(True)
        self.hotkey_commit_timer.timeout.connect(self.commit_current_hotkey_selection)

    def start_interaction(self, current_game_time):
        if self.is_selecting:
            self.cycle_selection()
            return

        self.logger.info(f"开始倒计时选择流程，锚点时间: {current_game_time}")
        self.anchor_game_time = current_game_time
        self.is_selecting = True
        self.current_option_index = -1
        self.show_selection_ui()
        self.hotkey_commit_timer.start(5000)

    def show_selection_ui(self):
        if self.parent():
            geo = self.parent().geometry()
            x = geo.x()
            y = geo.y() - 80 
            self.selection_window.move(x, y)
        self.selection_window.highlight_button(-1)
        self.selection_window.show()

    def cycle_selection(self):
        if not self.is_selecting:
            return
        
        # [修改] 循环长度 = 配置项数量 + 2个固定选项(清除/关闭)
        total_options = len(config.COUNTDOWN_OPTIONS) + 2
        
        if self.current_option_index == 0:
            self.current_option_index = 0
        else:
            self.current_option_index = (self.current_option_index + 1) % total_options
            
        self.selection_window.highlight_button(self.current_option_index)
        self.hotkey_commit_timer.start(5000)

    def commit_current_hotkey_selection(self):

        if self.is_selecting:
            if self.current_option_index == -1:
                self.logger.info("倒计时选择超时且未选择任何项，取消操作。")
                self.cancel_selection()
            else:
                # [修改] 根据索引构建选中的选项数据
                num_config_options = len(config.COUNTDOWN_OPTIONS)
                
                selected_opt = None
                if self.current_option_index < num_config_options:
                    # 选中了常规倒计时
                    selected_opt = config.COUNTDOWN_OPTIONS[self.current_option_index]
                elif self.current_option_index == num_config_options:
                    # 选中了倒数第二个：清除最近
                    selected_opt = {'action': 'clear_recent'}
                elif self.current_option_index == num_config_options + 1:
                    # 选中了最后一个：关闭
                    selected_opt = {'action': 'close'}
                
                if selected_opt:
                    self.logger.info(f"倒计时选择超时，自动确认选项索引: {self.current_option_index}")
                    self.confirm_selection(selected_opt)

    def confirm_selection(self, opt_dict):
        """确认选择，添加倒计时到队列"""
        
        # 处理特殊动作：关闭
        if opt_dict.get('action') == 'close':
            self.logger.info("用户选择关闭倒计时菜单")
            self.cancel_selection()
            return

        # 处理特殊动作：清除最近
        if opt_dict.get('action') == 'clear_recent':
            self.logger.info("用户选择清除最近的倒计时")
            self.remove_recent_countdown()
            self.cancel_selection()
            return
        
        if self.anchor_game_time is None:
            self.cancel_selection()
            return

        duration = opt_dict.get('time', 60)
        label = opt_dict.get('label', '自定义')
        sound = opt_dict.get('sound', None)
        
        # 1. 如果队列已满，移除最早的一个 (First-In, First-Out)
        if len(self.active_countdowns) >= config.COUNTDOWN_MAX_CONCURRENT:
            oldest = self.active_countdowns.pop(0)
            # 务必通知 ToastManager 移除对应的显示
            if self.toast_manager:
                self.toast_manager.remove_alert(oldest['id'])
            self.logger.info(f"倒计时队列已满，移除最早的: {oldest['label']}")

        # 2. 生成新对象
        self.id_counter += 1
        new_id = f"custom_cd_{self.id_counter}" # 使用特定前缀，方便调试
        
        target_time = self.anchor_game_time + duration
        new_entry = {
            'id': new_id,
            'target': target_time,
            'label': label,
            'sound': sound,
            'warned': False
        }
        
        self.active_countdowns.append(new_entry)
        self.logger.info(f"添加倒计时: {label}, 目标: {target_time}")

        # 3. 结束选择状态
        self.is_selecting = False
        self.selection_window.hide()
        self.hotkey_commit_timer.stop()
        self.anchor_game_time = None

    def remove_recent_countdown(self):
        """移除最近添加的一个倒计时 (LIFO: Last-In, First-Out)"""
        if not self.active_countdowns:
            self.logger.info("当前没有倒计时可清除")
            return

        # 移除列表末尾的元素（最近添加的）
        removed_entry = self.active_countdowns.pop()
        self.logger.info(f"已移除倒计时: {removed_entry['label']}")
        
        # 通知 ToastManager 清除显示
        if self.toast_manager:
            self.toast_manager.remove_alert(removed_entry['id'])

    def cancel_selection(self):
        self.is_selecting = False
        self.selection_window.hide()
        self.hotkey_commit_timer.stop()
        self.anchor_game_time = None
    
    def clear_all_countdowns(self):
        """清空所有当前的倒计时"""
        self.logger.info("正在清空所有自定义倒计时...")
        for entry in self.active_countdowns:
            if self.toast_manager:
                self.toast_manager.remove_alert(entry['id'])
        self.active_countdowns.clear()
        self.cancel_selection()

    def update_game_time(self, current_seconds, is_in_game):
        """
        每帧调用。管理所有活动的倒计时。
        :param current_seconds: 当前游戏时间
        :param is_in_game: 当前游戏界面状态 (传给 ToastManager 用)
        """
        # 遍历副本，因为可能会在循环中移除元素
        for entry in self.active_countdowns[:]:
            remaining = entry['target'] - current_seconds
            event_id = entry['id']
            
            # 1. 检查是否结束
            if remaining <= 0:
                if self.toast_manager:
                    self.toast_manager.remove_alert(event_id)
                self.active_countdowns.remove(entry)
                continue
            
            # 2. 准备显示内容
            # 格式: "BOSS: 55秒"
            message = f"{entry['label']}: {int(remaining)}秒"
            
            # 3. 检查是否需要播放声音
            sound_to_play = None
            
            warn_threshold = getattr(config, 'COUNTDOWN_WARNING_THRESHOLD_SECONDS', 10)
            if remaining <= warn_threshold:
                if not entry['warned']:
                    sound_to_play = entry['sound']
                    entry['warned'] = True
            
            # 4. 调用 ToastManager 显示
            # ToastManager 会自动处理 event_id 对应的堆叠位置
            custom_color = getattr(config, 'COUNTDOWN_DISPLAY_COLOR', 'rgb(0, 255, 255)')

            if self.toast_manager:
                self.toast_manager.show_map_countdown_alert(
                    event_id, 
                    remaining, 
                    message, 
                    is_in_game, 
                    sound_filename = sound_to_play,
                    default_color = custom_color # <--- 传入自定义颜色
                )

    def handle_hotkey_trigger(self, current_game_seconds):
        if not self.is_selecting:
            self.start_interaction(current_game_seconds)
        else:
            self.cycle_selection()
            
    def clear_all_countdowns(self):
        """清空所有当前的倒计时"""
        self.logger.info("正在清空所有自定义倒计时...")
        # 遍历当前列表，通知 ToastManager 移除每一个
        for entry in self.active_countdowns:
            if self.toast_manager:
                self.toast_manager.remove_alert(entry['id'])
        
        # 清空列表
        self.active_countdowns.clear()
        # 重置状态
        self.cancel_selection()