import asyncio
import os
import traceback

import win32gui
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QIcon, QPixmap, QColor, QPainter
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QPushButton, QGraphicsDropShadowEffect

import config
from fileutil import get_resources_dir
from logging_util import get_logger
from message_presenter import MessagePresenter
from window_utils import get_sc2_window_geometry

mutator_types = ['deployment', 'propagator', 'voidrifts', 'killbots', 'bombbots']
mutator_types_to_CHS = {'deployment': '部署', 'propagator': '小软', 'voidrifts': '裂隙', 'killbots': '杀戮',
                        'bombbots': '炸弹'}


class MutatorManager(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = get_logger(__name__)

        self.mutator_alert_labels = {}
        self.mutator_alert_timers = {}
        self.mutator_buttons = []

        self.active_mutator_time_points = {}

        # 增加一个字典来跟踪当前正在显示的提醒时间点，避免重复触发
        self.currently_alerting = {}

        self.init_mutator_ui()
        self.init_mutator_alerts()

    def init_mutator_ui(self):
        """初始化突变因子按钮UI"""
        layout = QHBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(4, 5, 8, 5)

        icon_paths = ['deployment.png', 'propagator.png', 'voidrifts.png', 'killbots.png', 'bombbots.png']
        for icon_name in icon_paths:
            btn = QPushButton()
            icon_path = os.path.join(get_resources_dir(), 'ico', 'mutator', icon_name)

            original_pixmap = QPixmap(icon_path)
            if original_pixmap.isNull():
                self.logger.warning(f"警告: 无法加载图标: {icon_path}")
                continue

            transparent_pixmap = self.create_transparent_pixmap(original_pixmap, config.MUTATOR_ICON_TRANSPARENCY)
            gray_pixmap = self.create_gray_pixmap(original_pixmap)
            gray_transparent_pixmap = self.create_transparent_pixmap(gray_pixmap, config.MUTATOR_ICON_TRANSPARENCY)

            btn.setIcon(QIcon(gray_transparent_pixmap))
            btn.setIconSize(QSize(26, 26))
            btn.setFixedSize(32, 32)
            btn.setCheckable(True)

            btn.setStyleSheet('''
                QPushButton { border: none; padding: 0px; 
                    border-radius: 3px; 
                    background-color: transparent; 
                    min-width: 30px; 
                    min-height: 30px; }
                QPushButton:checked { background-color: rgba(255, 255, 255, 0.1); margin-top: -1px; }
            ''')

            btn.original_icon = QIcon(transparent_pixmap)
            btn.gray_icon = QIcon(gray_transparent_pixmap)

            mutator_type = icon_name.split('.')[0]
            btn.setProperty("mutator_type", mutator_type)
            btn.toggled.connect(lambda checked, b=btn: self.on_mutator_toggled(b, checked))

            layout.addWidget(btn)
            self.mutator_buttons.append(btn)

        layout.addStretch()

    def create_transparent_pixmap(self, pixmap, opacity):
        """创建半透明的QPixmap"""
        transparent_pixmap = QPixmap(pixmap.size())
        transparent_pixmap.fill(Qt.transparent)
        painter = QPainter(transparent_pixmap)
        painter.setOpacity(opacity)
        painter.drawPixmap(0, 0, pixmap)
        painter.end()
        return transparent_pixmap

    def create_gray_pixmap(self, pixmap):
        """创建灰度的QPixmap"""
        gray_image = pixmap.toImage()
        for y in range(gray_image.height()):
            for x in range(gray_image.width()):
                color = gray_image.pixelColor(x, y)
                gray = int((color.red() * 0.299) + (color.green() * 0.587) + (color.blue() * 0.114))
                color.setRgb(gray, gray, gray, color.alpha())
                gray_image.setPixelColor(x, y, color)
        return QPixmap.fromImage(gray_image)

    def init_mutator_alerts(self):
        """初始化突变因子提醒标签"""

        for mutator_type in mutator_types:
            label = MessagePresenter(self.parent(), icon_name=f'{mutator_type}.png')
            self.mutator_alert_labels[mutator_type] = label

            '''
            label = QLabel(self.parent())
            label.setWindowFlags(
                Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
            )
            label.setAttribute(Qt.WA_TranslucentBackground)
            label.hide()
            self.mutator_alert_labels[mutator_type] = label
            '''

    def on_mutator_toggled(self, button, checked):
        mutator_type = button.property("mutator_type")

        if checked:
            button.setIcon(button.original_icon)
            shadow = QGraphicsDropShadowEffect()
            shadow.setBlurRadius(10)
            shadow.setXOffset(3)
            shadow.setYOffset(3)
            shadow.setColor(QColor(0, 0, 0, 160))
            button.setGraphicsEffect(shadow)

            time_points = self.load_mutator_config(mutator_type)
            self.active_mutator_time_points[mutator_type] = time_points
        else:
            button.setIcon(button.gray_icon)
            button.setGraphicsEffect(None)

            if mutator_type in self.active_mutator_time_points:
                del self.active_mutator_time_points[mutator_type]
            if mutator_type in self.currently_alerting:
                del self.currently_alerting[mutator_type]
            self.hide_mutator_alert(mutator_type)

    def load_mutator_config(self, mutator_name):
        """加载突变因子配置文件"""
        try:
            config_path = os.path.join('resources', 'mutator', f'{mutator_name}.txt')
            if not os.path.exists(config_path):
                self.logger.error(f'突变因子配置文件不存在: {config_path}')
                return []

            with open(config_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            time_points = []
            for line in lines:
                if line.strip():
                    parts = line.strip().split('\t')
                    if len(parts) >= 1:
                        time_str = parts[0].strip()
                        time_parts = time_str.split(':')
                        if len(time_parts) == 2:
                            seconds = int(time_parts[0]) * 60 + int(time_parts[1])
                            time_points.append(seconds)

            return sorted(time_points)

        except Exception as e:
            self.logger.error(f'加载突变因子配置失败: {str(e)}')
            self.logger.error(traceback.format_exc())
            return []

    def check_alerts(self, current_seconds, game_screen):
        """
        检查所有激活的突变因子，并持续更新倒计时提醒。
        此函数将由 qt_tui 中的 update_game_time 周期性调用。
        """
        sc2_rect = get_sc2_window_geometry()
        if not sc2_rect or game_screen != 'in_game':
            # 如果找不到SC2窗口，则隐藏所有提醒
            for label in self.mutator_alert_labels.values():
                label.hide()
            return

        for mutator_type, time_points in self.active_mutator_time_points.items():
            next_deployment_time = None
            for deployment_time in time_points:
                if deployment_time > current_seconds:
                    next_deployment_time = deployment_time
                    break

            if next_deployment_time and (
                    next_deployment_time - current_seconds) <= config.MUTATION_FACTOR_ALERT_SECONDS:
                time_remaining = next_deployment_time - current_seconds
                message = f"{mutator_types_to_CHS.get(mutator_type)} 还有: {int(time_remaining):0>2}秒 "
                self.show_mutator_alert(message, mutator_type, time_remaining)
            else:
                self.hide_mutator_alert(mutator_type)

    def show_mutator_alert(self, message, mutator_type='deployment', time_remaining=None):
        """
        显示/更新突变因子提醒，并根据剩余时间动态改变颜色。
        """
        sc2_rect = get_sc2_window_geometry()

        if not sc2_rect:
            self.hide_mutator_alert(mutator_type)
            return

        sc2_x, sc2_y, sc2_width, sc2_height = sc2_rect
        alert_label = self.mutator_alert_labels.get(mutator_type)

        if not alert_label:
            self.logger.warning(f"警告：未找到 mutator_type: {mutator_type} 对应的提醒标签。")
            return

        line_height = int(sc2_height * config.MUTATOR_ALERT_LINE_HEIGHT_PERCENT)
        font_size = int(line_height * config.MUTATOR_ALERT_FONT_SIZE_PERCENT_OF_LINE)

        if not isinstance(alert_label, MessagePresenter):
            icon_name = f"{mutator_type}.png"
            alert_label = MessagePresenter(self.parent(), icon_name=icon_name, font_size=font_size)
            self.mutator_alert_labels[mutator_type] = alert_label

        # 1. 设置标签的几何信息 
        alert_area_y = sc2_y + int(sc2_height * config.MUTATOR_ALERT_TOP_OFFSET_PERCENT)

        try:
            mutator_index = mutator_types.index(mutator_type)
            alert_label_y = alert_area_y + (mutator_index * line_height)
        except ValueError:
            self.logger.warning(f"未知的 mutator 类型: {mutator_type}")
            return

        horizontal_indent = int(sc2_width * config.MUTATOR_ALERT_HORIZONTAL_INDENT_PERCENT)
        alert_label_x = sc2_x + horizontal_indent

        # 设置窗口属性和大小
        alert_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        if (alert_label.x() != alert_label_x or alert_label.y() != alert_label_y
                or alert_label.width() != sc2_width or alert_label.height() != line_height):
            alert_label.setFixedSize(sc2_width, line_height)
            alert_label.move(alert_label_x, alert_label_y)
            #alert_label.setWindowFlags(
            #    Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WA_TranslucentBackground
            #)

        # 动态更新文本、颜色和字体大小
        text_color = config.MUTATION_FACTOR_NORMAL_COLOR
        if time_remaining is not None and time_remaining <= config.MUTATION_FACTOR_WARNING_THRESHOLD_SECONDS:
            text_color = config.MUTATION_FACTOR_WARNING_COLOR

        # 传递计算好的 font_size
        alert_label.update_alert(
            message,
            text_color,
            x=alert_label_x, y=alert_label_y,
            width=sc2_width, height=line_height,
            font_size=font_size
        )

    def hide_mutator_alert(self, mutator_type):
        """隐藏突变因子提醒"""
        if mutator_type in self.mutator_alert_labels:
            self.mutator_alert_labels[mutator_type].hide()

    def get_current_screen(self):
        return self.parent().get_current_screen()

    def on_control_state_changed(self, unlocked):
        for btn in self.mutator_buttons:
            btn.setAttribute(Qt.WA_TransparentForMouseEvents, not unlocked)
            if btn.isChecked():
                btn.setIcon(btn.original_icon)
            else:
                btn.setIcon(btn.gray_icon)


