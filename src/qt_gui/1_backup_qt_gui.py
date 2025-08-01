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

    def handle_screenshot_hotkey(self):
        """处理截图快捷键"""
        if not config.DEBUG_SHOW_ENEMY_INFO_SQUARE:
            return
        
        try:
            # 使用已保存的矩形区域进行截图
            successful_captures = 0
            
            for rect in self.rect_screenshots:
                try:
                    # 调用capture_screen_rect进行截图并保存
                    save_path = image_util.capture_screen_rect(rect)
                    if save_path:
                        self.logger.info(f'成功保存截图到: {save_path}')
                        successful_captures += 1
                    else:
                        self.logger.warning(f'截图保存失败: {rect.x()}, {rect.y()}, {rect.width()}, {rect.height()}')
                except Exception as capture_error:
                    self.logger.error(f'区域截图失败: {str(capture_error)}')
                    self.logger.error(traceback.format_exc())
            
            if successful_captures == len(self.rect_screenshots):
                self.logger.info('所有区域截图完成')
            else:
                self.logger.warning(f'部分区域截图失败: 成功{successful_captures}/{len(self.rect_screenshots)}')
        except Exception as e:
            self.logger.error(f'截图处理失败: {str(e)}')
            self.logger.error(traceback.format_exc())

    def init_ui(self):
        #初始化变量
        self.suppress_auto_selection = False
        """初始化用户界面"""
        self.setWindowTitle('SC2 Timer')
        self.setGeometry(config.MAIN_WINDOW_X, config.MAIN_WINDOW_Y, config.MAIN_WINDOW_WIDTH, 30)  # 调整初始窗口位置
        
        # 设置窗口样式 - 不设置点击穿透，这将由on_control_state_changed方法控制
        self.setWindowFlags(
            Qt.FramelessWindowHint |  # 无边框
            Qt.WindowStaysOnTopHint |  # 置顶
            Qt.Tool |  # 不在任务栏显示
            Qt.MSWindowsFixedSizeDialogHint  # 禁用窗口自动调整
        )
        self.setAttribute(Qt.WA_TranslucentBackground)  # 透明背景
        self.setAttribute(Qt.WA_NoSystemBackground)  # 禁用系统背景
        
        # 添加键盘事件监听变量
        self.ctrl_pressed = False
        
        # 创建主容器控件
        self.main_container = QWidget(self)
        self.main_container.setGeometry(0, 0, config.MAIN_WINDOW_WIDTH, 50)  # 调整主容器初始高度
        from config import MAIN_WINDOW_BG_COLOR
        self.main_container.setStyleSheet(f'background-color: {MAIN_WINDOW_BG_COLOR}')
        
        # 创建时间显示标签
        self.time_label = QLabel(self.current_time, self.main_container)
        self.time_label.setFont(QFont('Consolas', 11))
        self.time_label.setStyleSheet('color: rgb(0, 255, 128); background-color: transparent')
        self.time_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.time_label.setGeometry(10, 40, 100, 20)  # 调整宽度为100px
        self.time_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)  # 添加鼠标事件穿透
        
        # 创建地图版本选择按钮组
        self.map_version_group = QWidget(self.main_container)
        self.map_version_group.setGeometry(60, 40, 100, 20)  # 增加总宽度到100px
        self.map_version_group.setStyleSheet('background-color: transparent')
        version_layout = QHBoxLayout(self.map_version_group)
        version_layout.setContentsMargins(0, 0, 0, 0)
        version_layout.setSpacing(4)  # 增加按钮间距
        
        self.version_buttons = []
        for version in ['A', 'B']:  # 默认使用A/B，后续会根据地图类型动态更改
            btn = QPushButton(version)
            btn.setFont(QFont('Arial', 11))  # 增加字体大小
            btn.setFixedSize(48, 20)  # 增加按钮宽度到48px
            btn.setCheckable(True)
            btn.setStyleSheet('''
                QPushButton {
                    color: rgb(200, 200, 200);
                    background-color: rgba(43, 43, 43, 200);
                    border: none;
                    border-radius: 3px;
                    padding: 0px;
                }
                QPushButton:checked {
                    color: rgb(0, 191, 255);
                    background-color: rgba(0, 191, 255, 30);
                }
                QPushButton:hover {
                    background-color: rgba(0, 191, 255, 20);
                }
            ''')
            version_layout.addWidget(btn)
            self.version_buttons.append(btn)
            btn.clicked.connect(self.on_version_selected)
        
        # 默认隐藏按钮组
        self.map_version_group.hide()
        
        # 创建表格显示区
        from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
        self.table_area = QTableWidget(self.main_container)
        self.table_area.setGeometry(0, 65, config.MAIN_WINDOW_WIDTH, config.TABLE_HEIGHT)  # 保持表格区域位置不变
        self.table_area.setColumnCount(3)
        self.table_area.horizontalHeader().setVisible(False)  # 隐藏水平表头
        self.table_area.setColumnWidth(0, 50)  # 设置时间列的固定宽度
        self.table_area.setColumnWidth(2, 5)  # 设置时间列的固定宽度
        self.table_area.setColumnWidth(1, config.MAIN_WINDOW_WIDTH - 55)  # 设置文字列的固定宽度
        self.table_area.verticalHeader().setVisible(False)  # 隐藏垂直表头
        self.table_area.setEditTriggers(QTableWidget.NoEditTriggers)  # 设置表格只读
        self.table_area.setSelectionBehavior(QTableWidget.SelectRows)  # 设置选择整行
        self.table_area.setShowGrid(False)  # 隐藏网格线
        self.table_area.setStyleSheet(f'''
            QTableWidget {{ 
                border: none; 
                background-color: transparent; 
                padding-left: 5px; 
                font-size: {config.TABLE_FONT_SIZE}px;
                font-family: Arial;
            }}
            QTableWidget::horizontalHeader {{ 
                border: none;
                background-color: transparent;
                padding: 0px;
                padding-left: 5px;
                text-align: left;
            }}
            QTableWidget::verticalHeader {{
                border: none;
                background-color: transparent;
                padding: 0px;
                padding-left: 5px;
                text-align: left;
            }}
            QTableWidget::item {{ 
                padding: 0px;
                padding-left: 5px;
                text-align: left;
                /* 移除对颜色的全局设置，允许单元格通过setForeground方法设置颜色 */
            }}
            QTableWidget::item:selected {{ 
                background-color: transparent; 
                color: rgb(255, 255, 255); 
                border: none; 
                text-align: left;
            }}
            QTableWidget::item:focus {{ 
                background-color: transparent; 
                color: rgb(255, 255, 255); 
                border: none; 
                text-align: left;
            }}''')

        # 设置表格的滚动条策略
        self.table_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
 
        # self.setFixedSize(config.MAIN_WINDOW_WIDTH, 250)  # 固定窗口大小为250
 
        
        # 调整主窗口大小以适应新添加的控件
        self.main_container.setGeometry(0, 0, config.MAIN_WINDOW_WIDTH, 300)  # 调整容器高度
        
        # 创建搜索框
        self.search_box = QLineEdit(self.main_container)
        self.search_box.setPlaceholderText("搜索…")
        self.search_box.setFixedSize(50, 30)
        self.search_box.setFont(QFont('Arial', 9))
        self.search_box.setStyleSheet('''
            QLineEdit {
                color: white;
                background-color: rgba(50, 50, 50, 200);
                border: 1px solid gray;
                border-radius: 5px;
                padding: 5px;
            }
        ''')
        self.search_box.move(10, 5)
    
        # 创建下拉框
        self.combo_box = QComboBox(self.main_container)
        self.combo_box.setGeometry(40, 5, 117, 30)
        self.combo_box.setFont(QFont('Arial', 9))  # 修改字体大小为9pt
        
        # 设置下拉列表视图
        view = self.combo_box.view()
        view.setStyleSheet("""
            background-color: rgba(43, 43, 43, 200);
            color: white;
        """)
        
        # 设置ComboBox样式
        self.combo_box.setStyleSheet('''
        QComboBox {
            color: rgb(0, 191, 255);
            background-color: rgba(43, 43, 43, 200);
            border: none;
            border-radius: 5px;
            padding: 5px;
            font-size: 9pt;
        }
        QComboBox::drop-down {
            border: none;
            width: 20px;
        }
        QComboBox::down-arrow {
            image: none;
            border-left: 6px solid transparent;
            border-right: 6px solid transparent;
            border-top: 6px solid white;
            width: 0;
            height: 0;
            margin-right: 5px;
        }
        /* 下拉滚动条样式 */
        QComboBox QScrollBar:vertical {
            width: 8px;
            background: rgba(200, 200, 200, 100);
        }
        QComboBox QScrollBar::handle:vertical {
            background: rgba(150, 150, 150, 150);
            border-radius: 4px;
        }''')
        
        # 加载resources文件夹下的文件
        resources_dir = get_resources_dir('resources', 'maps', config.current_language)
        if not resources_dir:
            files = []
        else:
            files = list_files(resources_dir)
        self.combo_box.setGeometry(60, 5, 100, 30)  # 右移一点
        #self.combo_box.setGeometry(40, 5, 117, 30)
        self.combo_box.setFont(QFont('Arial', 9))
        self.combo_box.addItems(files)
        
        # 连接下拉框选择变化事件
        self.combo_box.currentTextChanged.connect(self.on_map_selected)
        
        # 如果有文件，自动加载第一个
        if files:
            self.on_map_selected(files[0])
            
        ####################
        #用户输入搜索
        # 清空搜索框的定时器
        self.clear_search_timer = QTimer()
        self.clear_search_timer.setSingleShot(True)
        
        #更新搜索内容
        def update_combo_box(keyword, allow_auto_select=True):
            
            keyword = keyword.strip().lower()
            current_selected = self.combo_box.currentText()

            
            self.combo_box.blockSignals(True)  # 🚫 禁止选项变化触发 currentTextChanged
            self.combo_box.clear()

            filtered = [f for f in files if keyword in f.lower()]

            mapped_result = config.MAP_SEARCH_KEYWORDS.get(keyword)
            if mapped_result and mapped_result not in filtered and mapped_result in files:
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
    
    
    def init_tray(self):
        """初始化系统托盘"""
        from tray_manager import TrayManager
        self.tray_manager = TrayManager(self)

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
    
    def on_map_selected(self, map_name):
        """处理地图选择变化事件"""
        # 检查是否是由用户手动选择触发的
        if not self.manual_map_selection and self.sender() == self.combo_box:
            self.manual_map_selection = True
            self.logger.info('用户手动选择了地图')
        
        # 处理地图版本按钮组的显示
        if '-' in map_name:
            prefix = map_name.rsplit('-', 1)[0]
            suffix = map_name.rsplit('-', 1)[1]
            
            # 检查是否存在同前缀的其他地图
            has_variant = False
            variant_type = None
            for i in range(self.combo_box.count()):
                other_map = self.combo_box.itemText(i)
                if other_map != map_name and other_map.startswith(prefix + '-'):
                    has_variant = True
                    other_suffix = other_map.rsplit('-', 1)[1]
                    if other_suffix in ['左', '右'] and suffix in ['左', '右']:
                        variant_type = 'LR'
                    elif other_suffix in ['A', 'B'] and suffix in ['A', 'B']:
                        variant_type = 'AB'
                    break
            
            if has_variant and variant_type:
                # 更新按钮文本
                if variant_type == 'LR':
                    self.version_buttons[0].setText('左')
                    self.version_buttons[1].setText('右')
                else:  # AB
                    self.version_buttons[0].setText('A')
                    self.version_buttons[1].setText('B')
                
                # 设置当前选中的按钮
                current_suffix = suffix
                for btn in self.version_buttons:
                    btn.setChecked(btn.text() == current_suffix)
                
                # 显示按钮组
                self.map_version_group.show()
            else:
                # 隐藏按钮组
                self.map_version_group.hide()
        else:
            # 没有版本区分，隐藏按钮组
            self.map_version_group.hide()
        
        try:
            map_file_path = get_resources_dir('resources', 'maps', config.current_language, map_name)
            self.logger.info(f'尝试加载地图文件: {map_file_path}')
            
            # 读取地图文件内容
            if os.path.exists(map_file_path):
                with open(map_file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.logger.info(f'成功读取地图文件内容: {map_name}\n文件内容:\n{content}')
                
                # 清空表格现有内容
                self.table_area.setRowCount(0)
                self.logger.info('已清空表格现有内容')
                
                # 按行分割内容，过滤掉空行和只包含空白字符的行
                lines = [line.strip() for line in content.split('\n') if line and not line.isspace()]
                self.logger.info('解析到的有效行数: {}'.format(len(lines)))
                self.logger.info('解析后的行内容:\n{}'.format('\n'.join(lines)))
                
                # 设置表格行数
                self.table_area.setRowCount(len(lines))
                self.logger.info(f'设置表格行数为: {len(lines)}')
                
                # 填充表格内容
                for row, line in enumerate(lines):
                    # 按tab分隔符拆分时间和事件
                    parts = line.split('\t')
                    self.logger.info(f'处理第{row+1}行: {line}, 拆分结果: {parts}')
                    
                    if len(parts) >= 2:
                        # 创建时间单元格
                        time_item = QTableWidgetItem(parts[0])
                        time_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                        time_item.setForeground(QBrush(QColor(255, 255, 255)))  # 修改时间列文字颜色为白色
                        self.table_area.setItem(row, 0, time_item)
                        
                        # 创建事件单元格
                        event_item = QTableWidgetItem(parts[1])
                        event_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                        event_item.setForeground(QBrush(QColor(255, 255, 255)))  # 设置事件列文字颜色为白色
                        self.table_area.setItem(row, 1, event_item)
                        
                        if len(parts) == 3:
                            army_item = QTableWidgetItem(parts[2])
                            army_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                            army_item.setForeground(QBrush(QColor(255, 255, 255)))  # 设置事件
                            self.table_area.setItem(row, 2, army_item)
                            self.logger.info(f'已添加表格内容 - 行{row+1}: 时间={parts[0]}, 事件={parts[1]}, {parts[2]}')
                        else:
                            self.logger.info(f'已添加表格内容 - 行{row+1}: 时间={parts[0]}, 事件={parts[1]}')
                    else:
                        # 对于不符合格式的行，将整行内容显示在事件列
                        event_item = QTableWidgetItem(line)
                        event_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                        event_item.setForeground(QBrush(QColor(255, 255, 255)))  # 设置事件列文字颜色为白色
                        
                        self.table_area.setItem(row, 0, event_item)
                        self.table_area.setSpan(row, 0, 1, 3)  # 将当前行的两列合并为一列

                        self.logger.info(f'已添加不规范行内容到合并单元格 - 行{row+1}: {line}')
                
                # 验证表格内容
                row_count = self.table_area.rowCount()
                self.logger.info(f'最终表格行数: {row_count}')
                for row in range(row_count):
                    time_item = self.table_area.item(row, 0)
                    event_item = self.table_area.item(row, 1)
                    time_text = time_item.text() if time_item else 'None'
                    event_text = event_item.text() if event_item else 'None'
                    self.logger.info(f'验证第{row+1}行内容: 时间={time_text}, 事件={event_text}')
                
            else:
                self.logger.error(f'地图文件不存在: {map_name}')
                return
            
        except Exception as e:
            self.logger.error(f'加载地图文件时出错: {str(e)}\n{traceback.format_exc()}')

    def init_toast(self):
        """初始化Toast提示组件"""
        from toast_manager import ToastManager
        self.toast_manager = ToastManager(self)

    def show_toast(self, message, duration=None, force_show=False):
        """显示Toast提示"""
        self.toast_manager.show_map_toast(message, duration, force_show)

    def show_mutator_alert(self, message, mutator_type='deployment'):
        """显示突变因子提醒"""
        # 检查游戏状态，非游戏中状态不显示提示
        from mainfunctions import get_game_screen
        if get_game_screen() != 'in_game':
            self.logger.info('非游戏中状态，不显示alert Toast提示')
            return
            
        # 获取对应类型的标签
        alert_label = self.mutator_alert_labels.get(mutator_type)
        if not alert_label:
            return
            
        # 清除已有布局
        if alert_label.layout() is not None:
            QWidget().setLayout(alert_label.layout())
        
        # 在Windows平台上，使用Windows API设置窗口样式
        if sys.platform == 'win32':
            try:
                import ctypes
                from ctypes import wintypes
                
                # 定义Windows API常量
                GWL_EXSTYLE = -20
                WS_EX_TRANSPARENT = 0x00000020
                WS_EX_LAYERED = 0x00080000
                
                # 获取窗口句柄
                hwnd = int(alert_label.winId())
                
                # 获取当前窗口样式
                ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                
                # 添加透明样式
                new_ex_style = ex_style | WS_EX_TRANSPARENT | WS_EX_LAYERED
                
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
            alert_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        
        # 创建布局
        layout = QVBoxLayout(alert_label)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setAlignment(Qt.AlignLeft)
        
        # 创建一个QWidget作为提醒框
        alert_widget = QWidget()
        alert_widget.setAttribute(Qt.WA_TransparentForMouseEvents, True)  # 添加鼠标事件穿透
        alert_widget.setAttribute(Qt.WA_NoSystemBackground)  # 禁用系统背景
        alert_widget.setAttribute(Qt.WA_TranslucentBackground)  # 透明背景
        alert_layout = QHBoxLayout(alert_widget)
        alert_layout.setContentsMargins(0, 0, 0, 0)
        alert_layout.setAlignment(Qt.AlignLeft)
        
        # 根据突变因子类型设置图标和文本
        icon_name = f'{mutator_type}.png'
        icon_path = os.path.join('ico', 'mutator', icon_name)
        
        # 设置显示文本
        display_text = message
        
        if os.path.exists(icon_path):
            icon_label = QLabel()
            icon_label.setPixmap(QPixmap(icon_path).scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            icon_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)  # 添加鼠标事件穿透
            icon_label.setAttribute(Qt.WA_NoSystemBackground)  # 禁用系统背景
            icon_label.setAttribute(Qt.WA_TranslucentBackground)  # 透明背景
            alert_layout.addWidget(icon_label)
        
        # 创建文本标签
        text_label = QLabel(display_text)
        text_label.setStyleSheet(f'color: {config.MUTATOR_DEPLOYMENT_COLOR}; font-size: {config.TOAST_MUTATOR_FONT_SIZE}px')
        text_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)  # 添加鼠标事件穿透
        text_label.setAttribute(Qt.WA_NoSystemBackground)  # 禁用系统背景
        text_label.setAttribute(Qt.WA_TranslucentBackground)  # 透明背景
        alert_layout.addWidget(text_label)
        
        # 将提醒框添加到布局中
        alert_widget.setLayout(alert_layout)
        layout.addWidget(alert_widget)
        
        # 设置固定宽度，避免位置偏移
        alert_label.setFixedWidth(250)
        
        # 设置提醒窗口位置
        current_screen = self.get_current_screen()
        screen_geometry = current_screen.geometry()
        # 根据突变因子类型设置不同的水平位置
        position_map = {
            'voidrifts': config.MUTATOR_RIFT_POS,  
            'propagator': config.MUTATOR_PROPAGATOR_POS,  
            'deployment': config.MUTATOR_DEPLOYMENT_POS,
            'killbots': config.MUTATOR_KILLBOTS_POS,
            'bombbots': config.MUTATOR_BOMBBOTS_POS
        }
        # 计算相对于屏幕的绝对位置
        x = screen_geometry.x() + int(screen_geometry.width() * position_map.get(mutator_type, 0.5)) - 125  # 使用固定宽度的一半
        y = int(self.height() * config.MUTATOR_TOAST_POSITION)  # 使用专门的突变因子提示位置配置
        alert_label.move(x, y)
        
        # 显示提醒标签并启动定时器
        alert_label.show()
        self.mutator_alert_timers[mutator_type].start(config.TOAST_DURATION)

    def hide_mutator_alert(self, mutator_type):
        """隐藏突变因子提醒"""
        if mutator_type in self.mutator_alert_labels:
            self.mutator_alert_labels[mutator_type].hide()
            self.mutator_alert_timers[mutator_type].stop()

    def hide_toast(self):
        """隐藏Toast提示"""
        self.toast_manager.hide_toast()
    
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
            
    def get_text(self, key):
        """获取多语言文本"""
        try:
            config_path = get_resources_dir('resources', 'words.conf')
            with open(config_path, 'r', encoding='utf-8') as f:
                import json
                content = json.load(f)
                texts = content['qt_gui']
                if config.current_language in texts and key in texts[config.current_language]:
                    return texts[config.current_language][key]
                return key
        except Exception as e:
            self.logger.error(f"加载语言配置文件失败: {str(e)}")
            return key

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
            files = []
        else:
            files = list_files(resources_dir)
        
        # 清空并重新添加地图列表
        self.combo_box.clear()
        self.combo_box.addItems(files)
        
        # 如果有文件，自动加载第一个
        if files:
            self.on_map_selected(files[0])
        
        # 更新UI文本
        self.map_label.setText(self.get_text('map_label'))
        self.replace_commander_btn.setText(self.get_text('replace_commander'))
        
        # 重新初始化系统托盘菜单以更新语言选择标记
        self.init_tray()
    
    def handle_artifact_shortcut(self):
        # 如果窗口可见，则销毁图片
        if self.artifact_window.isVisible():
            self.artifact_window.destroy_images()
            self.artifact_window.hide()
        else:
            # 获取当前选择的地图名称并显示对应的神器图片
            try:
                current_map = self.combo_box.currentText()
                if current_map:
                    self.artifact_window.show_artifact(current_map, config.ARTIFACTS_IMG_OPACITY, config.ARTIFACTS_IMG_GRAY)
            except Exception as e:
                self.logger.error(f'draw artifacts layer failed: {str(e)}')
                self.logger.error(traceback.format_exc())

    def handle_lock_shortcut(self):
        """处理锁定快捷键"""
        self.logger.info(f'检测到锁定快捷键组合: {config.LOCK_SHORTCUT}')
        # 切换控制窗口的锁定状态
        self.control_window.is_locked = not self.control_window.is_locked
        self.control_window.update_icon()
        # 发送状态改变信号
        self.control_window.state_changed.emit(not self.control_window.is_locked)
    
    def handle_map_switch_hotkey(self):
        """处理地图切换快捷键"""
        self.logger.info(f'检测到地图切换快捷键组合: {config.MAP_SHORTCUT}')
        # 检查当前地图是否为A/B版本
        if self.map_version_group.isVisible():
            self.logger.info('当前地图支持A/B版本切换')
            # 获取当前选中的按钮
            current_btn = None
            for btn in self.version_buttons:
                if btn.isChecked():
                    current_btn = btn
                    break
            
            # 切换到另一个版本
            if current_btn:
                current_idx = self.version_buttons.index(current_btn)
                next_idx = (current_idx + 1) % len(self.version_buttons)
                self.logger.info(f'从版本 {current_btn.text()} 切换到版本 {self.version_buttons[next_idx].text()}')
                self.version_buttons[next_idx].click()
        else:
            self.logger.info('当前地图不支持A/B版本切换')
    
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

    def load_mutator_config(self, mutator_name):
        """加载突变因子配置文件"""
        try:
            # 获取配置文件路径
            config_path = os.path.join('resources', 'mutator', f'{mutator_name}.txt')
            self.logger.info(f'加载突变因子配置: {config_path}')
            
            if not os.path.exists(config_path):
                self.logger.error(f'突变因子配置文件不存在: {config_path}')
                return []
                
            # 读取配置文件
            with open(config_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # 解析时间点
            time_points = []
            for line in lines:
                if line.strip() and not line.isspace():
                    parts = line.strip().split('\t')
                    if len(parts) >= 1:
                        time_str = parts[0].strip()
                        # 将时间字符串转换为秒数
                        time_parts = time_str.split(':')
                        if len(time_parts) == 2:  # MM:SS
                            seconds = int(time_parts[0]) * 60 + int(time_parts[1])
                            time_points.append(seconds)
                            self.logger.debug(f"添加时间点: {time_str} -> {seconds}秒")
            
            self.logger.info(f'加载了 {len(time_points)} 个时间点: {time_points}')
            return sorted(time_points)  # 确保时间点是有序的
            
        except Exception as e:
            self.logger.error(f'加载突变因子配置失败: {str(e)}')
            self.logger.error(traceback.format_exc())
            return []

    def check_mutator_alerts(self):
        """检查突变因子提醒"""
        try:
            # 从全局变量获取当前游戏时间
            from mainfunctions import most_recent_playerdata
            if most_recent_playerdata and isinstance(most_recent_playerdata, dict):
                current_time = most_recent_playerdata.get('time', 0)
                if not current_time:
                    return
                    
                current_seconds = int(float(current_time))
                self.logger.debug(f"当前游戏时间: {current_seconds}秒")
                
                # 检查每个突变因子的时间点
                mutator_types = ['deployment', 'propagator', 'voidrifts', 'killbots', 'bombbots']
                for i, mutator_type in enumerate(mutator_types):
                    # 检查对应按钮是否被选中
                    if not self.mutator_buttons[i].isChecked():
                        continue
                        
                    time_points = []
                    time_points_attr = f'{mutator_type}_time_points'
                    if hasattr(self, time_points_attr):
                        time_points = getattr(self, time_points_attr)
                    
                    # 确保已提醒时间点集合存在
                    alerted_points_attr = f'alerted_{mutator_type}_time_points'
                    if not hasattr(self, alerted_points_attr):
                        setattr(self, alerted_points_attr, set())
                    
                    alerted_points = getattr(self, alerted_points_attr)
                    for time_point in time_points:
                        # 如果这个时间点已经提醒过，跳过
                        if time_point in alerted_points:
                            continue
                            
                        # 计算距离下一个时间点的秒数
                        time_diff = time_point - current_seconds
                        self.logger.debug(f"检查{mutator_type}时间点: {time_point}, 差值: {time_diff}")
                        
                        # 如果在提醒时间范围内且时间差大于0（未来时间点）
                        if time_diff > 0 and time_diff <= config.MUTATION_FACTOR_ALERT_SECONDS:
                            from debug_utils import format_time_to_mmss
                            # 读取配置文件中的第二列文本
                            config_path = os.path.join('resources', 'mutator', f'{mutator_type}.txt')
                            with open(config_path, 'r', encoding='utf-8') as f:
                                lines = f.readlines()
                            # 找到对应时间点的第二列文本
                            second_column_text = ''
                            for line in lines:
                                if line.strip() and not line.isspace():
                                    parts = line.strip().split('\t')
                                    if len(parts) >= 2:
                                        time_str = parts[0].strip()
                                        time_parts = time_str.split(':')
                                        if len(time_parts) == 2:
                                            line_seconds = int(time_parts[0]) * 60 + int(time_parts[1])
                                            if line_seconds == time_point:
                                                second_column_text = parts[1].strip()
                                                break
                            
                            self.logger.info(f"触发{mutator_type}突变因子提醒: {format_time_to_mmss(time_point)}处的事件")
                            self.show_mutator_alert(f"{time_diff} 秒后 {second_column_text}", mutator_type)
                            
                            # 记录已提醒的时间点
                            alerted_points.add(time_point)
                        
        except Exception as e:
            self.logger.error(f'检查突变因子提醒失败: {str(e)}')
            self.logger.error(traceback.format_exc())