from PyQt5.QtWidgets import QLabel
from PyQt5.QtGui import QPainter, QPen, QColor, QPainterPath, QFontMetrics # 新增 QFontMetrics
from PyQt5.QtCore import Qt
import re

class OutlinedLabel(QLabel):
    def __init__(self, outline_color=QColor(0, 0, 0), outline_width=2, parent=None):
        super(OutlinedLabel, self).__init__(parent)
        
        self.outline_color = QColor(0, 0, 0)
        self.outline_width = 2
        
        self.setOutlineColor(outline_color)
        self.setOutlineWidth(outline_width)

    def setOutlineColor(self, color):
        parsed_color = QColor(0, 0, 0)
        
        if isinstance(color, str):
            match = re.match(r'rgb\((\d+),\s*(\d+),\s*(\d+)\)', color)
            if match:
                r, g, b = map(int, match.groups())
                parsed_color = QColor(r, g, b)
            else:
                parsed_color.setNamedColor(color)
        elif isinstance(color, QColor):
            parsed_color = color
        
        if parsed_color.isValid():
            self.outline_color = parsed_color
        else:
            self.outline_color = QColor(0, 0, 0)
        self.update()

    def setOutlineWidth(self, width):
        if isinstance(width, (int, float)):
            self.outline_width = int(width)
        else:
            self.outline_width = 2
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        font = self.font()
        font.setPointSize(self.font().pointSize())
        painter.setFont(font)

        text = self.text()
        rect = self.contentsRect()
        
        # 使用 QFontMetrics 计算正确的文本位置
        font_metrics = QFontMetrics(font)
        # 基线y坐标 = 绘制区域的y + 字体ascender + 描边宽度
        y_pos = rect.y() + font_metrics.ascent() + self.outline_width

        # 1. 创建文本路径
        path = QPainterPath()
        path.addText(rect.x(), y_pos, font, text)

        # 2. 绘制描边
        pen = QPen()
        pen.setColor(self.outline_color)
        pen.setWidth(self.outline_width)
        pen.setJoinStyle(Qt.RoundJoin) 
        
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
        
        # 3. 绘制前景文本
        painter.setPen(Qt.NoPen) 
        painter.setBrush(self.palette().text().color())
        painter.drawPath(path)