#mutator_manager
import asyncio
import os
import traceback

import win32gui
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QIcon, QPixmap, QColor, QPainter
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QPushButton, QGraphicsDropShadowEffect

from src import config
from src.utils.fileutil import get_resources_dir
from src.utils.logging_util import get_logger
from src.output.message_presenter import MessagePresenter
from src.utils.window_utils import get_sc2_window_geometry
from src.game_state_service import state as game_state
from src.db.daos import load_mutator_by_name,get_all_mutator_names,get_all_notify_mutator_names


#名称到简略中文名称映射，用于提示显示,将来迁移到语言模块
mutator_names_to_CHS = {'AggressiveDeployment': '部署', 'Propagators': '小软', 'VoidRifts': '裂隙', 'KillBots': '杀戮',
                        'BoomBots': '炸弹', 'HeroesFromtheStorm': '风暴', 'AggressiveDeploymentProtoss': '部署神族'}



class MutatorManager(QWidget):
    def __init__(self, parent=None, mutators_db=None):
        super().__init__(parent)
        self.logger = get_logger(__name__)

        self.mutators_db = mutators_db
        self.mutator_names = get_all_mutator_names(self.mutators_db)
        self.notify_mutator_names = get_all_notify_mutator_names(self.mutators_db)
        # 突变因子提醒标签和定时器
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
        from PyQt5.QtWidgets import QVBoxLayout
        layout = QVBoxLayout(self)
        layout.setSpacing(1)
        layout.setContentsMargins(0, 5, 0, 0)

        mutator_list = self.mutator_names
        for mutator_name in mutator_list:
            btn = QPushButton()
            icon_path = os.path.join(get_resources_dir(), 'icons','mutators', f'{mutator_name}.png')

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
            btn.setToolTip(mutator_names_to_CHS.get(mutator_name.split('.')[0]))

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

            btn.setProperty("mutator_name", mutator_name)
            btn.toggled.connect(lambda checked, b=btn: self.on_mutator_toggled(b, checked))

            layout.addWidget(btn)
            self.mutator_buttons.append(btn)

        layout.addStretch()
        
        # 确保 MutatorManager 的尺寸适应所有按钮
        self.setFixedSize(layout.sizeHint())

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

        for mutator_name in self.notify_mutator_names:
            if len(load_mutator_by_name(self.mutators_db,mutator_name)) > 1:
                #只有1条一般只为不涉及时间点的提示，不需要提醒标签
                icon_path = os.path.join(get_resources_dir(), 'icons','mutators', f'{mutator_name}.png')
                label = MessagePresenter(self.parent(), icon_path = icon_path)
                self.mutator_alert_labels[mutator_name] = label


    def on_mutator_toggled(self, button, checked):
        mutator_name = button.property("mutator_name")

        if game_state.active_mutators is None:
            game_state.active_mutators = []

        if checked:

            if mutator_name not in game_state.active_mutators:
                game_state.active_mutators.append(mutator_name)

            button.setIcon(button.original_icon)
            shadow = QGraphicsDropShadowEffect()
            shadow.setBlurRadius(10)
            shadow.setXOffset(3)
            shadow.setYOffset(3)
            shadow.setColor(QColor(0, 0, 0, 160))
            button.setGraphicsEffect(shadow)
            
            if(self.is_muatator_required_to_notify(mutator_name)==True):
                time_points = self.load_mutator_config(mutator_name)
                self.active_mutator_time_points[mutator_name] = time_points
                self.logger.warning(f"手动加载 {mutator_name} 配置。时间点数量: {len(time_points)}")
        else:
            button.setIcon(button.gray_icon)
            button.setGraphicsEffect(None)

            if mutator_name in game_state.active_mutators:
                game_state.active_mutators.remove(mutator_name)

            if mutator_name in self.active_mutator_time_points:
                del self.active_mutator_time_points[mutator_name]
            if mutator_name in self.currently_alerting:
                del self.currently_alerting[mutator_name]
            self.hide_mutator_alert(mutator_name)

    def load_mutator_config(self, mutator_name):
        """加载突变因子配置文件"""
        try:
            time_points_info = []
            mutator_data = load_mutator_by_name(self.mutators_db,mutator_name)
            for a_mutator in mutator_data:
                time_points_info.append((a_mutator['time_value'],a_mutator['content_text'],a_mutator['sound_filename']))
            return time_points_info #dao已经排序

        except Exception as e:
            self.logger.error(f'加载突变因子配置失败: {str(e)}')
            self.logger.error(traceback.format_exc())
            return []

    def check_alerts(self, current_seconds, is_in_game):
        """
        检查所有激活的突变因子，并持续更新倒计时提醒。
        此函数将由 qt_tui 中的 update_game_time 周期性调用。
        """
        sc2_rect = get_sc2_window_geometry()
        if not sc2_rect or is_in_game == False:
            # 如果找不到SC2窗口，则隐藏所有提醒
            for label in self.mutator_alert_labels.values():
                label.hide()
            return

        for mutator_name, time_points_info in self.active_mutator_time_points.items():
            next_deployment_info = None
            for deployment_seconds, content_text,sound_filename in time_points_info:
                if deployment_seconds > current_seconds:
                    next_deployment_info = (deployment_seconds, content_text,sound_filename)
                    break
            
            if not next_deployment_info:
                self.hide_mutator_alert(mutator_name)
                continue # 跳到下一个 mutator_name

            next_deployment_time = next_deployment_info[0]
            content_to_show = next_deployment_info[1]
            warning_sound_filename = next_deployment_info[2] if len(next_deployment_info[2]) > 0 else None

            if (next_deployment_time - current_seconds) <= config.MUTATOR_ALERT_SECONDS:
                time_remaining = next_deployment_time - current_seconds

                if (mutator_name == "AggressiveDeploymentProtoss" or mutator_name == "AggressiveDeployment"):
                    #部署因子涉及到强度信息
                     message = f"{int(time_remaining)}秒后：{mutator_names_to_CHS.get(mutator_name)} 强度：{content_to_show}"
                else:
                    #其他因子只涉及到数量，风暴不由mutatormanager播报
                    message = f"{int(time_remaining)}秒后：{mutator_names_to_CHS.get(mutator_name)}*{content_to_show} "


                self.show_mutator_alert(message, mutator_name, time_remaining,warning_sound_filename)
            else:
                self.hide_mutator_alert(mutator_name)

    def show_mutator_alert(self, message, mutator_name='deployment', time_remaining=None, warning_sound_filename=None):
        """
        显示/更新突变因子提醒，并根据剩余时间动态改变颜色。
        """
        sc2_rect = get_sc2_window_geometry()

        if not sc2_rect:
            self.hide_mutator_alert(mutator_name)
            return

        sc2_x, sc2_y, sc2_width, sc2_height = sc2_rect
        alert_label = self.mutator_alert_labels.get(mutator_name)

        if not alert_label:
            self.logger.warning(f"警告：未找到 mutator_name: {mutator_name} 对应的提醒标签。")
            return

        line_height = int(getattr(config, 'MUTATOR_ALERT_LINE_HEIGHT', 32))
        font_size = int(getattr(config, 'MUTATOR_ALERT_FONT_SIZE', 19))

        if not isinstance(alert_label, MessagePresenter):
            icon_path = os.path.join(get_resources_dir(), 'icons','mutators', f'{mutator_name}.png')
            alert_label = MessagePresenter(self.parent(), icon_path=icon_path, font_size=font_size)
            self.mutator_alert_labels[mutator_name] = alert_label

        # 1. 设置标签的几何信息
        start_offset_y = int(getattr(config, 'MUTATOR_ALERT_OFFSET_Y', 324))
        alert_area_y = sc2_y + start_offset_y

        try:
            mutator_index = self.notify_mutator_names.index(mutator_name)
            alert_label_y = alert_area_y + (mutator_index * line_height)
        except ValueError:
            self.logger.warning(f"未知的 mutator 类型: {mutator_name}")
            return

        horizontal_indent = int(getattr(config, 'MUTATOR_ALERT_OFFSET_X', 19))
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
        text_color = config.MUTATOR_NORMAL_COLOR

        if time_remaining is not None and time_remaining <= config.MUTATOR_WARNING_THRESHOLD_SECONDS:
            text_color = config.MUTATOR_WARNING_COLOR
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

    def hide_mutator_alert(self, mutator_name):
        """隐藏突变因子提醒"""
        if mutator_name in self.mutator_alert_labels:
            self.mutator_alert_labels[mutator_name].hide()

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

    def is_muatator_required_to_notify(self, mutator_name):
        """检查某个突变因子是否需要提醒"""
        return mutator_name in self.notify_mutator_names
    
    def sync_mutator_toggles(self, confirmed_mutators):
        """
        根据识别器确认的突变因子列表，同步按钮的选中状态。
        confirmed_mutators: 识别器确认的突变因子名称列表 (e.g., ['propagator', 'deployment'])
        """
        self.logger.info(f"同步突变因子按钮状态: {confirmed_mutators}")

        if 'AggressiveDeployment' in confirmed_mutators and game_state.enemy_race == 'Protoss':
            self.logger.info("检测到 AggressiveDeployment 且敌方种族为 Protoss，切换到 AggressiveDeploymentProtoss 变式。")
            confirmed_mutators.remove('AggressiveDeployment')
            confirmed_mutators.append('AggressiveDeploymentProtoss')

        # 将所有按钮的信号暂时阻塞，避免在同步过程中触发 on_mutator_toggled 逻辑
        for btn in self.mutator_buttons:
            btn.blockSignals(True)

        try:
            for btn in self.mutator_buttons:
                mutator_name = btn.property("mutator_name")
                should_be_checked = mutator_name in confirmed_mutators

                # 1. 确保按钮的选中状态正确
                btn.setChecked(should_be_checked)

                # 2. 【关键修复】手动同步 UI 和加载配置，因为信号被阻塞
                if should_be_checked:
                    #确定加载配置名称
                    config_name_to_load = mutator_name
                    if mutator_name == 'AggressiveDeployment' and game_state.enemy_race == 'Protoss':
                        config_name_to_load = 'AggressiveDeploymentProtoss'
                        self.logger.info(f"应用变式: {mutator_name} + {game_state.enemy_race } -> 加载 {config_name_to_load}")
                    
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
                    
                    if time_points:
                        self.logger.info(f"配置 '{config_name_to_load}' 已成功加载 {len(time_points)} 个时间点。")
                    else:
                        # 如果没有时间点，可能是文件缺失或格式错误
                        self.logger.error(f"警告：配置 '{config_name_to_load}' 加载后时间点列表为空。")
                    
                    # 更新活动配置
                    self.active_mutator_time_points[mutator_name] = time_points #字典形式，键为原始mutator_name，在识别到protoss时可以更新值
                    self.logger.debug(f"通过同步加载 {mutator_name} 配置。")
                else:
                    # 同步 UI 状态 (灰色图标和清除阴影)
                    btn.setIcon(btn.gray_icon)
                    btn.setGraphicsEffect(None)

                    # 清除配置
                    if mutator_name in self.active_mutator_time_points:
                        del self.active_mutator_time_points[mutator_name]
                    self.hide_mutator_alert(mutator_name)
        except Exception as e:
                # 【捕获所有异常，并打印完整的堆栈信息】
                self.logger.error(f"FATAL ERROR during mutator sync: {str(e)}")
                self.logger.error(traceback.format_exc())
        finally:
            # 恢复所有按钮的信号
            for btn in self.mutator_buttons:
                btn.blockSignals(False)