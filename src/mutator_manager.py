import os
import sys
import time
import traceback
import win32gui
from PyQt5.QtWidgets import QWidget, QLabel, QHBoxLayout, QVBoxLayout, QPushButton, QGraphicsDropShadowEffect, \
    QApplication
from PyQt5.QtGui import QFont, QIcon, QPixmap, QBrush, QColor, QPainter
from PyQt5.QtCore import Qt, QTimer, QSize
import config
from fileutil import get_resources_dir
from debug_utils import format_time_to_mmss
from logging_util import get_logger
from mainfunctions import get_game_screen, most_recent_playerdata


class MutatorManager(QWidget):
    def __init__(self, parent=None):
        print(f'run MutatorManager {self.__init__.__name__}')
        super().__init__(parent)
        self.logger = get_logger(__name__)

        self.mutator_alert_labels = {}
        self.mutator_alert_timers = {}
        self.mutator_buttons = []

        # 移除定时器 self.mutator_timer

        self.init_mutator_ui()
        self.init_mutator_alerts()


    # ... (init_mutator_ui, create_transparent_pixmap, create_gray_pixmap, init_mutator_alerts 方法保持不变) ...
    def init_mutator_ui(self):
        print(f'run MutatorManager {self.init_mutator_ui.__name__}')
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
        print(f'run MutatorManager {self.create_transparent_pixmap.__name__}')
        """创建半透明的QPixmap"""
        transparent_pixmap = QPixmap(pixmap.size())
        transparent_pixmap.fill(Qt.transparent)
        painter = QPainter(transparent_pixmap)
        painter.setOpacity(opacity)
        painter.drawPixmap(0, 0, pixmap)
        painter.end()
        return transparent_pixmap

    def create_gray_pixmap(self, pixmap):
        print(f'run MutatorManager {self.create_gray_pixmap.__name__}')
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
        print(f'run MutatorManager {self.create_gray_pixmap.__name__}')
        """初始化突变因子提醒标签和定时器"""
        mutator_types = ['deployment', 'propagator', 'voidrifts', 'killbots', 'bombbots']
        for mutator_type in mutator_types:
            label = QLabel(self.parent())
            label.setWindowFlags(
                Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
            )
            label.setAttribute(Qt.WA_TranslucentBackground)
            label.hide()
            self.mutator_alert_labels[mutator_type] = label

            timer = QTimer()
            timer.timeout.connect(lambda t=mutator_type: self.hide_mutator_alert(t))
            self.mutator_alert_timers[mutator_type] = timer

    def on_mutator_toggled(self, button, checked):
        #print(f'run MutatorManager {self.on_mutator_toggled.__name__}')
        """处理突变按钮状态改变"""
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
            setattr(self, f'{mutator_type}_time_points', time_points)

            # 这里不再启动定时器
        else:
            button.setIcon(button.gray_icon)
            button.setGraphicsEffect(None)

            if hasattr(self, f'{mutator_type}_time_points'):
                delattr(self, f'{mutator_type}_time_points')
            if hasattr(self, f'alerted_{mutator_type}_time_points'):
                delattr(self, f'alerted_{mutator_type}_time_points')

    def load_mutator_config(self, mutator_name):
        print(f'run MutatorManager {self.load_mutator_config.__name__}')
        """加载突变因子配置文件"""
        # ... (保持不变) ...
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

    # 新增一个公共方法，让主窗口调用
    def check_alerts(self, current_seconds):
        #print(f'run MutatorManager {self.check_alerts.__name__}')
        """
        检查突变因子提醒。
        由主窗口的 update_game_time 方法调用。
        """
        try:
            mutator_types = ['deployment', 'propagator', 'voidrifts', 'killbots', 'bombbots']
            for i, mutator_type in enumerate(mutator_types):
                if not self.mutator_buttons[i].isChecked():
                    continue

                time_points_attr = f'{mutator_type}_time_points'
                if not hasattr(self, time_points_attr):
                    continue

                time_points = getattr(self, time_points_attr)
                alerted_points_attr = f'alerted_{mutator_type}_time_points'
                if not hasattr(self, alerted_points_attr):
                    setattr(self, alerted_points_attr, set())

                alerted_points = getattr(self, alerted_points_attr)
                for time_point in time_points:
                    if time_point in alerted_points:
                        continue

                    time_diff = time_point - current_seconds

                    if 0 < time_diff <= config.MUTATION_FACTOR_ALERT_SECONDS:
                        config_path = os.path.join('resources', 'mutator', f'{mutator_type}.txt')
                        with open(config_path, 'r', encoding='utf-8') as f:
                            lines = f.readlines()
                        second_column_text = ''
                        for line in lines:
                            if line.strip():
                                parts = line.strip().split('\t')
                                if len(parts) >= 2:
                                    time_str = parts[0].strip()
                                    time_parts = time_str.split(':')
                                    if len(time_parts) == 2:
                                        line_seconds = int(time_parts[0]) * 60 + int(time_parts[1])
                                        if line_seconds == time_point:
                                            second_column_text = parts[1].strip()
                                            break

                        self.show_mutator_alert(f"{time_diff} 秒后 {second_column_text}", mutator_type)
                        alerted_points.add(time_point)
        except Exception as e:
            self.logger.error(f'检查突变因子提醒失败: {str(e)}')
            self.logger.error(traceback.format_exc())

    def show_mutator_alert(self, message, mutator_type='deployment'):
        """
        显示突变因子提醒，并根据“StarCraft II”窗口位置动态定位。
        """
        sc2_rect = self._get_sc2_window_geometry()
        if not sc2_rect:
            self.logger.warning("未找到 'StarCraft II' 窗口，无法显示提醒。")
            return

        sc2_x, sc2_y, sc2_width, sc2_height = sc2_rect

        # 1. 计算提醒区域的动态位置和尺寸
        alert_area_y = sc2_y + int(sc2_height * config.MUTATOR_ALERT_TOP_OFFSET_PERCENT)

        # 行高为窗口高度的 4%
        line_height = int(sc2_height * config.MUTATOR_ALERT_FONT_SIZE_PERCENT)

        # 字体大小为行高的 80%，以确保不被裁剪
        font_size = int(line_height * 0.8)

        # 2. 确定当前 mutator 提醒的垂直位置和水平缩进
        mutator_types = ['deployment', 'propagator', 'voidrifts', 'killbots', 'bombbots']
        try:
            mutator_index = mutator_types.index(mutator_type)
            alert_label_y = alert_area_y + (mutator_index * line_height)
        except ValueError:
            self.logger.warning(f"未知的 mutator 类型: {mutator_type}")
            return

        # 使用新的配置常量计算水平缩进
        horizontal_indent = int(sc2_width * config.MUTATOR_ALERT_HORIZONTAL_INDENT_PERCENT)
        alert_label_x = sc2_x + horizontal_indent

        # 打印调试信息，检查计算出的缩进值
        self.logger.debug(f"窗口宽度: {sc2_width}px, 计算出的水平缩进: {horizontal_indent}px")

        alert_label = self.mutator_alert_labels.get(mutator_type)
        if not alert_label:
            return

        # 3. 确保所有相关控件都能正确穿透鼠标事件
        # ... (以下代码与之前版本相同) ...
        alert_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        alert_label.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WA_TranslucentBackground
        )

        if alert_label.layout():
            layout = alert_label.layout()
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
        else:
            layout = QHBoxLayout(alert_label)

        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        icon_name = f'{mutator_type}.png'
        icon_path = os.path.join(get_resources_dir(), 'ico', 'mutator', icon_name)
        display_text = message

        if os.path.exists(icon_path):
            icon_label = QLabel()
            icon_size = font_size
            icon_label.setPixmap(
                QPixmap(icon_path).scaled(icon_size, icon_size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            layout.addWidget(icon_label)

        text_label = QLabel(display_text)
        text_label.setFont(QFont('Arial', font_size))
        text_label.setStyleSheet(f'color: {config.MUTATOR_DEPLOYMENT_COLOR}; background-color: transparent;')
        layout.addWidget(text_label)

        # 4. 动态设置标签的位置和大小
        alert_label.setFixedSize(sc2_width, line_height)
        alert_label.move(alert_label_x, alert_label_y)

        alert_label.show()
        self.mutator_alert_timers[mutator_type].start(config.TOAST_DURATION)
    '''
    def show_mutator_alert(self, message, mutator_type='deployment'):
        print(f'run MutatorManager {self.show_mutator_alert.__name__}')
        """显示突变因子提醒"""
        if get_game_screen() != 'in_game':
            return

        alert_label = self.mutator_alert_labels.get(mutator_type)
        if not alert_label:
            return

        parent_window = self.parent()
        screen_geometry = parent_window.geometry() if parent_window else QApplication.primaryScreen().geometry()

        alert_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        if alert_label.layout():
            layout = alert_label.layout()
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
        else:
            layout = QVBoxLayout(alert_label)

        layout.setContentsMargins(5, 5, 5, 5)
        layout.setAlignment(Qt.AlignLeft)

        alert_widget = QWidget()
        alert_widget.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        alert_widget.setAttribute(Qt.WA_NoSystemBackground)
        alert_widget.setAttribute(Qt.WA_TranslucentBackground)
        alert_layout = QHBoxLayout(alert_widget)
        alert_layout.setContentsMargins(0, 0, 0, 0)
        alert_layout.setAlignment(Qt.AlignLeft)

        icon_name = f'{mutator_type}.png'
        icon_path = os.path.join(get_resources_dir(), 'ico', 'mutator', icon_name)
        display_text = message

        if os.path.exists(icon_path):
            icon_label = QLabel()
            icon_label.setPixmap(QPixmap(icon_path).scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            alert_layout.addWidget(icon_label)

        text_label = QLabel(display_text)
        text_label.setStyleSheet(
            f'color: {config.MUTATOR_DEPLOYMENT_COLOR}; font-size: {config.TOAST_MUTATOR_FONT_SIZE}px')
        alert_layout.addWidget(text_label)

        alert_widget.setLayout(alert_layout)
        layout.addWidget(alert_widget)

        alert_label.setFixedWidth(250)

        position_map = {
            'voidrifts': config.MUTATOR_RIFT_POS, 'propagator': config.MUTATOR_PROPAGATOR_POS,
            'deployment': config.MUTATOR_DEPLOYMENT_POS, 'killbots': config.MUTATOR_KILLBOTS_POS,
            'bombbots': config.MUTATOR_BOMBBOTS_POS
        }
        parent_window = self.parent()
        screen_geometry = parent_window.geometry() if parent_window else QApplication.primaryScreen().geometry()
        x = screen_geometry.x() + int(screen_geometry.width() * position_map.get(mutator_type, 0.5)) - 125
        y = int(screen_geometry.height() * config.MUTATOR_TOAST_POSITION)
        alert_label.move(x, y)

        alert_label.show()
        self.mutator_alert_timers[mutator_type].start(config.TOAST_DURATION)
    '''

    def hide_mutator_alert(self, mutator_type):
        #print(f'run MutatorManager {self.hide_mutator_alert.__name__}')
        """隐藏突变因子提醒"""
        if mutator_type in self.mutator_alert_labels:
            self.mutator_alert_labels[mutator_type].hide()
            self.mutator_alert_timers[mutator_type].stop()

    # 注意：get_current_screen 方法需要从 qt_gui.py 中迁移过来，或者让 qt_gui.py 将屏幕信息传递给 MutatorManager。
    # 假设 get_game_screen 和 get_current_screen 等辅助函数在新模块中可以访问。
    def get_current_screen(self):
        print(f'run MutatorManager {self.get_current_screen.__name__}')
        return self.parent().get_current_screen()

    def on_control_state_changed(self, unlocked):
        #print(f'run MutatorManager {self.on_control_state_changed.__name__}')
        """根据主窗口的锁定状态更新按钮的事件穿透属性"""
        for btn in self.mutator_buttons:
            btn.setAttribute(Qt.WA_TransparentForMouseEvents, not unlocked)

            if btn.isChecked():
                btn.setIcon(btn.original_icon)
            else:
                btn.setIcon(btn.gray_icon)

    """
    通过窗口标题获取“StarCraft II”窗口的几何信息。
    如果未找到窗口，则返回 None。
    """
    def _get_sc2_window_geometry(self):
        try:
            hwnd = win32gui.FindWindow(None, "StarCraft II")
            if hwnd:
                rect = win32gui.GetWindowRect(hwnd)
                x = rect[0]
                y = rect[1]
                w = rect[2] - x
                h = rect[3] - y
                print(f'found StarCraft II with {x}, {y}, {w}, {h}')
                return x, y, w, h
        except Exception as e:
            self.logger.error(f"获取'StarCraft II'窗口几何信息失败: {e}")
        return None