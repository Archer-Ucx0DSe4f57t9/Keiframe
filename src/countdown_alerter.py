import os
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QPixmap
from PyQt5.QtWidgets import QLabel, QHBoxLayout

from fileutil import get_resources_dir


class CountdownAlert(QLabel):
    def __init__(self, parent=None, icon_name=None, font_size=16):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.hide()

        self._last_message = None
        self._last_color = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        # 图标
        self.icon_label = None
        if icon_name:
            self.icon_label = QLabel()
            icon_path = os.path.join(get_resources_dir(), 'ico', 'mutator', icon_name)
            if os.path.exists(icon_path):
                self.icon_label.setPixmap(
                    QPixmap(icon_path).scaled(font_size, font_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
                layout.addWidget(self.icon_label)

        # 文本
        self.text_label = QLabel()
        self.text_label.setFont(QFont('Arial', font_size))
        layout.addWidget(self.text_label)

    def update_alert(self, message, color, x=None, y=None, width=None, height=None):
        """
        更新文本和颜色，并且可以通过参数设置位置和大小。
        """
        if message != self._last_message or color != self._last_color:
            self.text_label.setText(message)
            self.text_label.setStyleSheet(f'color: {color}; background-color: transparent;')
            self._last_message = message
            self._last_color = color

        if x is not None and y is not None:
            if width and height:
                self.setFixedSize(width, height)
            self.move(x, y)

        if not self.isVisible():
            self.show()

    def hide_alert(self):
        self.hide()
