from PyQt5.QtWidgets import QLabel
from PyQt5.QtGui import QPainter, QPen, QColor
from PyQt5.QtCore import Qt

class LOutlinedLabel(QLabel):
    def __init__(self, outline_color = QColor(0, 0, 0), parent=None):
        super(OutlinedLabel, self).__init__(parent)
        if isinstance(outline_color, str):
            self.outline_color = QColor(outline_color)
        else:
            self.outline_color = outline_color  # 默认描边颜色为黑色
        self.outline_width = 5  # 默认描边宽度为2

    def setOutlineColor(self, color):
        self.outline_color = QColor(color)
        self.update()

    def setOutlineWidth(self, width):
        self.outline_width = width
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 字体
        font = self.font()
        font.setPointSize(self.font().pointSize())
        painter.setFont(font)
        
        # 文本
        text = self.text()
        rect = self.contentsRect()
        
        # 绘制描边
        pen = QPen()
        pen.setColor(self.outline_color)
        pen.setWidth(self.outline_width)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        
        # 移动9个方向绘制描边
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                if dx == 0 and dy == 0:
                    continue
                outline_rect = rect.translated(dx, dy)
                painter.drawText(outline_rect, self.alignment(), text)
        
        # 绘制前景文本
        painter.setPen(QPen(self.palette().text().color()))
        painter.setBrush(self.palette().text().color())
        painter.drawText(rect, self.alignment(), text)