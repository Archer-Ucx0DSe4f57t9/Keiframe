#ui_setup.py
import os
from PyQt5.QtWidgets import (
    QWidget, QLabel, QComboBox, QTableWidget,
    QPushButton, QHBoxLayout, QLineEdit, QApplication
)
from PyQt5.QtGui import QFont, QBrush, QColor
from PyQt5.QtCore import Qt, QTimer
import config
from fileutil import get_resources_dir, list_files
from mutator_manager import MutatorManager
from misc.commander_selector import CommanderSelector

# 辅助函数 1: 设置窗口样式
def setup_window_style(window):
    """设置主窗口的基本样式和属性"""
    window.setWindowTitle('SC2 Timer')
    window.setGeometry(config.MAIN_WINDOW_X, config.MAIN_WINDOW_Y, config.MAIN_WINDOW_WIDTH, 30)
    window.setWindowFlags(
        Qt.FramelessWindowHint |
        Qt.WindowStaysOnTopHint |
        Qt.Tool |
        Qt.MSWindowsFixedSizeDialogHint
    )
    window.setAttribute(Qt.WA_TranslucentBackground)
    window.setAttribute(Qt.WA_NoSystemBackground)
    window.ctrl_pressed = False # 从 init_ui 中移到这里

# 辅助函数 2: 创建主容器
def setup_main_container(window):
    """创建主容器"""
    window.main_container = QWidget(window)
    window.main_container.setGeometry(0, 0, config.MAIN_WINDOW_WIDTH, 50)
    window.main_container.setStyleSheet(f'background-color: {config.MAIN_WINDOW_BG_COLOR}')

# 辅助函数 3: 创建时间标签
def setup_time_labels(window):
    """创建时间显示标签和倒计时标签"""
     # 创建时间显示标签
    window.time_label = QLabel(window.current_time, window.main_container)
    window.time_label.setFont(QFont('Consolas', 11))
    window.time_label.setStyleSheet('color: rgb(0, 255, 128); background-color: transparent')
    window.time_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    window.time_label.setGeometry(10, 40, 100, 20)
    window.time_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    
    # 创建倒计时显示标签
    window.countdown_label = QLabel("", window.main_container)
    window.countdown_label.setFont(QFont('Consolas', 11))
    # 使用不同的颜色（例如黄色）以作区分
    window.countdown_label.setStyleSheet('color: rgb(255, 255, 0); background-color: transparent')
    window.countdown_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    # 放置在主计时器旁边
    window.countdown_label.setGeometry(80, 40, 100, 20)
    window.countdown_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
    window.countdown_label.hide()

# 辅助函数 4: 创建版本按钮组
def setup_map_version_group(window):
    """创建地图版本选择按钮组"""
    # ... (版本按钮组创建和样式代码) ... (保持与原文件一致)
    window.map_version_group = QWidget(window.main_container)
    window.map_version_group.setGeometry(60, 40, 100, 20)
    window.map_version_group.setStyleSheet('background-color: transparent')
    version_layout = QHBoxLayout(window.map_version_group)
    version_layout.setContentsMargins(0, 0, 0, 0)
    version_layout.setSpacing(4)

    window.version_buttons = []
    for version in ['A', 'B']:
        btn = QPushButton(version)
        btn.setFont(QFont('Arial', 11))
        btn.setFixedSize(48, 20)
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
        window.version_buttons.append(btn)
        # 注意：这里只连接到 window.on_version_selected，该方法需要保留在 TimerWindow 中。
        btn.clicked.connect(window.on_version_selected)

    window.map_version_group.hide()

