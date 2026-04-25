from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtGui import QPainter, QLinearGradient, QColor, QPen, QPainterPath


class AeroTitleBar(QWidget):
    """Royale Noir / Aero Black 风格标题栏"""
    def __init__(self, parent_window, title=""):
        super().__init__(parent_window)
        self.parent_window = parent_window
        self._dragging = False
        self._drag_pos = QPoint()

        self.setObjectName("titleBar")
        self.setFixedHeight(32)
        self.setMouseTracking(True)
        self.setAutoFillBackground(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 6, 0)
        layout.setSpacing(4)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("titleLabel")
        self.title_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        layout.addWidget(self.title_label)
        layout.addStretch()

        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("titleCloseButton")
        self.close_btn.setFixedSize(26, 20)
        self.close_btn.clicked.connect(self.parent_window.close)

        layout.addWidget(self.close_btn)

    def set_title(self, title):
        self.title_label.setText(title)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        rect = self.rect().adjusted(0, 0, -1, -1)
        radius = 10

        path = QPainterPath()
        path.moveTo(rect.left(), rect.bottom())
        path.lineTo(rect.left(), rect.top() + radius)
        path.quadTo(rect.left(), rect.top(), rect.left() + radius, rect.top())
        path.lineTo(rect.right() - radius, rect.top())
        path.quadTo(rect.right(), rect.top(), rect.right(), rect.top() + radius)
        path.lineTo(rect.right(), rect.bottom())
        path.closeSubpath()

        grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        grad.setColorAt(0.00, QColor(78, 92, 124, 220))
        grad.setColorAt(0.16, QColor(36, 43, 58, 228))
        grad.setColorAt(0.55, QColor(12, 14, 20, 234))
        grad.setColorAt(1.00, QColor(3, 4, 6, 240))
        painter.fillPath(path, grad)

        gloss_rect = rect.adjusted(1, 1, -1, -rect.height() // 2)
        gloss = QLinearGradient(gloss_rect.topLeft(), gloss_rect.bottomLeft())
        gloss.setColorAt(0.0, QColor(255, 255, 255, 70))
        gloss.setColorAt(0.35, QColor(180, 205, 255, 32))
        gloss.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillRect(gloss_rect, gloss)

        painter.setPen(QPen(QColor(235, 245, 255, 60), 1))
        painter.drawLine(rect.left() + radius, rect.top(), rect.right() - radius, rect.top())

        painter.setPen(QPen(QColor(120, 150, 205, 45), 1))
        painter.drawLine(rect.left() + 1, rect.bottom(), rect.right() - 1, rect.bottom())

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_pos = event.globalPos() - self.parent_window.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging and event.buttons() & Qt.LeftButton:
            self.parent_window.move(event.globalPos() - self._drag_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._dragging = False
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        event.accept()