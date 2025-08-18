import os
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QPixmap, QPainter, QPen, QColor
from PyQt5.QtWidgets import QLabel, QHBoxLayout

from fileutil import get_resources_dir

class OutlinedLabel(QLabel):
    def __init__(self, outline_color, parent=None):
        super().__init__(parent)
        self.outline_color = QColor(outline_color)
        self.outline_width = 1
        self.font_size = 16

    def setFontSize(self, font_size):
        self.font_size = font_size
        self.update()

    def setOutlineWidth(self, width):
        self.outline_width = width
        self.update()

    def setOutlineColor(self, color):
        self.outline_color = QColor(color)
        self.update()

    def bestIntValueForShadow(self, para):
        if para > 1:
            return int(para)
        else:
            return 1
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 1. 绘制阴影
        self.setOutlineWidth(self.bestIntValueForShadow(self.font_size*0.1))
        pen = QPen(self.outline_color, self.outline_width * 2)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)

        # 创建一个偏移矩形，用于绘制阴影，使它与主文本不重叠
        shadow_offset = self.bestIntValueForShadow(self.font_size * 0.1)
        shadow_rect = self.rect().translated(shadow_offset, shadow_offset)
        painter.drawText(shadow_rect, Qt.AlignCenter, self.text())

        # 2. 绘制主文本
        painter.setPen(QPen(self.palette().color(self.foregroundRole())))
        painter.drawText(self.rect(), Qt.AlignCenter, self.text())

        painter.end()


class CountdownAlert(QLabel):
    def __init__(self, parent=None, icon_name=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.hide()

        self._last_message = None
        self._last_color = None
        self.icon_name = icon_name

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        # 图标
        self.icon_label = None
        if icon_name:
            self.icon_label = QLabel()
            layout.addWidget(self.icon_label)

        # 文本
        self.text_label = OutlinedLabel(outline_color='black')
        self.text_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.text_label.setOutlineWidth(2)  # 设置描边宽度
        self.text_label.setAlignment(Qt.AlignVCenter)
        layout.addWidget(self.text_label)

    def update_alert(self, message, color, x=None, y=None, width=None, height=None, font_size = 16):
        """
        更新文本和颜色，并且可以通过参数设置位置和大小。
        """
        self.text_label.setFont(QFont('Arial', font_size))
        self.text_label.setFontSize(font_size) #阴影用

        if self.icon_label:
            icon_path = os.path.join(get_resources_dir(), 'ico', 'mutator', self.icon_name)
            if os.path.exists(icon_path):
                self.icon_label.setPixmap(
                    QPixmap(icon_path).scaled(font_size, font_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )

        if message != self._last_message or color != self._last_color:
            self.text_label.setText(message)
            # 更新样式以改变颜色，并保留阴影
            self.text_label.setStyleSheet(
                f'color: {color};'
                'background-color: transparent;'
            )
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