# 辅助函数 5: 创建表格区域
def setup_table_area(window):
    """创建表格显示区"""
    # ... (表格区域创建和样式代码) ... (保持与原文件一致)
    from PyQt5.QtWidgets import QTableWidget
    window.table_area = QTableWidget(window.main_container)
    window.table_area.setGeometry(0, 65, config.MAIN_WINDOW_WIDTH, config.TABLE_HEIGHT)
    window.table_area.setColumnCount(3)
    window.table_area.horizontalHeader().setVisible(False)
    window.table_area.setColumnWidth(0, 50)
    window.table_area.setColumnWidth(2, 5)
    window.table_area.setColumnWidth(1, config.MAIN_WINDOW_WIDTH - 55)
    window.table_area.verticalHeader().setVisible(False)
    window.table_area.setEditTriggers(QTableWidget.NoEditTriggers)
    window.table_area.setSelectionBehavior(QTableWidget.SelectRows)
    window.table_area.setShowGrid(False)
    window.table_area.setStyleSheet(f'''
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

    window.table_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    window.table_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    
    # 调整主窗口大小以适应新添加的控件
    window.main_container.setGeometry(0, 0, config.MAIN_WINDOW_WIDTH, 300)  # 调整容器高度


# 辅助函数 6: 创建搜索框和下拉框
def setup_search_and_combo_box(window):
    """创建搜索框和地图下拉框"""
    # ... (搜索框和下拉框创建和样式代码) ... (保持与原文件一致)
    window.search_box = QLineEdit(window.main_container)
    window.search_box.setPlaceholderText("搜索…")
    window.search_box.setFixedSize(50, 30)
    window.search_box.setFont(QFont('Arial', 9))
    window.search_box.setStyleSheet('''
        QLineEdit {
            color: white;
            background-color: rgba(50, 50, 50, 200);
            border: 1px solid gray;
            border-radius: 5px;
            padding: 5px;
        }
    ''')
    window.search_box.move(10, 5)

    # 创建下拉框
    window.combo_box = QComboBox(window.main_container)
    window.combo_box.setGeometry(60, 5, 100, 30)# 右移一点
    window.combo_box.setFont(QFont('Arial', 9))

    # 设置下拉列表视图
    view = window.combo_box.view()
    view.setStyleSheet("""
        background-color: rgba(43, 43, 43, 200);
        color: white;
    """)

    # 设置ComboBox样式
    window.combo_box.setStyleSheet('''
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
    all_files = list_files(resources_dir) if resources_dir else []
    window.files = []
    for file_name in all_files:
    # 确保只处理 .csv 文件
        if file_name.lower().endswith('.csv'):
            # 移除 .csv 扩展名
            clean_name = file_name[:-4] 
            window.files.append(clean_name)

    window.combo_box.addItems(sorted(window.files))

    ####################
    # 用户输入搜索
    # 清空搜索框的定时器
    window.clear_search_timer = QTimer()
    window.clear_search_timer.setSingleShot(True)
    # 注意：搜索框的信号连接 (textChanged.connect) 需要保留在 TimerWindow 的 __init__ 中，以便访问内部函数。

# 辅助函数 7: 创建突变和指挥官替换区域
def setup_mutator_commander(window):
    """创建突变管理器和指挥官替换按钮"""
    # ... (突变和按钮创建和样式代码) ... (保持与原文件一致)
    window.mutator_manager = MutatorManager(window.main_container)
    window.mutator_manager.setStyleSheet("""
        QWidget {
            background-color: rgba(43, 43, 43, 96);
            border-radius: 5px;
        }
    """)
    
    
    
    table_bottom = window.table_area.geometry().bottom()
    window.mutator_manager.setGeometry(0, table_bottom + 5, window.main_container.width(), 50)

    window.replace_commander_btn = QPushButton(window.get_text('replace_commander'), window.main_container)
    window.replace_commander_btn.clicked.connect(window.on_replace_commander)
    window.replace_commander_btn.setStyleSheet('''
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
        window.replace_commander_btn.setFixedSize(150, 30)
    else:
        window.replace_commander_btn.setFixedSize(0, 0)
    commander_btn_x = (window.main_container.width() - window.replace_commander_btn.width()) // 2
    window.replace_commander_btn.move(commander_btn_x, window.mutator_manager.geometry().bottom() + 5)
    window.replace_commander_btn.hide()

    window.main_container.setFixedHeight(window.replace_commander_btn.geometry().bottom() + 5)
    window.setFixedHeight(window.main_container.height())

    window.commander_selector = CommanderSelector(window)

# 主 UI 初始化函数
def init_ui(window):
    """主 UI 初始化函数，调用所有子函数"""
    # 初始化标志
    window.suppress_auto_selection = False
    
    # 调用所有辅助函数
    setup_window_style(window)
    setup_main_container(window)
    setup_time_labels(window)
    setup_map_version_group(window)
    setup_table_area(window)
    setup_search_and_combo_box(window)
    setup_mutator_commander(window)
    
    # 强制显示窗口 (保持原样)
    window.show()
    # Windows 置顶处理 (保持在 qt_gui.py 中调用)