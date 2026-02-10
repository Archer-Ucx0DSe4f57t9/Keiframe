#ui_setup.py
import os
from PyQt5.QtWidgets import (
    QWidget, QLabel, QComboBox, QHBoxLayout,
    QPushButton, QHBoxLayout, QLineEdit, QApplication
)
from PyQt5.QtGui import QFont, QBrush, QColor
from PyQt5.QtCore import Qt, QTimer

from src import config
from src.utils.font_uitils import set_font_size
from src.mutaor_handlers.mutator_manager import MutatorManager
from src.db.map_daos import get_all_map_names
from pypinyin import lazy_pinyin, Style

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
    set_font_size(window.time_label, config.TABLE_FONT_SIZE) # 使用统一的字体大小设置函数
    window.time_label.setStyleSheet('color: rgb(0, 255, 128); background-color: transparent')
    window.time_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    window.time_label.setGeometry(10, 40, 100, 20)
    window.time_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    
    # 创建倒计时显示标签
    window.countdown_label = QLabel("", window.main_container)
    set_font_size(window.countdown_label, config.TABLE_FONT_SIZE) # 使用统一的字体大小设置函数
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
        set_font_size(btn, 11) # 使用统一的字体大小设置函数
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
    window.table_area.setGeometry(0, 65, config.MAIN_WINDOW_WIDTH-config.MUTATOR_WIDTH, config.TABLE_HEIGHT)
    window.table_area.setColumnCount(3)
    window.table_area.horizontalHeader().setVisible(False)
    window.table_area.setColumnWidth(0, 50)
    window.table_area.setColumnWidth(2, 5)
    window.table_area.setColumnWidth(1, config.MAIN_WINDOW_WIDTH-config.MUTATOR_WIDTH - 55)
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
    set_font_size(window.search_box, 9) # 使用统一的字体大小设置函数
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
    set_font_size(window.combo_box, 9) # 使用统一的字体大小设置函数

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

    window.map_list = sorted(get_all_map_names(window.maps_db),key=pinyin_key)
    window.combo_box.addItems(sorted(window.map_list, key=pinyin_key))

    ####################
    # 用户输入搜索
    # 清空搜索框的定时器
    window.clear_search_timer = QTimer()
    window.clear_search_timer.setSingleShot(True)
    # 注意：搜索框的信号连接 (textChanged.connect) 需要保留在 TimerWindow 的 __init__ 中，以便访问内部函数。

# 辅助函数 7: 创建突变和指挥官替换区域
def setup_mutator_ui(window):
    """创建突变管理器和指挥官替换按钮"""
    # ... (突变和按钮创建和样式代码) ... (保持与原文件一致)
    window.mutator_manager = MutatorManager(window.main_container,window.mutators_db)
    window.mutator_manager.setStyleSheet("""
        QWidget {
            background-color: rgba(43, 43, 43, 96);
            border-radius: 5px;
        }
    """)
    
    mutator_x = config.MAIN_WINDOW_WIDTH - config.MUTATOR_WIDTH 
    
    # 获取 time_label 的 top 坐标 (假设 time_label 已经在 window.time_label 中设置)
    # 根据 ui_setup.py 中的定义：time_label.setGeometry(10, 40, 100, 20)
    time_label_y = 30 
    
    # 将 MutatorManager 放置在窗口右侧，从 time_label 的顶部开始
    # 高度暂时设为 250，以便容纳所有按钮。最终高度将在 MutatorManager 内部决定。
    window.mutator_manager.setGeometry(mutator_x, time_label_y, config.MUTATOR_WIDTH, 250)

def setup_bottom_buttons(window):
    """
    初始化表格下方的功能按钮区域
    包含：Memo 按钮、预留位置、以及废弃的指挥官替换按钮占位
    """
    # --- 常量定义 ---
    AREA_HEIGHT = 35  # 底部区域总高度
    BTN_SIZE = 27     # 按钮大小
    
    # --- 1. 创建底部容器 ---
    start_y = window.table_area.geometry().bottom() + 5
    
    window.bottom_button_area = QWidget(window.main_container)
    window.bottom_button_area.setStyleSheet("background-color: transparent;")
    window.bottom_button_area.setGeometry(0, start_y, config.MAIN_WINDOW_WIDTH - config.MUTATOR_WIDTH , AREA_HEIGHT)

    # --- 2. 设置水平布局 ---
    # 这就是"依次添加"的核心
    layout = QHBoxLayout(window.bottom_button_area)
    layout.setContentsMargins(5, 0, 5, 0)       # 设置边距：左5, 上0, 右5, 下0
    layout.setSpacing(5)                        # 设置按钮之间的间距
    layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter) # 靠左对齐，垂直居中

    # --- 3. 定义通用样式和创建函数 (工厂模式) ---
    # 这样你可以方便地添加任意数量的按钮，样式统一
    def add_icon_button(text, tooltip):
        btn = QPushButton(text) # 注意：使用布局时，父对象会在 addWidget 时自动指定
        btn.setFixedSize(BTN_SIZE, BTN_SIZE)
        btn.setToolTip(tooltip)
        btn.setStyleSheet("""
            QPushButton {
                color: rgb(200, 200, 200);
                background-color: rgba(60, 60, 60, 200);
                border: 1px solid rgba(100, 100, 100, 100);
                border-radius: 3px;
                font-weight: bold;

                font-size: 12px;
            }
            QPushButton:hover {
                background-color: rgba(80, 80, 80, 200);
                color: white;
                border: 1px solid rgba(150, 150, 150, 150);
            }
            QPushButton:pressed {
                background-color: rgba(100, 100, 100, 200);
            }
        """)
        layout.addWidget(btn) # <--- 关键：添加到布局中，自动排列
        return btn

    # --- 4. 依次添加按钮 ---
    
    window.memo_btn = add_icon_button("📝", "笔记本")
    window.countdown_btn = add_icon_button("⏰", "自定义倒计时")
    window.setting_btn = add_icon_button("⚙️", "设置界面") 
    window.exit_btn = add_icon_button("🏃", "退出") 


    # --- 5. 处理废弃的 Replace Commander Button (隐藏占位) ---
    # 注意：这个按钮我们不放入布局，直接隐藏即可
    window.replace_commander_btn = QPushButton(window.main_container)
    window.replace_commander_btn.setFixedSize(0, 0)
    window.replace_commander_btn.hide()


    # --- 6. 最终调整主窗口高度 ---
    final_height = window.bottom_button_area.geometry().bottom() + 5
    window.main_container.setFixedHeight(final_height)
    window.setFixedHeight(window.main_container.height())
    
    # 定位：左侧留 5px 边距，垂直居中
    # 垂直居中计算: (AREA_HEIGHT - BTN_SIZE) / 2 = (35 - 27) / 2 = 4
    window.memo_btn.move(5, 4)
    

def pinyin_key(text: str):
    """
    返回拼音首字母串，用于排序
    """
    return ''.join(
        lazy_pinyin(text, style=Style.FIRST_LETTER)
    )

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
    setup_mutator_ui(window)
    setup_bottom_buttons(window)
    # 强制显示窗口 (保持原样)
    window.show()
    # Windows 置顶处理 (保持在 qt_gui.py 中调用)