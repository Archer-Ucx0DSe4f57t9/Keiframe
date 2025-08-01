from PyQt5.QtWidgets import (
    QWidget, QLabel, QHBoxLayout, QVBoxLayout, QPushButton,
    QTableWidget, QComboBox, QLineEdit, QTableWidgetItem,QHeaderView
)
from PyQt5.QtGui import QFont, QColor, QPixmap, QIcon, QPainter
from PyQt5.QtCore import Qt, QTimer, QSize
import os
import config
from fileutil import get_resources_dir, list_files

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
            self.files = []
        else:
            self.files = list_files(resources_dir)
        self.combo_box.setGeometry(60, 5, 100, 30)  # 右移一点
        #self.combo_box.setGeometry(40, 5, 117, 30)
        self.combo_box.setFont(QFont('Arial', 9))
        self.combo_box.addItems(self.files)
        
        # 连接下拉框选择变化事件
        self.combo_box.currentTextChanged.connect(self.on_map_selected)
        
        # 如果有文件，自动加载第一个
        if self.files:
            self.on_map_selected(self.files[0])
            
        ####################
        #用户输入搜索
        # 清空搜索框的定时器
        self.clear_search_timer = QTimer()
        self.clear_search_timer.setSingleShot(True)