from PyQt5.QtWidgets import QLabel, QWidget, QHBoxLayout, QVBoxLayout
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QPixmap
import os
import traceback
import asyncio
import config
from fileutil import get_resources_dir
from game_monitor import get_troop_from_game
from troop_util import TroopLoader
from outlined_label import OutlinedLabel
from message_presenter import MessagePresenter
from window_utils import get_sc2_window_geometry
from logging_util import get_logger

class ToastManager:
    
    def __init__(self, parent_window):
        self.parent = parent_window
        self.logger = parent_window.logger
        self.map_alerts = {}  # 用于存储地图事件的 MessagePresenter 实例

    def hide_toast(self):
        """隐藏Toast提示"""
        for alert in self.map_alerts.values():
            alert.hide_alert()

    def show_map_countdown_alert(self, event_id, time_diff, message, game_screen):

        new_event = False
        """
        根据事件ID显示或更新地图倒计时提示
        event_id: 地图事件的唯一标识符
        message: 显示的文本
        time_diff: 剩余的秒数，用于确定颜色
        """
        # 检查游戏状态，非游戏中状态不显示提示
        if game_screen != 'in_game':
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

        # 动态计算字体大小和行高
        line_height = int(sc2_height * config.MAP_ALERT_LINE_HEIGHT_PERCENT)
        font_size = int(line_height * config.MAP_ALERT_FONT_SIZE_PERCENT_OF_LINE)

        # 根据事件ID确定垂直位置
        # 例如，可以创建一个列表来维护事件的显示顺序
        # 假设你的事件ID可以按顺序排列
        event_ids = sorted(self.map_alerts.keys())
        try:
            event_index = event_ids.index(event_id)
            alert_label_y = sc2_y + int(sc2_height * config.MAP_ALERT_TOP_OFFSET_PERCENT) + (event_index * line_height)
        except ValueError:
            return  # 如果事件不在列表中，则不显示

        # 确定水平位置
        alert_label_x = sc2_x + int(sc2_width * config.MAP_ALERT_HORIZONTAL_INDENT_PERCENT)

        # 根据时间差设置颜色
        text_color = config.MAP_ALERT_NORMAL_COLOR  # 默认颜色
        if time_diff is not None and time_diff <= config.MAP_ALERT_WARNING_THRESHOLD_SECONDS:
            text_color = config.MAP_ALERT_WARNING_COLOR

        # 更新 MessagePresenter 的内容
        alert_label.update_alert(
            message,
            text_color,
            x=alert_label_x, y=alert_label_y,
            width=sc2_width, height=line_height,
            font_size=font_size
        )

    def remove_alert(self, event_id):
        if event_id in self.map_alerts:
            self.map_alerts[event_id].hide_alert()
            del self.map_alerts[event_id]

    def has_alert(self, event_id):
        return event_id in self.map_alerts

