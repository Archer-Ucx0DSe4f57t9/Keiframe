from PyQt5.QtWidgets import QLabel, QWidget, QHBoxLayout, QVBoxLayout
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QPixmap
import os
import traceback
import asyncio
import time
from src import config
from src.troop_util import TroopLoader
from src.presentation_modules.message_presenter import MessagePresenter
from src.utils.window_utils import get_sc2_window_geometry

class ToastManager:
    
    def __init__(self, parent_window):
        self.parent = parent_window
        self.logger = parent_window.logger
        self.map_alerts = {}  # 用于存储地图事件的 MessagePresenter 实例
        self.warning_flash_states = {}
        self.warning_flash_timer = QTimer()
        self.warning_flash_timer.setInterval(self._warning_flash_interval_ms())
        self.warning_flash_timer.timeout.connect(self._on_warning_flash_timeout)

    @staticmethod
    def _warning_flash_enabled():
        return bool(getattr(config, 'WARNING_FLASH_ENABLED', True))

    @staticmethod
    def _warning_flash_interval_ms():
        return max(1, int(getattr(config, 'WARNING_FLASH_INTERVAL_MS', 500)))

    def _start_warning_flash_timer(self):
        if not self._warning_flash_enabled():
            return

        interval_ms = self._warning_flash_interval_ms()
        if self.warning_flash_timer.interval() != interval_ms:
            self.warning_flash_timer.setInterval(interval_ms)
        if not self.warning_flash_timer.isActive():
            self.warning_flash_timer.start()

    def _stop_warning_flash_timer_if_idle(self):
        if not self.warning_flash_states or not self._warning_flash_enabled():
            self.warning_flash_timer.stop()

    @staticmethod
    def _alert_is_visible(alert):
        is_visible = getattr(alert, 'isVisible', None)
        if not callable(is_visible):
            return True
        try:
            return bool(is_visible())
        except Exception:
            return True

    @staticmethod
    def _state_color(state):
        if state.get('show_warning_color', False):
            return state['warning_color']
        return state['normal_color']

    def _refresh_warning_alert(self, event_id, state):
        alert = self.map_alerts.get(event_id)
        if alert is None or not self._alert_is_visible(alert):
            return

        alert.update_message(
            state['message'],
            self._state_color(state),
            x=state['x'],
            y=state['y'],
            width=state['width'],
            height=state['height'],
            font_size=state['font_size'],
            sound_filename=None,
            vertical_offset=state['vertical_offset'],
        )

    def _on_warning_flash_timeout(self):
        """按现实时间切换每个地图事件的 warning 显示颜色。"""
        if not self._warning_flash_enabled():
            for event_id, state in self.warning_flash_states.items():
                state['show_warning_color'] = True
                self._refresh_warning_alert(event_id, state)
            self.warning_flash_timer.stop()
            return

        now = time.monotonic()
        interval_seconds = self._warning_flash_interval_ms() / 1000.0
        for event_id, state in list(self.warning_flash_states.items()):
            if not state.get('warning_active', False):
                self.warning_flash_states.pop(event_id, None)
                continue

            if now < state.get('next_toggle_time', now):
                continue

            state['show_warning_color'] = not state.get('show_warning_color', False)
            state['next_toggle_time'] = now + interval_seconds
            self._refresh_warning_alert(event_id, state)

        self._stop_warning_flash_timer_if_idle()

    def _clear_warning_flash_state(self, event_id):
        self.warning_flash_states.pop(event_id, None)
        self._stop_warning_flash_timer_if_idle()

    def _clear_warning_flash_states(self):
        self.warning_flash_states.clear()
        self.warning_flash_timer.stop()

    def hide_toast(self):
        """隐藏Toast提示"""
        for alert in self.map_alerts.values():
            alert.hide_alert()
        self._clear_warning_flash_states()

    def show_map_countdown_alert(self, event_id, time_diff, message, is_in_game, sound_filename: str = None, default_color=None):
        self.logger.debug(f"尝试播报信息{message}")
        
        new_event = False
        """
        根据事件ID显示或更新地图倒计时提示
        event_id: 地图事件的唯一标识符
        message: 显示的文本
        time_diff: 剩余的秒数，用于确定颜色
        """
        # 检查游戏状态，非游戏中状态不显示提示
        if is_in_game == False:
            self.hide_toast()
            return

        # 事件结束后由调用方通常直接 remove_alert；这里也保护直接调用者。
        if time_diff is not None and time_diff <= 0:
            self.remove_alert(event_id)
            return

        # 根据事件ID获取或创建 MessagePresenter 实例
        if event_id not in self.map_alerts:
            # 如果是新事件，创建一个新的 MessagePresenter
            self.map_alerts[event_id] = MessagePresenter(icon_path=None)
            new_event = True

        alert_label = self.map_alerts[event_id]
        if new_event:
            #alert_label.setWindowFlags(
            #    Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WA_TranslucentBackground
            #)
            alert_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            alert_label.setAttribute(Qt.WA_TranslucentBackground, True)
        sc2_rect = get_sc2_window_geometry()
        if not sc2_rect:
            alert_label.hide_alert()
            return


        sc2_x, sc2_y, sc2_width, sc2_height = sc2_rect
        
        # 使用自定义 key 进行排序
        # 结果示例: [map_event_1, map_event_5, custom_cd_1, custom_cd_2]
        

        # 动态计算字体大小和行高
        # 1. 计算行高和字体大小
        line_height = config.TOAST_LINE_HEIGHT
        font_size = config.TOAST_FONT_SIZE

        # 2. 计算垂直位置 (Y)
        # 获取当前所有的事件ID并排序，决定谁在第一行，谁在第二行
        offset_y = getattr(config, 'TOAST_OFFSET_Y', 150)
        offset_x = getattr(config, 'TOAST_OFFSET_X', 19) # 默认1920*0.01防报错
        line_height = getattr(config, 'TOAST_LINE_HEIGHT', 40) # 假设你设置了固定值
        
        
        def get_sort_key(eid):
            # 如果是 map_event 开头，优先级为 0 (最高，排在最上面)
            if eid.startswith('map_event'):
                return (0, eid)
            # 其他（如 custom_cd），优先级为 1 (排在地图事件下面)
            else:
                return (1, eid)


        event_ids = sorted(self.map_alerts.keys(), key=get_sort_key)
        
        try:
            # 获取当前事件在排序后的列表中的索引
            # 这个索引直接决定了它在第几行 (index * line_height)
            event_index = event_ids.index(event_id)
            alert_label_y = sc2_y + offset_y + (event_index * line_height)
        except ValueError:
            return

        # 确定水平位置
        alert_label_x = sc2_x + offset_x

        # 根据时间差设置颜色。warning 的相位和声音状态由 ToastManager 保存，
        # 不因每次游戏秒更新而重新初始化。
        # 1. 优先使用传入的 default_color (自定义倒计时颜色)
        # 2. 如果没有传入，使用 config.MAP_ALERT_NORMAL_COLOR (地图事件默认颜色)
        normal_color = default_color if default_color else config.MAP_ALERT_NORMAL_COLOR
        warning_color = config.MAP_ALERT_WARNING_COLOR
        warning_active = (
            time_diff is not None
            and time_diff > 0
            and time_diff <= config.MAP_ALERT_WARNING_THRESHOLD_SECONDS
        )

        final_sound_filename = None

        if warning_active:
            state = self.warning_flash_states.get(event_id)
            if state is None:
                flash_enabled = self._warning_flash_enabled()
                state = {
                    'warning_active': True,
                    'show_warning_color': not flash_enabled,
                    'next_toggle_time': time.monotonic() + (
                        self._warning_flash_interval_ms() / 1000.0
                    ),
                    'sound_played': False,
                }
                self.warning_flash_states[event_id] = state

            state.update({
                'warning_active': True,
                'message': message,
                'normal_color': normal_color,
                'warning_color': warning_color,
                'x': alert_label_x,
                'y': alert_label_y,
                'width': sc2_width,
                'height': line_height,
                'font_size': font_size,
                'vertical_offset': getattr(config, 'TOAST_VERTICAL_OFFSET', 0),
            })

            if not self._warning_flash_enabled():
                state['show_warning_color'] = True
                self.warning_flash_timer.stop()
            else:
                self._start_warning_flash_timer()

            text_color = self._state_color(state)
            if not state['sound_played'] and sound_filename:
                final_sound_filename = sound_filename
                state['sound_played'] = True
        else:
            self._clear_warning_flash_state(event_id)
            text_color = normal_color

        # 更新 MessagePresenter 的内容
        alert_label.update_message(
            message,
            text_color,
            x=alert_label_x, 
            y=alert_label_y,
            width=sc2_width, # 宽度依然可以保持跟随窗口，或者你也想改成固定宽度？
            height=line_height,
            font_size=font_size,
            sound_filename=final_sound_filename,
            vertical_offset=getattr(config,'TOAST_VERTICAL_OFFSET',0) # 从config读取垂直偏移，默认为0
        )

    def remove_alert(self, event_id):
        self._clear_warning_flash_state(event_id)
        if event_id in self.map_alerts:
            alert_instance = self.map_alerts.get(event_id)
            if alert_instance and hasattr(alert_instance, 'hide_alert'):
                alert_instance.hide_alert()
            del self.map_alerts[event_id]

    def has_alert(self, event_id):
        return event_id in self.map_alerts

    def clear_all_alerts(self):
        self.logger.info("正在清除所有屏幕提示 (toasts)...")
        # 使用 list() 来创建一个字典值的副本进行迭代，
        # 这样在循环内部修改字典是安全的。
        for alert_id in list(self.map_alerts.keys()):
            self.remove_alert(alert_id) # 复用已有的 remove_alert 逻辑
        # 确保字典最终为空
        self.map_alerts.clear()
        self.warning_flash_states.clear()
        self.warning_flash_timer.stop()

    def shutdown(self):
        """停止闪烁定时器并清理所有 Toast。"""
        self.clear_all_alerts()
