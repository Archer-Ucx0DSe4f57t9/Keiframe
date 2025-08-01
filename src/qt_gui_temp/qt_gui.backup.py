import os
import sys
import re
import time
import traceback
import keyboard
import ctypes
import win32gui
from ctypes import windll
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QLabel, QSystemTrayIcon, 
    QMenu, QAction, QApplication, QComboBox, 
    QTableWidgetItem, QPushButton, QTableWidget, 
    QHeaderView, QVBoxLayout, QGraphicsDropShadowEffect, QHBoxLayout
    , QLineEdit # 从 QtWidgets 导入
)
from control_window import ControlWindow
from commander_selector import CommanderSelector
from PyQt5.QtGui import (
    QFont, QIcon, QPixmap, QBrush,
    QColor, QCursor
)
from PyQt5.QtCore import Qt, QTimer, QPoint, pyqtSignal, QRect, QSize
import config
from PyQt5 import QtCore

import image_util
from fileutil import get_resources_dir, list_files

class TimerWindow(QMainWindow):
    # 创建信号用于地图更新
    progress_signal = QtCore.pyqtSignal(list)
    toggle_artifact_signal = pyqtSignal()


    def __init__(self):
        super().__init__()
        
        # 初始化artifact_window
        from artifacts import ArtifactWindow
        self.artifact_window = ArtifactWindow(self)

        # 设置窗口属性以支持DPI缩放
        self.setAttribute(Qt.WA_DontCreateNativeAncestors)
        self.setAttribute(Qt.WA_NativeWindow)
        if getattr(sys, 'frozen', False):  # 是否为打包的 exe
            base_dir = os.path.dirname(sys.executable)  # exe 所在目录
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # 源码所在目录

        # 初始化日志记录器
        from logging_util import get_logger
        self.logger = get_logger(__name__)
        self.logger.info('SC2 Timer 启动')
        
        # 初始化状态
        self.current_time = ""
        self.drag_position = QPoint(0, 0)
        
        # 添加一个标志来追踪地图选择的来源
        self.manual_map_selection = False
        
        # 初始化UI
        self.init_ui()
        
        # 初始化Toast提示
        self.init_toast()
        
        # 初始化定时器
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_game_time)
        self.timer.start(100)  # 自动开始更新，每100毫秒更新一次
        
        # 初始化突变因子提醒标签和定时器
        self.mutator_alert_labels = {}
        self.mutator_alert_timers = {}
        
        # 为每种突变因子类型创建独立的标签和定时器
        for mutator_type in ['deployment', 'propagator', 'voidrifts', 'killbots', 'bombbots']:
            label = QLabel(self)
            label.setWindowFlags(
                Qt.FramelessWindowHint |
                Qt.WindowStaysOnTopHint |
                Qt.Tool
            )
            label.setAttribute(Qt.WA_TranslucentBackground)
            label.hide()
            self.mutator_alert_labels[mutator_type] = label
            
            timer = QTimer()
            timer.timeout.connect(lambda t=mutator_type: self.hide_mutator_alert(t))
            self.mutator_alert_timers[mutator_type] = timer
        
        # 连接表格区域的双击事件
        self.table_area.mouseDoubleClickEvent = self.on_text_double_click
        
        # 初始化系统托盘
        self.init_tray()
        
        # 创建控制窗体
        self.control_window = ControlWindow()
        self.control_window.move(self.x(), self.y() - self.control_window.height())
        self.control_window.show()

        # 连接控制窗口的状态改变信号
        self.control_window.state_changed.connect(self.on_control_state_changed)
        
        # 监听主窗口位置变化
        self.windowHandle().windowStateChanged.connect(self.update_control_window_position)
        
        # 连接信号到处理函数
        self.progress_signal.connect(self.handle_progress_update)
        
        # 初始化全局快捷键
        self.init_global_hotkeys()
        
        # 启动游戏检查线程
        from mainfunctions import check_for_new_game
        import threading
        self.game_check_thread = threading.Thread(target=check_for_new_game, args=(self.progress_signal,), daemon=True)
        self.game_check_thread.start()
        
        # 初始化时设置为锁定状态（不可点击）
        # 使用延迟调用，确保窗口已完全初始化
        QTimer.singleShot(100, lambda: self.on_control_state_changed(False))
        
    def get_current_screen(self):
        """获取当前窗口所在的显示器"""
        window_geometry = self.geometry()
        window_center = window_geometry.center()
        
        # 获取所有显示器
        screens = QApplication.screens()
        
        # 遍历所有显示器，检查窗口中心点是否在显示器范围内
        for screen in screens:
            screen_geometry = screen.geometry()
            if screen_geometry.contains(window_center):
                return screen
        
        # 如果没有找到，返回主显示器
        return QApplication.primaryScreen()
    
    def update_control_window_position(self):
        # 保持控制窗口与主窗口位置同步
        current_screen = self.get_current_screen()
        screen_geometry = current_screen.geometry()
        
        # 确保控制窗口不会超出屏幕顶部
        new_y = max(screen_geometry.y(), self.y() - self.control_window.height())
        self.control_window.move(self.x(), new_y)

    def moveEvent(self, event):
        """鼠标移动事件，用于更新控制窗口位置"""
        super().moveEvent(event)
        if hasattr(self, 'control_window'):
            self.update_control_window_position()

        
        #更新搜索内容
        def update_combo_box(keyword, allow_auto_select=True):
            
            keyword = keyword.strip().lower()
            current_selected = self.combo_box.currentText()

            
            self.combo_box.blockSignals(True)  # 🚫 禁止选项变化触发 currentTextChanged
            self.combo_box.clear()

            filtered = [f for f in self.files if keyword in f.lower()]

            mapped_result = config.MAP_SEARCH_KEYWORDS.get(keyword)
            if mapped_result and mapped_result not in filtered and mapped_result in self.files:
                filtered.insert(0, mapped_result)

            self.combo_box.addItems(filtered)
            
            # ✅ 如果不是自动选择场景，恢复原选项
            if not allow_auto_select and current_selected in filtered:
                index = self.combo_box.findText(current_selected)
                if index >= 0:
                    self.combo_box.setCurrentIndex(index)

            self.combo_box.blockSignals(False)

            # ✅ 只在明确需要时触发地图变更
            if filtered and allow_auto_select:
                self.on_map_selected(filtered[0])

        # 用户输入时触发（允许自动选择）
        def filter_combo_box_user():
            keyword = self.search_box.text().strip().lower()
            update_combo_box(keyword, allow_auto_select=True)

        # 自动清除时触发（禁止自动选择）
        def filter_combo_box_clear():
            update_combo_box("", allow_auto_select=False)
            self.search_box.blockSignals(True)
            self.search_box.setText("")  # 不触发 filter_combo_box_user
            self.search_box.blockSignals(False)
        
        #根据搜索更新可选列表
        def restart_clear_timer():
            self.clear_search_timer.stop()
            self.clear_search_timer.start(30000)  # 30秒

        #搜索框关联
        self.search_box.textChanged.connect(filter_combo_box_user)
        self.search_box.textChanged.connect(restart_clear_timer)
        self.clear_search_timer.timeout.connect(filter_combo_box_clear)
        self.combo_box.currentTextChanged.connect(self.on_map_selected)
        
        # 调整时间标签的位置和高度
        self.time_label.setGeometry(10, 40, 100, 20)
        
        # 在表格区域之后添加图标区域
        self.icon_area = QWidget(self.main_container)
        icon_layout = QHBoxLayout()  # 不要在构造函数中传入父widget
        self.icon_area.setLayout(icon_layout)  # 单独设置布局
        
        # 设置图标区域的样式，便于调试
        self.icon_area.setStyleSheet("""
            QWidget {
                background-color: rgba(43, 43, 43, 96);
                border-radius: 5px;
            }
        """)
        
        # 图标文件路径
        icon_paths = ['deployment.png', 'propagator.png', 'voidrifts.png', 'killbots.png', 'bombbots.png']
        self.mutator_buttons = []
        
        for icon_name in icon_paths:
            btn = QPushButton()
            icon_path = os.path.join('ico', 'mutator', icon_name)
            
            # 打印调试信息
            print(f"尝试加载图标: {os.path.abspath(icon_path)}")
            print(f"文件是否存在: {os.path.exists(icon_path)}")
            
            # 加载原始图标
            original_pixmap = QPixmap(icon_path)
            if original_pixmap.isNull():
                print(f"警告: 无法加载图标: {icon_path}")
                continue
                
            # 创建半透明版本
            from PyQt5.QtGui import QPainter
            transparent_pixmap = QPixmap(original_pixmap.size())
            transparent_pixmap.fill(Qt.transparent)  # 填充透明背景
            painter = QPainter(transparent_pixmap)
            painter.setOpacity(config.MUTATOR_ICON_TRANSPARENCY)  # 设置70%不透明度
            painter.drawPixmap(0, 0, original_pixmap)
            painter.end()
                
            # 创建灰色版本
            gray_image = original_pixmap.toImage()
            for y in range(gray_image.height()):
                for x in range(gray_image.width()):
                    color = gray_image.pixelColor(x, y)
                    gray = int((color.red() * 0.299) + (color.green() * 0.587) + (color.blue() * 0.114))
                    color.setRgb(gray, gray, gray, color.alpha())
                    gray_image.setPixelColor(x, y, color)
            gray_pixmap = QPixmap.fromImage(gray_image)
            
            # 创建灰色半透明版本
            gray_transparent_pixmap = QPixmap(gray_pixmap.size())
            gray_transparent_pixmap.fill(Qt.transparent)  # 填充透明背景
            painter = QPainter(gray_transparent_pixmap)
            painter.setOpacity(config.MUTATOR_ICON_TRANSPARENCY)  # 设置70%不透明度
            painter.drawPixmap(0, 0, gray_pixmap)
            painter.end()
            
            # 设置按钮属性
            btn.setIcon(QIcon(transparent_pixmap))  # 默认使用半透明图标
            btn.setIconSize(QSize(26, 26))
            btn.setFixedSize(32, 32)  # 稍微减小按钮尺寸
            btn.setCheckable(True)
            
            # 修改按钮样式表，减小边框宽度和内边距
            btn.setStyleSheet('''
                QPushButton {
                    border: none;
                    padding: 0px;
                    border-radius: 3px;
                    background-color: transparent;
                    min-width: 30px;
                    min-height: 30px;
                }
                QPushButton:checked {
                    background-color: rgba(255, 255, 255, 0.1);
                    margin-top: -1px;
                }
            ''')
            
            # 存储原始和灰色图标
            btn.original_icon = QIcon(transparent_pixmap)  # 使用半透明版本
            btn.gray_icon = QIcon(gray_transparent_pixmap)  # 使用灰色半透明版本
            
            # 连接点击事件
            btn.toggled.connect(lambda checked, b=btn: self.on_mutator_toggled(b, checked))
            
            icon_layout.addWidget(btn)
            self.mutator_buttons.append(btn)
        
        # 调整布局，优化间距和边距
        icon_layout.setSpacing(8)  # 增加图标间距
        icon_layout.setContentsMargins(4, 5, 8, 5)  # 减小左侧边距
        icon_layout.addStretch()
        icon_layout.addStretch()
        
        # 调整主容器和图标区域的位置
        table_bottom = self.table_area.geometry().bottom()
        self.icon_area.setGeometry(0, table_bottom + 5, self.main_container.width(), 50)
        
        # 添加替换指挥官按钮
        self.replace_commander_btn = QPushButton(self.get_text('replace_commander'), self.main_container)
        self.replace_commander_btn.clicked.connect(self.on_replace_commander)
        self.replace_commander_btn.setStyleSheet('''
            QPushButton {
                color: black;
                background-color: rgba(236, 236, 236, 200);
                border: none;
                border-radius: 3px;
                padding: 5px;
                font-size: 12pt;
            }
            QPushButton:hover {
                background-color: rgba(43, 43, 43, 200);
            }
        ''')
        if config.REPLACE_COMMANDER_FLAG:
            self.replace_commander_btn.setFixedSize(150, 30)
        else:
            self.replace_commander_btn.setFixedSize(0, 0)
        commander_btn_x = (self.main_container.width() - self.replace_commander_btn.width()) // 2
        self.replace_commander_btn.move(commander_btn_x, self.icon_area.geometry().bottom() + 5)
        self.replace_commander_btn.hide()  # 初始状态为隐藏
        
        # 更新主容器高度
        self.main_container.setFixedHeight(self.replace_commander_btn.geometry().bottom() + 5)
        self.setFixedHeight(self.main_container.height())  # 更新窗口高度
        
        print(f"图标区域位置: {self.icon_area.geometry()}")
        print(f"主容器高度: {self.main_container.height()}")
        
        # 创建指挥官选择器实例，传入当前窗口的几何信息
        self.commander_selector = CommanderSelector(self)
        
        # 显示窗口并强制置顶
        self.show()
        if sys.platform == 'win32':
            import win32gui
            import win32con
            hwnd = int(self.winId())
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, 
                                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)
    
    def update_game_time(self):
        """更新游戏时间显示"""
        self.logger.debug('开始更新游戏时间')
        start_time = time.time()
        
        try:
            # 从全局变量获取游戏时间
            from mainfunctions import most_recent_playerdata
            if most_recent_playerdata and isinstance(most_recent_playerdata, dict):
                game_time = most_recent_playerdata.get('time', 0)
                self.logger.debug(f'从全局变量获取的原始时间数据: {game_time}')
                
                # 格式化时间显示
                hours = int(float(game_time) // 3600)
                minutes = int((float(game_time) % 3600) // 60)
                seconds = int(float(game_time) % 60)
                
                # 修改格式化逻辑：有小时时显示HH:MM:SS，没有小时时只显示MM:SS
                if hours > 0:
                    formatted_time = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                else:
                    formatted_time = f"{minutes:02d}:{seconds:02d}"
                    
                self.current_time = formatted_time
                self.time_label.setText(formatted_time)
                
                # 更新地图信息（如果有）
                map_name = most_recent_playerdata.get('map')
                if map_name:
                    self.logger.debug(f'地图信息更新: {map_name}')
                
                self.logger.debug(f'游戏时间更新: {formatted_time} (格式化后), 原始数据: {game_time}')
                
                # 根据当前时间调整表格滚动位置和行颜色
                try:
                    # 将当前时间转换为分钟数，以便于比较
                    current_minutes = hours * 60 + minutes
                    current_seconds = current_minutes * 60 + seconds
                    
                    # 遍历表格找到最接近的时间点并更新颜色
                    closest_row = 0
                    min_diff = float('inf')
                    
                    # 找出下一个即将触发的事件
                    next_event_row = -1
                    next_event_seconds = float('inf')
                    
                    # 第一次遍历：找出下一个即将触发的事件
                    for row in range(self.table_area.rowCount()):
                        time_item = self.table_area.item(row, 0)
                        if time_item and time_item.text():
                            try:
                                # 解析表格中的时间（格式可能是MM:SS或HH:MM:SS）
                                time_parts = time_item.text().split(':')
                                row_seconds = 0
                                if len(time_parts) == 2:  # MM:SS格式
                                    row_seconds = int(time_parts[0]) * 60 + int(time_parts[1])
                                elif len(time_parts) == 3:  # HH:MM:SS格式
                                    row_seconds = int(time_parts[0]) * 3600 + int(time_parts[1]) * 60 + int(time_parts[2])
                                
                                # 找出下一个即将触发的事件（未来的最近事件）
                                if row_seconds > current_seconds and row_seconds < next_event_seconds:
                                    next_event_seconds = row_seconds
                                    next_event_row = row
                                    
                                # 计算时间差（秒）
                                diff = abs(current_seconds - row_seconds)
                                if diff < min_diff:
                                    min_diff = diff
                                    closest_row = row
                            except ValueError:
                                continue
                    
                    # 第二次遍历：设置颜色
                    for row in range(self.table_area.rowCount()):
                        time_item = self.table_area.item(row, 0)
                        event_item = self.table_area.item(row, 1)
                        army_item = self.table_area.item(row, 2)
                        if time_item and time_item.text():
                            try:
                                # 解析表格中的时间（格式可能是MM:SS或HH:MM:SS）
                                time_parts = time_item.text().split(':')
                                row_seconds = 0
                                if len(time_parts) == 2:  # MM:SS格式
                                    row_seconds = int(time_parts[0]) * 60 + int(time_parts[1])
                                elif len(time_parts) == 3:  # HH:MM:SS格式
                                    row_seconds = int(time_parts[0]) * 3600 + int(time_parts[1]) * 60 + int(time_parts[2])
                                
                                # 根据时间差设置颜色
                                if row_seconds < current_seconds:  # 已过去的时间
                                    time_item.setForeground(QBrush(QColor(128, 128, 128, 255)))
                                    time_item.setBackground(QBrush(QColor(0, 0, 0, 0)))
                                    if event_item:
                                        event_item.setForeground(QBrush(QColor(128, 128, 128, 255)))
                                        event_item.setBackground(QBrush(QColor(0, 0, 0, 0)))
                                elif row == next_event_row:  # 下一个即将触发的事件
                                    time_item.setForeground(QBrush(QColor(config.TABLE_NEXT_FONT_COLOR[0], config.TABLE_NEXT_FONT_COLOR[1], config.TABLE_NEXT_FONT_COLOR[2])))  # 使用绿色高亮
                                    time_item.setBackground(QBrush(QColor(config.TABLE_NEXT_FONT_BG_COLOR[0], config.TABLE_NEXT_FONT_BG_COLOR[1], config.TABLE_NEXT_FONT_BG_COLOR[2], config.TABLE_NEXT_FONT_BG_COLOR[3])))
                                    if event_item:
                                        event_item.setForeground(QBrush(QColor(config.TABLE_NEXT_FONT_COLOR[0], config.TABLE_NEXT_FONT_COLOR[1], config.TABLE_NEXT_FONT_COLOR[2])))  # 使用绿色高亮
                                        event_item.setBackground(QBrush(QColor(config.TABLE_NEXT_FONT_BG_COLOR[0], config.TABLE_NEXT_FONT_BG_COLOR[1], config.TABLE_NEXT_FONT_BG_COLOR[2], config.TABLE_NEXT_FONT_BG_COLOR[3])))
                                
                                        # 显示完整的时间和事件信息作为Toast提醒
                                        # 检查是否需要显示Toast提示
                                        # 计算距离事件的时间差（秒）
                                        time_diff = row_seconds - current_seconds
                                        # 只在事件即将发生前的特定时间段内（30秒内）才显示Toast提示，并避免重复触发
                                        if time_diff > 0 and time_diff <= config.TIME_ALERT_SECONDS and not self.toast_manager.toast_label.isVisible():
                                            toast_message = f"{time_item.text()}\t{event_item.text()}" + (f"\t{army_item.text()}" if army_item else "")
                                            self.show_toast(toast_message, config.TOAST_DURATION)
                                elif abs(row_seconds - current_seconds) <= 30:  # 即将到来的时间（30秒内）
                                    time_item.setForeground(QBrush(QColor(0, 191, 255)))
                                    time_item.setBackground(QBrush(QColor(0, 191, 255, 30)))
                                    # 确保事件项存在且设置正确的颜色
                                    if event_item:
                                        event_item.setForeground(QBrush(QColor(0, 191, 255)))
                                        event_item.setBackground(QBrush(QColor(0, 191, 255, 30)))
                                        # 强制更新表格项
                                        self.table_area.update()
                                        # 强制更新表格视图
                                        self.table_area.viewport().update()
                                        # 刷新特定单元格
                                        model_index = self.table_area.model().index(row, 1)
                                        self.table_area.dataChanged(model_index, model_index)
                                else:  # 未来的时间
                                    time_item.setForeground(QBrush(QColor(255, 255, 255)))
                                    time_item.setBackground(QBrush(QColor(0, 0, 0, 0)))
                                    if event_item:
                                        event_item.setForeground(QBrush(QColor(255, 255, 255)))
                                        event_item.setBackground(QBrush(QColor(0, 0, 0, 0)))
                            except ValueError:
                                continue
                    
                    # 计算滚动位置，使最接近的时间点位于可见区域中间
                    if self.table_area.rowHeight(0) == 0:
                        return  # 或者返回你需要的其他值
                    else:
                        visible_rows = self.table_area.height() // self.table_area.rowHeight(0)
                    scroll_position = max(0, closest_row - (visible_rows // 2))
                    
                    # 设置滚动位置
                    self.table_area.verticalScrollBar().setValue(scroll_position)
                except Exception as e:
                    self.logger.error(f'调整表格滚动位置和颜色失败: {str(e)}\n{traceback.format_exc()}')

            else:
                self.logger.debug('未获取到有效的游戏时间数据')
                self.time_label.setText("00:00")
                
        except Exception as e:
            self.logger.error(f'获取游戏时间失败: {str(e)}\n{traceback.format_exc()}')
            # 如果获取失败，显示默认时间
            self.time_label.setText("00:00")
        
        self.logger.debug(f'本次更新总耗时：{time.time() - start_time:.2f}秒\n')
    

    def mousePressEvent(self, event):
        """鼠标按下事件，用于实现窗口拖动"""
        # 检查窗口是否处于可点击状态（非锁定状态）
        is_clickable = not self.testAttribute(Qt.WA_TransparentForMouseEvents)
        
        if is_clickable:  # 窗口可点击时
            if event.button() == Qt.LeftButton:
                pos = event.pos()
                map_area = QRect(10, 5, 30, 30)
                if map_area.contains(pos):
                    self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
                    self.is_dragging = True
                    event.accept()
                else:
                    # 检查是否点击了突变按钮
                    for btn in self.mutator_buttons:
                        if btn.geometry().contains(event.pos() - self.icon_area.pos()) and btn.property("clickable"):
                            event.accept()
                            return
                    event.ignore()
        else:
            if self.ctrl_pressed and event.button() == Qt.LeftButton:
                pos = event.pos()
                map_area = QRect(10, 5, 30, 30)
                if map_area.contains(pos):
                    self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
                    self.is_dragging = True
                    event.accept()
                else:
                    event.ignore()
            else:
                event.ignore()

    def mouseMoveEvent(self, event):
        """鼠标移动事件，用于实现窗口拖动"""
        if event.buttons() & Qt.LeftButton and hasattr(self, 'is_dragging') and self.is_dragging:
            self.move(event.globalPos() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        """鼠标释放事件"""
        if event.button() == Qt.LeftButton:
            self.is_dragging = False
            event.accept()

    def on_control_state_changed(self, unlocked):
        """处理控制窗口状态改变事件"""
        self.logger.info(f'控制窗口状态改变: unlocked={unlocked}')
        
        # 根据解锁状态显示或隐藏替换指挥官按钮
        if hasattr(self, 'replace_commander_btn'):
            if unlocked and config.REPLACE_COMMANDER_FLAG:
                self.replace_commander_btn.show()
            else:
                self.replace_commander_btn.hide()
                
        # 同步更新指挥官选择器窗口的显示状态
        if hasattr(self, 'commander_selector'):
            self.commander_selector.set_visibility(unlocked)
        
        # 在Windows平台上，直接使用Windows API设置窗口样式
        if sys.platform == 'win32':
            try:
                import ctypes
                from ctypes import wintypes
                
                # 定义Windows API常量
                GWL_EXSTYLE = -20
                WS_EX_TRANSPARENT = 0x00000020
                WS_EX_LAYERED = 0x00080000
                
                # 获取窗口句柄
                hwnd = int(self.winId())
                
                # 获取当前窗口样式
                ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                self.logger.info(f'当前窗口样式: {ex_style}')
                
                if not unlocked:  # 锁定状态（不可点击）
                    # 添加透明样式
                    new_ex_style = ex_style | WS_EX_TRANSPARENT | WS_EX_LAYERED
                    self.logger.info(f'设置窗口为不可点击状态，样式从 {ex_style} 更改为 {new_ex_style}')
                else:  # 解锁状态（可点击）
                    # 移除透明样式，但保留WS_EX_LAYERED
                    new_ex_style = (ex_style & ~WS_EX_TRANSPARENT) | WS_EX_LAYERED
                    self.logger.info(f'设置窗口为可点击状态，样式从 {ex_style} 更改为 {new_ex_style}')
                
                # 设置新样式
                result = ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_ex_style)
                if result == 0:
                    error = ctypes.windll.kernel32.GetLastError()
                    self.logger.error(f'SetWindowLongW失败，错误码: {error}')
                    
                # 强制窗口重绘
                ctypes.windll.user32.SetWindowPos(
                    hwnd, 0, 0, 0, 0, 0, 
                    0x0001 | 0x0002 | 0x0004 | 0x0020  # SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_FRAMECHANGED
                )
                
            except Exception as e:
                self.logger.error(f'设置Windows平台点击穿透失败: {str(e)}')
                self.logger.error(traceback.format_exc())
        else:
            # 非Windows平台使用Qt的方法
            self.hide()  # 先隐藏窗口
            
            if not unlocked:  # 锁定状态（不可点击）
                self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
                self.logger.info('已设置窗口为不可点击状态')
            else:  # 解锁状态（可点击）
                self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
                self.logger.info('已设置窗口为可点击状态')
                
            self.show()  # 重新显示窗口
        
        # 更新突变按钮的状态
        for btn in self.mutator_buttons:
            # 使用 setAttribute 来控制事件穿透
            btn.setAttribute(Qt.WA_TransparentForMouseEvents, not unlocked)
            
            # 不改变图标状态，保持当前显示
            if btn.isChecked():
                btn.setIcon(btn.original_icon)
            else:
                btn.setIcon(btn.gray_icon)
                
    def on_replace_commander(self):
        """处理替换指挥官按钮的点击事件"""
        if hasattr(self, 'commander_selector'):
            # 切换指挥官选择器窗口的打开/关闭状态
            self.commander_selector.toggle_window()
    
    def closeEvent(self, event):
        """关闭事件"""
        event.ignore()
        self.hide()
        
    def handle_progress_update(self, data):
        """处理进度更新信号"""
        if data[0] == 'update_map':
            # 在下拉框中查找并选择地图
            map_name = data[1]
            self.logger.info(f'收到地图更新信号: {map_name}')
            
            # 如果是新游戏开始，强制更新地图
            index = self.combo_box.findText(map_name)
            if index >= 0:
                self.logger.info(f'找到地图 {map_name}，更新下拉框选择')
                # 暂时禁用手动选择标志
                self.manual_map_selection = False
                self.combo_box.setCurrentIndex(index)
                # 手动调用地图选择事件处理函数，确保加载地图文件
                self.on_map_selected(map_name)
            else:
                self.logger.warning(f'未在下拉框中找到地图: {map_name}')

    def on_version_selected(self):
        """处理地图版本按钮选择事件"""
        sender = self.sender()
        if not sender or not isinstance(sender, QPushButton):
            return
            
        # 取消其他按钮的选中状态
        for btn in self.version_buttons:
            if btn != sender:
                btn.setChecked(False)
        
        # 获取当前地图名称的前缀
        current_map = self.combo_box.currentText()
        if not current_map:
            return
            
        # 根据按钮文本和地图前缀构造新的地图名称
        prefix = current_map.rsplit('-', 1)[0]
        new_map = f"{prefix}-{sender.text()}"
        
        # 在下拉框中查找并选择新地图
        index = self.combo_box.findText(new_map)
        if index >= 0:
            self.combo_box.setCurrentIndex(index)
    
    

    

    
    def on_text_double_click(self, event):
        """处理表格区域双击事件"""
        if event.button() == Qt.LeftButton:
            selected_items = self.table_area.selectedItems()
            if selected_items:
                # 获取选中行的完整内容
                row = selected_items[0].row()
                time_item = self.table_area.item(row, 0)
                event_item = self.table_area.item(row, 1)
                army_item = self.table_area.item(row, 2)
                if time_item and event_item:
                    time_text = time_item.text().strip()
                    event_text = event_item.text().strip()
                    army_text = army_item.text().strip() if army_item else ""
                    selected_text = f"{time_text}\t{event_text}\t{army_text}" if time_text and army_text.strip() else (f"{time_text}\t{event_text}" if time_text else event_text)
                    self.show_toast(selected_text, config.TOAST_DURATION, force_show=True)  # 设置5000毫秒（5秒）后自动消失
            event.accept()
            
    def init_global_hotkeys(self):
        """初始化全局快捷键"""
        try:
            # 解析快捷键配置
            map_shortcut = config.MAP_SHORTCUT.replace(' ', '').lower()
            lock_shortcut = config.LOCK_SHORTCUT.replace(' ', '').lower()
            screenshot_shortcut = config.SCREENSHOT_SHORTCUT.replace(' ', '').lower()
            artifact_shortcut = config.SHOW_ARTIFACT_SHORTCUT.replace(' ', '').lower()
            
            # 注册全局快捷键
            keyboard.add_hotkey(map_shortcut, self.handle_map_switch_hotkey)
            keyboard.add_hotkey(lock_shortcut, self.handle_lock_shortcut)
            keyboard.add_hotkey(screenshot_shortcut, self.handle_screenshot_hotkey)
        
            self.toggle_artifact_signal.connect(self.handle_artifact_shortcut)
            keyboard.add_hotkey(artifact_shortcut, self.toggle_artifact_signal.emit)
            self.logger.info(f'成功注册全局快捷键: {config.MAP_SHORTCUT}, {config.LOCK_SHORTCUT}, {config.SCREENSHOT_SHORTCUT}')
            
        except Exception as e:
            self.logger.error(f'注册全局快捷键失败: {str(e)}')
            self.logger.error(traceback.format_exc())
            

    def on_language_changed(self, lang):
        """处理语言切换事件"""
        # 更新config.py中的语言配置
        if getattr(sys, 'frozen', False):  # 是否为打包的 exe
            config_file = os.path.join(os.path.dirname(sys.executable), 'config.py')  # exe 所在目录
        else:
            config_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src','config.py') # 源码所在目录

        self.logger.info(f"load config: {config_file}")

        with open(config_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 使用正则表达式替换current_language的值
        new_content = re.sub(r"current_language\s*=\s*'[^']*'", f"current_language = '{lang}'", content)
        
        self.logger.info(f"update config: {config_file}")
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        # 更新config模块中的值
        config.current_language = lang
        
        # 更新commander_selector的语言设置
        if hasattr(self, 'commander_selector'):
            self.commander_selector.set_language(lang)
        
        # 重新加载地图列表
        resources_dir = get_resources_dir('resources', 'maps', lang)
        if not resources_dir:
            self.files = []
        else:
            self.files = list_files(resources_dir)
        
        # 清空并重新添加地图列表
        self.combo_box.clear()
        self.combo_box.addItems(self.files)
        
        # 如果有文件，自动加载第一个
        if self.files:
            self.on_map_selected(self.files[0])
        
        # 更新UI文本
        self.map_label.setText(self.get_text('map_label'))
        self.replace_commander_btn.setText(self.get_text('replace_commander'))
        
        # 重新初始化系统托盘菜单以更新语言选择标记
        self.init_tray()
    

    
    
    def closeEvent(self, event):
        """窗口关闭事件处理"""
        try:
            # 清理全局快捷键
            keyboard.unhook_all()
            self.logger.info('已清理所有全局快捷键')
        except Exception as e:
            self.logger.error(f'清理全局快捷键失败: {str(e)}')
            self.logger.error(traceback.format_exc())
        
        # 调用父类的closeEvent
        super().closeEvent(event)

    def showEvent(self, event):
        """窗口显示事件，确保窗口始终保持在最上层"""
        super().showEvent(event)
        if sys.platform == 'win32':
            import win32gui
            import win32con
            hwnd = int(self.winId())
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, 
                                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)

    def on_mutator_toggled(self, button, checked):
        """处理突变按钮状态改变"""
        if checked:
            # 切换到原始图标并添加阴影效果
            button.setIcon(button.original_icon)
            shadow = QGraphicsDropShadowEffect()
            shadow.setBlurRadius(10)
            shadow.setXOffset(3)
            shadow.setYOffset(3)
            shadow.setColor(QColor(0, 0, 0, 160))
            button.setGraphicsEffect(shadow)
            
            # 根据按钮索引加载对应的突变因子配置
            if button in self.mutator_buttons:
                button_index = self.mutator_buttons.index(button)
                mutator_types = ['deployment', 'propagator', 'voidrifts', 'killbots', 'bombbots']
                if button_index < len(mutator_types):
                    mutator_type = mutator_types[button_index]
                    time_points = self.load_mutator_config(mutator_type)
                    setattr(self, f'{mutator_type}_time_points', time_points)
                    
                    # 启动检查定时器（如果还没有启动）
                    if not hasattr(self, 'mutator_timer'):
                        self.mutator_timer = QTimer()
                        self.mutator_timer.timeout.connect(self.check_mutator_alerts)
                        self.mutator_timer.start(1000)  # 每秒检查一次
        else:
            # 切换回灰色图标并移除阴影效果
            button.setIcon(button.gray_icon)
            button.setGraphicsEffect(None)
            
            # 清除对应突变因子的时间点和提醒记录
            if button in self.mutator_buttons:
                button_index = self.mutator_buttons.index(button)
                mutator_types = ['deployment', 'propagator', 'voidrifts']
                
                if button_index < len(mutator_types):
                    mutator_type = mutator_types[button_index]
                    # 清除时间点
                    setattr(self, f'{mutator_type}_time_points', [])
                    # 清除已提醒记录
                    if hasattr(self, f'alerted_{mutator_type}_time_points'):
                        delattr(self, f'alerted_{mutator_type}_time_points')
                
                # # 如果所有按钮都未选中，停止定时器
                # if not any(btn.isChecked() for btn in self.mutator_buttons):
                #     if hasattr(self, 'mutator_timer'):
                #         self.mutator_timer.stop()
