import os
import time
import traceback
import re
from PyQt5.QtWidgets import QWidget, QLabel
from PyQt5.QtCore import QTimer, QPoint, Qt
from PyQt5.QtGui import QFont, QColor
import config

class MutatorHandlers:
    """
    处理突变因子相关的逻辑和提醒。
    """
    def __init__(self, parent=None):
        self.parent = parent
        self.mutator_alert_timer = QTimer(self.parent)
        self.mutator_alert_timer.timeout.connect(self.hide_mutator_alert)
        self.alerted_points = set()
        self.mutator_window = None

    def show_mutator_alert(self, text, mutator_type):
        """
        显示一个突变因子提醒窗口。
        """
        # 如果窗口已存在，则更新文本
        if self.mutator_window:
            self.mutator_window.label.setText(text)
            self.mutator_window.show()
            self.mutator_alert_timer.start(5000)
            return

        # 创建并显示新的提醒窗口
        self.mutator_window = QWidget()
        self.mutator_window.setWindowFlags(Qt.SplashScreen | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.mutator_window.setAttribute(Qt.WA_TranslucentBackground)
        self.mutator_window.setFixedSize(300, 50)
        self.mutator_window.setStyleSheet(f"background-color: {self.get_mutator_color(mutator_type)}; border-radius: 10px;")

        label = QLabel(text, self.mutator_window)
        label.setFont(QFont("Inter", 12))
        label.setStyleSheet("color: white;")
        label.setAlignment(Qt.AlignCenter)
        label.setGeometry(0, 0, 300, 50)
        self.mutator_window.label = label
        
        # 将窗口放置在右下角
        screen_geometry = self.parent.screen().geometry()
        x = screen_geometry.width() - self.mutator_window.width() - 10
        y = screen_geometry.height() - self.mutator_window.height() - 10
        self.mutator_window.move(x, y)

        self.mutator_window.show()
        self.mutator_alert_timer.start(5000)

    def hide_mutator_alert(self):
        """
        隐藏突变因子提醒窗口。
        """
        if self.mutator_window:
            self.mutator_window.hide()

    def get_mutator_color(self, mutator_type):
        """
        根据突变因子类型返回颜色。
        """
        if mutator_type == "普通":
            return "#3498db"
        elif mutator_type == "困难":
            return "#e67e22"
        elif mutator_type == "残酷":
            return "#e74c3c"
        else:
            return "#7f8c8d"

    def check_mutator_alerts(self, current_time):
        """
        检查是否需要提醒突变因子。
        """
        try:
            # ... (此处省略了原始代码中的具体文件读取和逻辑)
            # 您需要将原始代码中 check_mutator_alerts 的逻辑复制到这里
            pass
        except Exception as e:
            # self.logger.error(f'检查突变因子提醒失败: {str(e)}')
            # self.logger.error(traceback.format_exc())
            pass
