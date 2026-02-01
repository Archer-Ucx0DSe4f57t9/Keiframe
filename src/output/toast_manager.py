from PyQt5.QtWidgets import QLabel, QWidget, QHBoxLayout, QVBoxLayout
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QPixmap
import os
import traceback
import asyncio
from src import config
from src.troop_util import TroopLoader
from src.output.message_presenter import MessagePresenter
from src.utils.window_utils import get_sc2_window_geometry

class ToastManager:
    
    def __init__(self, parent_window):
        self.parent = parent_window
        self.logger = parent_window.logger
        self.map_alerts = {}  # 用于存储地图事件的 MessagePresenter 实例

    def hide_toast(self):
        """隐藏Toast提示"""
        for alert in self.map_alerts.values():
            alert.hide_alert()

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

        # 根据事件ID获取或创建 MessagePresenter 实例
        if event_id not in self.map_alerts:
            # 如果是新事件，创建一个新的 MessagePresenter
            self.map_alerts[event_id] = MessagePresenter(icon_name=None)
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

        # 根据时间差设置颜色
        # 1. 优先使用传入的 default_color (自定义倒计时颜色)
        # 2. 如果没有传入，使用 config.MAP_ALERT_NORMAL_COLOR (地图事件默认颜色)
        text_color = default_color if default_color else config.MAP_ALERT_NORMAL_COLOR

        final_sound_filename = None

        if time_diff is not None and time_diff <= config.MAP_ALERT_WARNING_THRESHOLD_SECONDS:
            text_color = config.MAP_ALERT_WARNING_COLOR
            if sound_filename:
                final_sound_filename = sound_filename

        # 更新 MessagePresenter 的内容
        alert_label.update_message(
            message,
            text_color,
            x=alert_label_x, y=alert_label_y,
            width=sc2_width, # 宽度依然可以保持跟随窗口，或者你也想改成固定宽度？
            height=line_height,
            font_size=font_size,
            sound_filename=final_sound_filename
        )

    def remove_alert(self, event_id):
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