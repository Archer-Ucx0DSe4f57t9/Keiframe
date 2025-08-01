from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QLabel, QSystemTrayIcon,
    QMenu, QAction, QApplication, QComboBox,
    QTableWidgetItem, QPushButton, QTableWidget,
    QHeaderView, QVBoxLayout, QGraphicsDropShadowEffect, QHBoxLayout
)
from PyQt5.QtGui import QFont, QIcon, QPixmap, QBrush, QColor, QCursor
from PyQt5.QtCore import Qt, QTimer, QPoint, pyqtSignal, QRect, QSize
import config
from fileutil import get_resources_dir, list_files

class UIInitializer:
    """
    负责初始化所有 UI 组件。
    """
    def init_ui(self):
        """
        初始化主窗口的用户界面。
        """
        self.setWindowIcon(QIcon(os.path.join(get_resources_dir(), 'logo.ico')))
        self.set_window_background()

        main_layout = QVBoxLayout()
        # 创建一个主容器 QWidget
        main_widget = QWidget()
        main_widget.setObjectName("main_widget")
        main_widget.setStyleSheet(
            """
            #main_widget {
                background-color: #2e3436;
            }
            """
        )
        self.setCentralWidget(main_widget)

        # 游戏时间标签
        self.time_label = QLabel("00:00", self)
        self.time_label.setFont(QFont("Inter", 60, QFont.Bold))
        self.time_label.setStyleSheet("color: #E0E0E0;")
        self.time_label.setAlignment(Qt.AlignCenter)
        self.time_label.setGraphicsEffect(self.create_shadow_effect())
        main_layout.addWidget(self.time_label)

        # 地图名称标签
        self.map_label = QLabel("正在搜索游戏...", self)
        self.map_label.setFont(QFont("Inter", 12))
        self.map_label.setStyleSheet("color: #E0E0E0;")
        self.map_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.map_label)

        # ... (此处省略了原始代码中其他 UI 控件的创建和布局)

    def set_window_background(self):
        """
        设置窗口的背景。
        """
        self.setAutoFillBackground(True)
        p = self.palette()
        p.setBrush(self.backgroundRole(), QBrush(QColor(46, 52, 54, 200)))
        self.setPalette(p)

    def create_shadow_effect(self):
        """
        创建并返回一个阴影效果。
        """
        shadow_effect = QGraphicsDropShadowEffect()
        shadow_effect.setBlurRadius(10)
        shadow_effect.setColor(QColor(0, 0, 0, 150))
        shadow_effect.setOffset(2, 2)
        return shadow_effect
