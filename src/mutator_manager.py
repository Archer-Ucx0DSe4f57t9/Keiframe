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

mutator_types = ['AggressiveDeployment', 'Propagators', 'VoidRifts', 'KillBots', 'BoomBots', 
                 'HeroesFromtheStorm', 'AggressiveDeploymentProtoss'] # 
#名称到简略中文名称映射，用于提示显示
mutator_types_to_CHS = {'AggressiveDeployment': '部署', 'Propagators': '小软', 'VoidRifts': '裂隙', 'KillBots': '杀戮',
                        'BoomBots': '炸弹', 'HeroesFromtheStorm': '风暴', 'AggressiveDeploymentProtoss': '部署'}

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

        icon_paths = ['AggressiveDeployment.png', 'Propagators.png', 'VoidRifts.png', 'KillBots.png', 'BoomBots.png']
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
            config_path = os.path.join('resources', 'mutator', f'{mutator_name}.csv')
            if not os.path.exists(config_path):
                self.logger.error(f'突变因子配置文件不存在: {config_path}')
                return []

            with open(config_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            time_points_info = []
            for line in lines:
                if line.strip():
                    parts = line.strip().split(',')
                    if len(parts) >= 3:
                        time_str = parts[0].strip()
                        content_text = parts[1].strip() 
                        sound_filename = parts[2].strip() # <--- 新增：读取第 3 列的内容
                        
                        time_parts = time_str.split(':')
                        if len(time_parts) == 2:
                            seconds = int(time_parts[0]) * 60 + int(time_parts[1])
                            time_points_info.append((seconds, content_text, sound_filename))  #存储时间点、因子信息和音频文件名的元组

            return sorted(time_points_info,key=lambda x: x[0])  # 返回按时间排序的列表

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

        for mutator_type, time_points_info in self.active_mutator_time_points.items():
            next_deployment_info = None
            for deployment_seconds, content_text,sound_filename in time_points_info:
                if deployment_seconds > current_seconds:
                    next_deployment_info = (deployment_seconds, content_text,sound_filename)
                    break

            if next_deployment_info:
                next_deployment_time = next_deployment_info[0]
                content_to_show = next_deployment_info[1]
                warning_sound_filename = next_deployment_info[2] if len(next_deployment_info[2]) > 0 else None

            if (next_deployment_time - current_seconds) <= config.MUTATION_FACTOR_ALERT_SECONDS:
                time_remaining = next_deployment_time - current_seconds

                if (mutator_type == "AggressiveDeploymentProtoss" or mutator_type == "AggressiveDeployment"):
                    #部署因子涉及到强度信息
                     message = f"{int(time_remaining)}秒后：{mutator_types_to_CHS.get(mutator_type)} 强度：{content_to_show}"
                else:
                    #其他因子只涉及到数量，风暴不由mutatormanager播报
                    message = f"{int(time_remaining)}秒后：{mutator_types_to_CHS.get(mutator_type)}*{content_to_show} "


                self.show_mutator_alert(message, mutator_type, time_remaining,warning_sound_filename)
            else:
                self.hide_mutator_alert(mutator_type)

    def show_mutator_alert(self, message, mutator_type='deployment', time_remaining=None, warning_sound_filename=None):
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
            sound_filename = warning_sound_filename
        else:
            sound_filename = None

        # 传递计算好的 font_size
        alert_label.update_message(
            message,
            text_color,
            x=alert_label_x, y=alert_label_y,
            width=sc2_width, height=line_height,
            font_size=font_size,
            sound_filename=sound_filename
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
                # 激活状态 (彩色)
                btn.setIcon(btn.original_icon)
            else:
                # 非激活状态 (灰色)
                btn.setIcon(btn.gray_icon)

    def sync_mutator_toggles(self, confirmed_mutators):
        """
        根据识别器确认的突变因子列表，同步按钮的选中状态。
        confirmed_mutators: 识别器确认的突变因子名称列表 (e.g., ['propagator', 'deployment'])
        """
        self.logger.info(f"同步突变因子按钮状态: {confirmed_mutators}")

        if 'AggressiveDeployment' in confirmed_mutators and self.parent().game_state.enemy_race == 'Protoss':
            self.logger.warning("检测到 AggressiveDeployment 且敌方种族为 Protoss，切换到 AggressiveDeploymentProtoss 变式。")
            confirmed_mutators.remove('AggressiveDeployment')
            confirmed_mutators.append('AggressiveDeploymentProtoss')

        # 将所有按钮的信号暂时阻塞，避免在同步过程中触发 on_mutator_toggled 逻辑
        for btn in self.mutator_buttons:
            btn.blockSignals(True)

        try:
            for btn in self.mutator_buttons:
                mutator_type = btn.property("mutator_type")
                should_be_checked = mutator_type in confirmed_mutators

                # 1. 确保按钮的选中状态正确
                btn.setChecked(should_be_checked)

                # 2. 【关键修复】手动同步 UI 和加载配置，因为信号被阻塞
                if should_be_checked:
                    #确定加载配置名称
                    config_name_to_load = mutator_type
                    if mutator_type == 'AggressiveDeploymentProtoss':
                        config_name_to_load = 'AggressiveDeploymentProtoss'
                        self.logger.warning(f"应用变式: {mutator_type} + {self.parent().game_state.enemy_race } -> 加载 {config_name_to_load}")
                    
                    # 同步 UI 状态（图标和阴影）
                    btn.setIcon(btn.original_icon)
                    # 重新应用阴影效果（如果需要）
                    shadow = QGraphicsDropShadowEffect()
                    shadow.setBlurRadius(10)
                    shadow.setXOffset(3)
                    shadow.setYOffset(3)
                    shadow.setColor(QColor(0, 0, 0, 160))
                    btn.setGraphicsEffect(shadow)

                    # 重新加载配置 (核心步骤)
                    time_points = self.load_mutator_config(config_name_to_load)
                    
                    # 更新活动配置
                    self.active_mutator_time_points[mutator_type] = time_points #字典形式，键为原始mutator_type，在识别到protoss时可以更新值
                    self.logger.debug(f"通过同步加载 {mutator_type} 配置。")
                else:
                    # 同步 UI 状态 (灰色图标和清除阴影)
                    btn.setIcon(btn.gray_icon)
                    btn.setGraphicsEffect(None)

                    # 清除配置
                    if mutator_type in self.active_mutator_time_points:
                        del self.active_mutator_time_points[mutator_type]
                    self.hide_mutator_alert(mutator_type)

        finally:
            # 恢复所有按钮的信号
            for btn in self.mutator_buttons:
                btn.blockSignals(False)