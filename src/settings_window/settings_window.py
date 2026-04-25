# settings_window.py
import json
import os
import sys
import copy
import re
import tempfile

from PyQt5 import QtCore
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QLabel, QLineEdit, QSpinBox, QDoubleSpinBox,
    QCheckBox, QPushButton, QColorDialog, QMessageBox,
    QFormLayout, QScrollArea, QDialog, QComboBox, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
    QFrame, QGraphicsDropShadowEffect, QProxyStyle, QStyle
)
from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QRect
from PyQt5.QtGui import QKeyEvent, QColor, QKeySequence, QPolygon, QPixmap, QPainter

from src import config
from src.utils.logging_util import get_logger
from src.utils.fileutil import get_resources_dir, get_project_root
from src.utils.excel_utils import ExcelUtil
from src.utils.data_validator import DataValidator
from src.db import map_daos, mutator_daos
from src.settings_window.widgets import HotkeyInput, ColorInput
from src.settings_window.complex_inputs import DictInput, DictTable, CountdownOptionsInput
from src.settings_window.tabs import SettingsTabsBuilder
from src.settings_window.setting_data_handler import SettingsHandler

class DarkArrowProxyStyle(QProxyStyle):
    """为深色主题强制绘制清晰可见的箭头"""
    def __init__(self, base_style=None):
        super().__init__(base_style)

    def drawPrimitive(self, element, option, painter, widget=None):
        arrow_elements = {
            QStyle.PE_IndicatorArrowUp,
            QStyle.PE_IndicatorArrowDown,
            QStyle.PE_IndicatorArrowLeft,
            QStyle.PE_IndicatorArrowRight,
        }

        if element in arrow_elements:
            rect = option.rect.adjusted(1, 1, -1, -1)
            if rect.width() <= 0 or rect.height() <= 0:
                return

            cx = rect.center().x()
            cy = rect.center().y()

            size = max(4, min(rect.width(), rect.height()) // 2)

            if element == QStyle.PE_IndicatorArrowDown:
                points = [
                    QPoint(cx - size, cy - size // 2),
                    QPoint(cx + size, cy - size // 2),
                    QPoint(cx, cy + size),
                ]
            elif element == QStyle.PE_IndicatorArrowUp:
                points = [
                    QPoint(cx - size, cy + size // 2),
                    QPoint(cx + size, cy + size // 2),
                    QPoint(cx, cy - size),
                ]
            elif element == QStyle.PE_IndicatorArrowLeft:
                points = [
                    QPoint(cx + size // 2, cy - size),
                    QPoint(cx + size // 2, cy + size),
                    QPoint(cx - size, cy),
                ]
            else:  # QStyle.PE_IndicatorArrowRight
                points = [
                    QPoint(cx - size // 2, cy - size),
                    QPoint(cx - size // 2, cy + size),
                    QPoint(cx + size, cy),
                ]

            painter.save()
            painter.setRenderHint(painter.Antialiasing, True)

            # 先画一层深色阴影，避免白箭头贴在浅背景时发虚
            shadow_offset = QPoint(0, 1)
            shadow_poly = QPolygon([p + shadow_offset for p in points])
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 0, 0, 170))
            painter.drawPolygon(shadow_poly)

            # 再画主箭头
            painter.setBrush(QColor(245, 245, 245, 245))
            painter.drawPolygon(QPolygon(points))
            painter.restore()
            return

        super().drawPrimitive(element, option, painter, widget)

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

        self.min_btn = QPushButton("—")
        self.min_btn.setObjectName("titleMinButton")
        self.min_btn.setFixedSize(26, 20)
        self.min_btn.clicked.connect(self.parent_window.showMinimized)

        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("titleCloseButton")
        self.close_btn.setFixedSize(26, 20)
        self.close_btn.clicked.connect(self.parent_window.close)

        layout.addWidget(self.min_btn)
        layout.addWidget(self.close_btn)

    def set_title(self, title):
        self.title_label.setText(title)

    def paintEvent(self, event):
        from PyQt5.QtGui import QPainter, QLinearGradient, QColor, QPen, QPainterPath

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

        # 主体深色渐变：更接近 Royale Noir，而不是 XP 纯黑条
        grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        grad.setColorAt(0.00, QColor(78, 92, 124, 220))
        grad.setColorAt(0.16, QColor(36, 43, 58, 228))
        grad.setColorAt(0.55, QColor(12, 14, 20, 234))
        grad.setColorAt(1.00, QColor(3, 4, 6, 240))
        painter.fillPath(path, grad)

        # 顶部冷色高光
        gloss_rect = rect.adjusted(1, 1, -1, -rect.height() // 2)
        gloss = QLinearGradient(gloss_rect.topLeft(), gloss_rect.bottomLeft())
        gloss.setColorAt(0.0, QColor(255, 255, 255, 70))
        gloss.setColorAt(0.35, QColor(180, 205, 255, 32))
        gloss.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillRect(gloss_rect, gloss)

        # 顶边亮线
        painter.setPen(QPen(QColor(235, 245, 255, 60), 1))
        painter.drawLine(rect.left() + radius, rect.top(), rect.right() - radius, rect.top())

        # 底部分隔线
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

class SettingsWindow(QDialog):
    settings_saved = pyqtSignal(dict)

class SettingsWindow(QDialog):
    settings_saved = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings_file = os.path.join(get_project_root(), 'settings.json')
        self.data_handler = SettingsHandler(
            self.settings_file,
            maps_db=parent.maps_db if parent else None,
            mutators_db=parent.mutators_db if parent else None
        )
        self.main_window = parent

        self.logger = get_logger("setting window")
        self.current_config = self.data_handler.load_config()
        self.original_config = copy.deepcopy(self.current_config)
        self.widgets = {}

        # 无边框 / 半透明 / 自定义缩放参数
        self._resize_margin = 8
        self._resizing = False
        self._resize_edges = set()
        self._resize_start_pos = QPoint()
        self._resize_start_geom = QRect()

        self._arrow_icon_paths = {}
        self._setup_window_shell()

        self.setWindowTitle("系统设置 / Settings")
        self.resize(1000, 980)
        self.setMinimumSize(920, 820)

        self._first_show_layout_fixed = False

        self.init_ui()
        self._ensure_arrow_icons()
        self.apply_dark_theme()
        self.disable_all_spinbox_wheels()

    # =========================
    # 窗口外壳
    # =========================
    def _setup_window_shell(self):
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
    
    def _ensure_arrow_icons(self):
        """生成深色主题下可见的白色箭头 PNG，供 QSS 显式引用"""
        cache_dir = os.path.join(tempfile.gettempdir(), "sc2timer_ui_icons")
        os.makedirs(cache_dir, exist_ok=True)

        down_path = os.path.join(cache_dir, "arrow_down_white.png")
        up_path = os.path.join(cache_dir, "arrow_up_white.png")

        if not os.path.exists(down_path):
            self._create_arrow_icon(down_path, "down")
        if not os.path.exists(up_path):
            self._create_arrow_icon(up_path, "up")

        self._arrow_icon_paths = {
            "down": down_path.replace("\\", "/"),
            "up": up_path.replace("\\", "/"),
        }

    def _create_arrow_icon(self, save_path, direction="down", size=14):
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)

        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)

        cx = size // 2
        cy = size // 2
        s = max(4, size // 3)

        if direction == "down":
            points = [
                QPoint(cx - s, cy - 1),
                QPoint(cx + s, cy - 1),
                QPoint(cx, cy + s),
            ]
        else:  # up
            points = [
                QPoint(cx - s, cy + 1),
                QPoint(cx + s, cy + 1),
                QPoint(cx, cy - s),
            ]

        # 阴影
        shadow_points = [QPoint(p.x(), p.y() + 1) for p in points]
        painter.setBrush(QColor(0, 0, 0, 170))
        painter.drawPolygon(QPolygon(shadow_points))

        # 主箭头
        painter.setBrush(QColor(248, 248, 248, 255))
        painter.drawPolygon(QPolygon(points))

        painter.end()
        pix.save(save_path, "PNG")

    def apply_dark_theme(self):
        self.setStyleSheet("""
        QWidget {
            color: #e8e8e8;
            font-size: 12pt;
        }

        QDialog {
            background: transparent;
        }

        QFrame#windowFrame {
            background-color: rgba(8, 8, 8, 138);
            border: 1px solid rgba(255, 255, 255, 26);
            border-radius: 10px;
        }

        QWidget#titleBar {
            background: transparent;
            border: none;
        }

        QLabel#titleLabel {
            font-size: 12pt;
            font-weight: 600;
            color: #f7f7f7;
            background: transparent;
            padding-left: 2px;
        }

        QFrame#contentArea {
            background: transparent;
            border: none;
            border-bottom-left-radius: 10px;
            border-bottom-right-radius: 10px;
        }

        QTabWidget::pane {
            border: 1px solid rgba(255, 255, 255, 18);
            background-color: rgba(10, 10, 10, 139);
            border-radius: 8px;
            top: -1px;
        }

        QTabBar::tab {
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(70, 74, 84, 165),
                stop:0.45 rgba(28, 30, 36, 170),
                stop:1 rgba(12, 12, 14, 178)
            );
            color: #d7dbe5;
            border: 1px solid rgba(255, 255, 255, 20);
            padding: 5px 10px;
            min-width: 48px;
            max-width: 88px;
            min-height: 18px;
            border-top-left-radius: 5px;
            border-top-right-radius: 5px;
            margin-right: 2px;
        }

        QTabBar::tab:selected {
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(110, 126, 160, 182),
                stop:0.22 rgba(54, 60, 74, 186),
                stop:1 rgba(18, 18, 24, 190)
            );
            color: #ffffff;
            border-bottom-color: rgba(135, 180, 245, 120);
        }

        QTabBar::tab:hover:!selected {
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(86, 92, 108, 175),
                stop:1 rgba(24, 24, 30, 182)
            );
        }

        QTabBar QToolButton {
            background-color: rgba(18, 18, 18, 175);
            color: #f0f0f0;
            border: 1px solid rgba(255, 255, 255, 18);
            border-radius: 3px;
            width: 18px;
            height: 18px;
            margin-top: 2px;
            margin-bottom: 2px;
            padding: 0px;
        }

        QTabBar QToolButton:hover {
            background-color: rgba(68, 92, 136, 190);
        }

        QScrollArea {
            border: none;
            background: transparent;
        }

        QScrollArea > QWidget > QWidget {
            background: transparent;
        }

        QGroupBox {
            background-color: rgba(20, 20, 20, 116);
            border: 1px solid rgba(255, 255, 255, 18);
            border-radius: 8px;
            margin-top: 12px;
            padding-top: 12px;
            font-weight: 600;
        }

        QGroupBox::title {
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 6px 0 6px;
            color: #ededed;
            background: transparent;
        }

        QLabel {
            background: transparent;
        }

        QLineEdit,
        QSpinBox,
        QDoubleSpinBox,
        QComboBox,
        QTableWidget,
        QHeaderView::section {
            background-color: rgba(32, 32, 32, 168);
            color: #f0f0f0;
        }

        QLineEdit,
        QSpinBox,
        QDoubleSpinBox,
        QComboBox {
            border: 1px solid rgba(255, 255, 255, 28);
            border-radius: 5px;
            padding: 4px 6px 4px 8px;
            min-height: 18px;
            selection-background-color: rgba(95, 145, 220, 150);
        }

        QLineEdit:focus,
        QSpinBox:focus,
        QDoubleSpinBox:focus,
        QComboBox:focus,
        QTableWidget:focus {
            border: 1px solid rgba(120, 175, 245, 155);
        }

        QComboBox::drop-down {
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 24px;
            border-left: 1px solid rgba(255, 255, 255, 26);
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(70, 74, 84, 205),
                stop:1 rgba(28, 30, 36, 215)
            );
            border-top-right-radius: 5px;
            border-bottom-right-radius: 5px;
        }

        QComboBox::drop-down:hover {
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(96, 110, 138, 220),
                stop:1 rgba(42, 48, 62, 228)
            );
        }

        QSpinBox,
        QDoubleSpinBox {
            padding-right: 20px;
        }

        QSpinBox::up-button,
        QSpinBox::down-button,
        QDoubleSpinBox::up-button,
        QDoubleSpinBox::down-button {
            subcontrol-origin: border;
            width: 18px;
            border-left: 1px solid rgba(255, 255, 255, 24);
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(72, 76, 86, 205),
                stop:1 rgba(28, 30, 36, 218)
            );
        }

        QSpinBox::up-button,
        QDoubleSpinBox::up-button {
            subcontrol-position: top right;
            border-top-right-radius: 5px;
            border-bottom: 1px solid rgba(255, 255, 255, 18);
        }

        QSpinBox::down-button,
        QDoubleSpinBox::down-button {
            subcontrol-position: bottom right;
            border-bottom-right-radius: 5px;
        }

        QSpinBox::up-button:hover,
        QSpinBox::down-button:hover,
        QDoubleSpinBox::up-button:hover,
        QDoubleSpinBox::down-button:hover {
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(102, 114, 142, 222),
                stop:1 rgba(40, 46, 60, 228)
            );
        }

        QComboBox QAbstractItemView {
            background-color: rgba(22, 22, 22, 225);
            color: #f0f0f0;
            border: 1px solid rgba(255, 255, 255, 20);
            selection-background-color: rgba(86, 130, 190, 160);
            selection-color: white;
        }

        QCheckBox {
            spacing: 8px;
        }

        QCheckBox::indicator {
            width: 16px;
            height: 16px;
            border-radius: 3px;
            border: 1px solid rgba(255, 255, 255, 30);
            background: rgba(30, 30, 30, 150);
        }

        QCheckBox::indicator:checked {
            background: rgba(88, 132, 198, 185);
            border: 1px solid rgba(140, 185, 245, 200);
        }

        QTableWidget {
            border: 1px solid rgba(255, 255, 255, 18);
            border-radius: 6px;
            gridline-color: rgba(255, 255, 255, 16);
            selection-background-color: rgba(75, 118, 180, 145);
            alternate-background-color: rgba(46, 46, 46, 120);
        }

        QHeaderView::section {
            border: none;
            border-right: 1px solid rgba(255, 255, 255, 16);
            border-bottom: 1px solid rgba(255, 255, 255, 16);
            padding: 7px;
            font-weight: 600;
            background-color: rgba(40, 40, 40, 172);
        }

        QTableCornerButton::section {
            background-color: rgba(40, 40, 40, 172);
            border: none;
            border-right: 1px solid rgba(255, 255, 255, 16);
            border-bottom: 1px solid rgba(255, 255, 255, 16);
        }

        QPushButton {
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(68, 68, 68, 190),
                stop:1 rgba(28, 28, 28, 198)
            );
            color: #f4f4f4;
            border: 1px solid rgba(255, 255, 255, 24);
            border-radius: 5px;
            padding: 6px 14px;
            min-height: 30px;
        }

        QPushButton:hover {
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(88, 88, 88, 205),
                stop:1 rgba(34, 34, 34, 210)
            );
        }

        QPushButton:pressed {
            background-color: rgba(20, 20, 20, 220);
        }

        QPushButton#accentButton {
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(96, 138, 202, 210),
                stop:1 rgba(54, 88, 148, 215)
            );
            border: 1px solid rgba(170, 205, 255, 100);
            font-weight: 600;
            min-height: 32px;
        }

        QPushButton#accentButton:hover {
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(110, 150, 215, 225),
                stop:1 rgba(60, 97, 158, 228)
            );
        }

        QPushButton#titleMinButton {
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(78, 82, 92, 235),
                stop:0.5 rgba(36, 38, 44, 240),
                stop:1 rgba(18, 18, 20, 242)
            );
            color: white;
            border: 1px solid rgba(220, 230, 255, 70);
            border-radius: 3px;
            padding: 0px;
            min-height: 20px;
            font-size: 10pt;
            font-weight: bold;
        }

        QPushButton#titleMinButton:hover {
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(102, 108, 122, 245),
                stop:1 rgba(28, 28, 34, 245)
            );
        }

        QPushButton#titleMinButton:pressed {
            background: rgba(20, 20, 24, 245);
        }

        QPushButton#titleCloseButton {
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(255, 146, 104, 248),
                stop:0.45 rgba(222, 82, 40, 248),
                stop:1 rgba(170, 36, 16, 248)
            );
            color: white;
            border: 1px solid rgba(255, 245, 240, 95);
            border-radius: 3px;
            padding: 0px;
            min-height: 20px;
            font-size: 10pt;
            font-weight: bold;
        }

        QPushButton#titleCloseButton:hover {
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(255, 170, 128, 252),
                stop:0.45 rgba(240, 96, 52, 252),
                stop:1 rgba(188, 42, 18, 252)
            );
        }

        QPushButton#titleCloseButton:pressed {
            background: rgba(150, 28, 12, 252);
        }

        QFrame#bottomBar {
            background: transparent;
            border: none;
        }

        QScrollBar:vertical {
            background: rgba(18, 18, 18, 110);
            width: 10px;
            margin: 2px;
            border-radius: 5px;
        }

        QScrollBar::handle:vertical {
            background: rgba(126, 126, 126, 155);
            min-height: 24px;
            border-radius: 5px;
        }

        QScrollBar::handle:vertical:hover {
            background: rgba(158, 158, 158, 180);
        }

        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical {
            height: 0px;
        }

        QScrollBar:horizontal {
            background: rgba(18, 18, 18, 110);
            height: 10px;
            margin: 2px;
            border-radius: 5px;
        }

        QScrollBar::handle:horizontal {
            background: rgba(126, 126, 126, 155);
            min-width: 24px;
            border-radius: 5px;
        }

        QScrollBar::handle:horizontal:hover {
            background: rgba(158, 158, 158, 180);
        }

        QScrollBar::add-line:horizontal,
        QScrollBar::sub-line:horizontal {
            width: 0px;
        }

        QToolTip {
            background-color: rgba(20, 20, 20, 230);
            color: #f2f2f2;
            border: 1px solid rgba(255, 255, 255, 18);
            padding: 5px;
        }
        """)

        down_icon = self._arrow_icon_paths.get("down", "")
        up_icon = self._arrow_icon_paths.get("up", "")

        self.setStyleSheet(
            self.styleSheet() +
            f"""
            QComboBox::down-arrow {{
                image: url("{down_icon}");
                width: 12px;
                height: 12px;
            }}

            QSpinBox::up-arrow,
            QDoubleSpinBox::up-arrow {{
                image: url("{up_icon}");
                width: 10px;
                height: 10px;
            }}

            QSpinBox::down-arrow,
            QDoubleSpinBox::down-arrow {{
                image: url("{down_icon}");
                width: 10px;
                height: 10px;
            }}
            """
        )

    # =========================
    # 窗口缩放
    # =========================
    def _hit_test_edges(self, pos):
        rect = self.rect()
        m = self._resize_margin
        edges = set()

        if pos.x() <= m:
            edges.add("left")
        elif pos.x() >= rect.width() - m:
            edges.add("right")

        if pos.y() <= m:
            edges.add("top")
        elif pos.y() >= rect.height() - m:
            edges.add("bottom")

        return edges

    def _update_resize_cursor(self, edges):
        if not edges:
            self.setCursor(Qt.ArrowCursor)
            return

        if ("left" in edges and "top" in edges) or ("right" in edges and "bottom" in edges):
            self.setCursor(Qt.SizeFDiagCursor)
        elif ("right" in edges and "top" in edges) or ("left" in edges and "bottom" in edges):
            self.setCursor(Qt.SizeBDiagCursor)
        elif "left" in edges or "right" in edges:
            self.setCursor(Qt.SizeHorCursor)
        elif "top" in edges or "bottom" in edges:
            self.setCursor(Qt.SizeVerCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    def _perform_resize(self, global_pos):
        start = self._resize_start_geom
        delta = global_pos - self._resize_start_pos

        left = start.left()
        right = start.right()
        top = start.top()
        bottom = start.bottom()

        min_w = self.minimumWidth()
        min_h = self.minimumHeight()

        if "left" in self._resize_edges:
            left = min(start.left() + delta.x(), start.right() - min_w + 1)
        if "right" in self._resize_edges:
            right = max(start.right() + delta.x(), start.left() + min_w - 1)
        if "top" in self._resize_edges:
            top = min(start.top() + delta.y(), start.bottom() - min_h + 1)
        if "bottom" in self._resize_edges:
            bottom = max(start.bottom() + delta.y(), start.top() + min_h - 1)

        self.setGeometry(QRect(QPoint(left, top), QPoint(right, bottom)))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            edges = self._hit_test_edges(event.pos())
            if edges:
                self._resizing = True
                self._resize_edges = edges
                self._resize_start_pos = event.globalPos()
                self._resize_start_geom = self.geometry()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizing:
            self._perform_resize(event.globalPos())
            event.accept()
            return

        self._update_resize_cursor(self._hit_test_edges(event.pos()))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._resizing = False
        self._resize_edges = set()
        self.setCursor(Qt.ArrowCursor)
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        if not self._resizing:
            self.setCursor(Qt.ArrowCursor)
        super().leaveEvent(event)

    # =========================
    # 原有 UI 初始化
    # =========================
    def disable_all_spinbox_wheels(self):
        """遍历并禁用所有 SpinBox 的滚轮事件防止误操作"""
        for spin in self.findChildren((QSpinBox, QDoubleSpinBox)):
            spin.setFocusPolicy(Qt.StrongFocus)
            spin.installEventFilter(self)

    def eventFilter(self, source, event):
        """拦截滚轮事件"""
        if event.type() == QtCore.QEvent.Wheel and isinstance(source, (QSpinBox, QDoubleSpinBox)):
            return True
        return super().eventFilter(source, event)
    
    def init_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(12, 12, 12, 12)
        outer_layout.setSpacing(0)

        self.window_frame = QFrame()
        self.window_frame.setObjectName("windowFrame")
        self.window_frame.setMouseTracking(True)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(34)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 135))
        self.window_frame.setGraphicsEffect(shadow)

        outer_layout.addWidget(self.window_frame)

        frame_layout = QVBoxLayout(self.window_frame)
        frame_layout.setContentsMargins(1, 1, 1, 1)
        frame_layout.setSpacing(0)

        self.title_bar = AeroTitleBar(self, "系统设置 / Settings")
        frame_layout.addWidget(self.title_bar)

        self.content_area = QFrame()
        self.content_area.setObjectName("contentArea")
        frame_layout.addWidget(self.content_area)

        content_layout = QVBoxLayout(self.content_area)
        content_layout.setContentsMargins(16, 14, 16, 16)
        content_layout.setSpacing(12)

        self.tabs = QTabWidget()
        self.tabs.setUsesScrollButtons(True)
        self.tabs.setDocumentMode(True)
        self.tabs.setElideMode(Qt.ElideRight)
        self.tabs.tabBar().setExpanding(False)
        self.tabs.tabBar().setDrawBase(False)
        self.tabs.tabBar().setUsesScrollButtons(True)

        builder = SettingsTabsBuilder()
        builder.create_general_tab(self)
        builder.create_data_management_tab(self)
        builder.create_interface_tab(self)
        builder.create_map_settings_tab(self)
        builder.create_mutation_settings_tab(self)
        builder.create_hotkey_tab(self)
        builder.create_general_rec_tab(self)

        content_layout.addWidget(self.tabs)

        bottom_bar = QFrame()
        bottom_bar.setObjectName("bottomBar")
        btn_layout = QHBoxLayout(bottom_bar)
        btn_layout.setContentsMargins(0, 4, 0, 0)
        btn_layout.setSpacing(10)

        save_btn = QPushButton("保存 (Save)")
        save_btn.setObjectName("accentButton")
        save_btn.clicked.connect(self.on_save)

        cancel_btn = QPushButton("取消 (Cancel)")
        cancel_btn.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)

        content_layout.addWidget(bottom_bar)

        # 关键：初始化后、切换页签后都强制刷新一次布局
        self.tabs.currentChanged.connect(
            lambda _: QtCore.QTimer.singleShot(0, self._refresh_current_tab_layout)
        )
        QtCore.QTimer.singleShot(0, self._refresh_current_tab_layout)

    def showEvent(self, event):
        super().showEvent(event)

        QtCore.QTimer.singleShot(0, self._refresh_current_tab_layout)

        if not self._first_show_layout_fixed:
            self._first_show_layout_fixed = True
            QtCore.QTimer.singleShot(0, self._finalize_first_show_layout)
            QtCore.QTimer.singleShot(30, self._finalize_first_show_layout)

    def _finalize_first_show_layout(self):
        """
        首次显示后，等待 Qt/Windows 把最终几何尺寸稳定下来，
        然后主动补一次布局刷新 + 轻微 resize 事件，避免用户手动拖一下窗口才正常。
        """
        self._refresh_current_tab_layout()

        # 取当前窗口和内容实际需要尺寸中的较大值
        hint_w = max(
            self.minimumWidth(),
            self.minimumSizeHint().width(),
            self.sizeHint().width(),
            self.width()
        )
        hint_h = max(
            self.minimumHeight(),
            self.minimumSizeHint().height(),
            self.sizeHint().height(),
            self.height()
        )

        # 给一点余量，避免边框/阴影/字体放大后刚好卡边
        target_w = max(1000, hint_w)
        target_h = max(980, hint_h + 8)

        if self.width() != target_w or self.height() != target_h:
            self.resize(target_w, target_h)

        # 关键：程序自己制造一次很小的 resize 往返，等价于“手动拖一下”
        self._force_fake_resize_event()
        self._refresh_current_tab_layout()

    def _force_fake_resize_event(self):
        """
        某些复杂页（尤其 QTableWidget 所在页）在首次 show 后，
        只有收到一次明确 resize event 才会完全铺开。
        """
        w = self.width()
        h = self.height()

        self.resize(w, h + 1)
        self.resize(w, h)

    def _refresh_current_tab_layout(self):
        """强制刷新当前页签布局，解决首次显示时表格区未正确撑开的情况"""
        if not hasattr(self, "tabs") or self.tabs is None:
            return

        current = self.tabs.currentWidget()
        if current is None:
            return

        self._activate_layout_recursively(current)

        for area in current.findChildren(QScrollArea):
            inner = area.widget()
            if inner is not None:
                self._activate_layout_recursively(inner)

        for table in current.findChildren(QTableWidget):
            table.updateGeometry()
            table.viewport().update()
            table.repaint()

        self.tabs.updateGeometry()
        self.content_area.updateGeometry()
        self.window_frame.updateGeometry()

        frame_layout = self._safe_get_qt_layout(self.window_frame)
        if frame_layout is not None:
            frame_layout.invalidate()
            frame_layout.activate()

        self.updateGeometry()
        self.repaint()

    def _safe_get_qt_layout(self, widget):
        """
        安全获取 QWidget 的 Qt layout，避免被实例属性 self.layout 覆盖后，
        直接调用 widget.layout() 触发 TypeError。
        """
        if widget is None:
            return None

        try:
            return QWidget.layout(widget)
        except Exception:
            return None

    def _activate_layout_recursively(self, widget):
        if widget is None:
            return

        layout = self._safe_get_qt_layout(widget)
        if layout is not None:
            layout.invalidate()
            layout.activate()

        widget.updateGeometry()

        for child in widget.findChildren(QWidget):
            child_layout = self._safe_get_qt_layout(child)
            if child_layout is not None:
                child_layout.invalidate()
                child_layout.activate()
            child.updateGeometry()

    def _activate_layout_recursively(self, widget):
        if widget is None:
            return

        layout = self._safe_get_qt_layout(widget)
        if layout is not None:
            layout.invalidate()
            layout.activate()

        widget.updateGeometry()

        for child in widget.findChildren(QWidget):
            child_layout = self._safe_get_qt_layout(child)
            if child_layout is not None:
                child_layout.invalidate()
                child_layout.activate()
            child.updateGeometry()

    
    def _collect_roi_data(self):
        """
        遍历存储在 self.roi_widgets 中的 QSpinBox，
        将其转换为嵌套字典格式：{lang: {region: ((x1, y1), (x2, y2))}}
        """
        nested_roi = {}
        for lang in ['zh', 'en']:
            nested_roi[lang] = {}
            if lang in self.roi_widgets:
                for region, spins in self.roi_widgets[lang].items():
                    nested_roi[lang][region] = (
                        (spins[0].value(), spins[1].value()),
                        (spins[2].value(), spins[3].value())
                    )
        return nested_roi

    def add_row(self, layout, label_text, key, widget_type, **kwargs):
        val = self.current_config.get(key)
        if val is None and widget_type != 'dict':
            self.logger.warning(f"配置项 '{key}' 未初始化，跳过显示")
            return

        widget = None
        if widget_type == 'line':
            widget = QLineEdit(str(val))
        elif widget_type == 'spin':
            widget = QSpinBox()
            widget.setRange(kwargs.get('min', 0), kwargs.get('max', 9999))
            widget.setValue(int(val))
        elif widget_type == 'double':
            widget = QDoubleSpinBox()
            widget.setRange(kwargs.get('min', 0.0), kwargs.get('max', 1.0))
            widget.setSingleStep(kwargs.get('step', 0.01))
            widget.setValue(float(val))
        elif widget_type == 'bool':
            widget = QCheckBox()
            widget.setChecked(bool(val))
        elif widget_type == 'combo':
            widget = QComboBox()
            widget.addItems(kwargs.get('items', []))
            widget.setCurrentText(str(val))
        elif widget_type == 'hotkey':
            widget = HotkeyInput()
            widget.setText(str(val))
        elif widget_type == 'color':
            widget = ColorInput(str(val))
        elif widget_type == 'dict':
            map_list = map_daos.get_all_map_names(self.data_handler.maps_db) if self.data_handler.maps_db else []
            widget = DictInput(val if isinstance(val, dict) else {}, map_list)
            self.widgets[key] = {'widget': widget, 'type': 'dict', 'label': label_text}
            layout.addRow(QLabel(label_text))
            layout.addRow(widget)
            return
        elif widget_type == 'countdown_list':
            widget = CountdownOptionsInput(val if isinstance(val, list) else [])
            self.widgets[key] = {'widget': widget, 'type': 'countdown_list', 'label': label_text}
            layout.addRow(QLabel(label_text))
            layout.addRow(widget)
            return
        elif widget_type == 'roi':
            widget = self.create_roi_widget(*val)
            self.widgets[key] = {'widget': widget['spins'], 'type': 'roi', 'label': label_text}
            layout.addRow(label_text, widget['box'])
            return
        elif widget_type == 'point':
            x, y = val
            show_btn = (key == 'MAIN_WINDOW_POS')
            widget_data = self.create_point_widget(x, y, show_get_btn=show_btn)
            self.widgets[key] = {'widget': widget_data['spins'], 'type': 'point', 'label': label_text}
            layout.addRow(label_text, widget_data['box'])
            return

        if widget:
            self.widgets[key] = {'widget': widget, 'type': widget_type, 'label': label_text}
            layout.addRow(label_text, widget)

    def create_roi_widget(self, x1, y1, x2, y2):
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)

        def spin(v):
            sb = QSpinBox()
            sb.setRange(0, 10000)
            sb.setValue(int(v))
            sb.setFixedWidth(96)
            sb.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            sb.setFocusPolicy(Qt.StrongFocus)
            sb.installEventFilter(self)
            return sb

        h.addWidget(QLabel("左上:"))
        spins = [spin(x1), spin(y1), spin(x2), spin(y2)]
        h.addWidget(spins[0])
        h.addWidget(spins[1])
        h.addSpacing(8)
        h.addWidget(QLabel("右下:"))
        h.addWidget(spins[2])
        h.addWidget(spins[3])
        h.addStretch()
        return {'box': box, 'spins': spins}
    
    def normalize_config(self, cfg: dict):
        point_map = {'MAIN_WINDOW_POS': ('MAIN_WINDOW_X', 'MAIN_WINDOW_Y')}
        for k, (xk, yk) in point_map.items():
            if k in cfg:
                x, y = cfg.pop(k)
                cfg[xk] = x
                cfg[yk] = y

    def create_point_widget(self, x, y, show_get_btn=False):
        """位置组件：增加获取当前位置按钮"""
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)

        def create_spin(v):
            sb = QSpinBox()
            sb.setRange(-10000, 10000)
            sb.setValue(int(v))
            sb.setFixedWidth(96)
            sb.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            sb.setFocusPolicy(Qt.StrongFocus)
            sb.installEventFilter(self)
            return sb

        spin_x = create_spin(x)
        spin_y = create_spin(y)

        h.addWidget(QLabel("X:"))
        h.addWidget(spin_x)
        h.addWidget(QLabel("Y:"))
        h.addWidget(spin_y)

        if show_get_btn:
            btn_get_pos = QPushButton("获取当前位置")
            btn_get_pos.setToolTip("读取主窗口当前在屏幕上的坐标")
            btn_get_pos.setMinimumHeight(32)

            def update_to_current():
                if self.main_window:
                    curr_x = self.main_window.x()
                    curr_y = self.main_window.y()
                    spin_x.setValue(curr_x)
                    spin_y.setValue(curr_y)
                else:
                    QMessageBox.warning(self, "警告", "无法获取主窗口对象")

            btn_get_pos.clicked.connect(update_to_current)
            h.addWidget(btn_get_pos)

        h.addStretch()
        return {'box': box, 'spins': [spin_x, spin_y]}

    def get_ui_values(self):
        new_values = {}
        for key, item in self.widgets.items():
            widget = item['widget']
            w_type = item['type']

            val = None
            if w_type in ('line', 'hotkey', 'color'):
                val = widget.text()
            elif w_type == 'spin':
                val = widget.value()
            elif w_type == 'double':
                val = round(widget.value(), 3)
            elif w_type == 'bool':
                val = widget.isChecked()
            elif w_type == 'combo':
                val = widget.currentText()
            elif w_type == 'roi':
                val = list(sb.value() for sb in widget)
            elif w_type == 'point':
                val = list(sb.value() for sb in widget)
            elif w_type == 'dict':
                val = widget.value()
            elif w_type == 'countdown_list':
                val = widget.value()

            new_values[key] = val
        return new_values

    def on_import_excel(self, config_type):
        """导入 Excel 配置，调用 SettingsHandler 进行验证和处理"""
        reply = QMessageBox.warning(
            self, "确认导入",
            "导入 Excel 将会【完全覆盖】并【删除】数据库中对应地图/因子的现有配置！\n"
            "建议仅在批量迁移数据时使用导入功能。\n\n是否继续？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.No:
            return

        path, _ = QFileDialog.getOpenFileName(self, "选择 Excel 文件", "", "Excel Files (*.xlsx)")
        if not path:
            return

        success, result = self.data_handler.validate_and_import(path, config_type)

        if success:
            QMessageBox.information(self, "导入成功", result)
        else:
            error_msg = "\n".join(result[:15])
            if len(result) > 15:
                error_msg += f"\n... 以及其他 {len(result) - 15} 个错误"

            QMessageBox.warning(self, "导入校验失败", f"发现数据问题，请修正：\n\n{error_msg}")

    def on_export_data(self, config_type):
        """将数据库中的配置导出为 Excel"""
        path, _ = QFileDialog.getSaveFileName(
            self, "选择保存位置", f"export_{config_type}.xlsx", "Excel Files (*.xlsx)"
        )
        if not path:
            return

        try:
            all_data = self.data_handler.get_all_configs_for_export(config_type)

            if not all_data:
                QMessageBox.warning(self, "警告", "数据库中没有找到任何可导出的数据。")
                return

            ExcelUtil.export_configs(all_data, path, config_type)
            QMessageBox.information(self, "成功", f"数据已成功导出至: {path}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导出失败: {str(e)}")

    def on_save(self):
        """保存配置：修复了数据分流顺序以及窗口驻留逻辑"""
        if self.focusWidget():
            self.focusWidget().clearFocus()

        new_values = self.get_ui_values()
        new_values['MALWARFARE_ROI'] = self._collect_roi_data()

        changes = self._generate_changes_report(new_values)

        if not changes:
            QMessageBox.information(self, "提示", "没有检测到任何修改，请修改后再保存或点击取消。")
            return

        reply = QMessageBox.question(
            self,
            "确认修改",
            "检测到以下修改，确认保存吗？\n\n" + "\n".join(changes[:10]) + ("\n..." if len(changes) > 10 else ""),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            keywords = None
            if 'MAP_SEARCH_KEYWORDS' in new_values:
                keywords = new_values.pop('MAP_SEARCH_KEYWORDS')

            self.normalize_config(new_values)

            success, msg = self.data_handler.save_all(new_values, keywords)
            if success:
                for k, v in new_values.items():
                    setattr(config, k, v)
                QMessageBox.information(self, "保存成功", msg)
                self.settings_saved.emit(new_values)
                self.accept()
            else:
                QMessageBox.critical(self, "保存失败", msg)

    def _normalize_data(self, data):
        """递归将所有元组转换为列表，确保对比基准一致"""
        if isinstance(data, tuple):
            return [self._normalize_data(i) for i in data]
        if isinstance(data, list):
            return [self._normalize_data(i) for i in data]
        if isinstance(data, dict):
            return {k: self._normalize_data(v) for k, v in data.items()}
        return data

    def _generate_changes_report(self, new_cfg):
        """对比配置变动，支持 ROI 和 关键词字典的深度详细对比"""
        from src import config
        report = []

        lang_map = {'zh': '中文', 'en': '英文'}
        region_map = {'purified_count': '净化节点', 'time': '时间', 'paused': '暂停标识'}

        for key, new_value in new_cfg.items():
            old_value = self.original_config.get(key)
            if old_value is None:
                old_value = getattr(config, key, None)

            norm_old = self._normalize_data(old_value)
            norm_new = self._normalize_data(new_value)

            if norm_old != norm_new:
                if key == 'MALWARFARE_ROI':
                    old_roi = old_value if isinstance(old_value, dict) else {}
                    new_roi = new_value if isinstance(new_value, dict) else {}
                    for lang in ['zh', 'en']:
                        o_lang = old_roi.get(lang, {})
                        n_lang = new_roi.get(lang, {})
                        for reg, label in region_map.items():
                            if self._normalize_data(o_lang.get(reg)) != self._normalize_data(n_lang.get(reg)):
                                l_name = lang_map.get(lang, lang)
                                report.append(f"【ROI-{l_name}】{label}: {o_lang.get(reg)} -> {n_lang.get(reg)}")

                elif key == 'MAP_SEARCH_KEYWORDS':
                    old_keys = norm_old.keys() if isinstance(norm_old, dict) else set()
                    new_keys = norm_new.keys() if isinstance(norm_new, dict) else set()

                    added = set(new_keys) - set(old_keys)
                    removed = set(old_keys) - set(new_keys)
                    common = set(old_keys) & set(new_keys)

                    if added:
                        report.append(f"【别名映射】新增: {list(added)}")
                    if removed:
                        report.append(f"【别名映射】删除: {list(removed)}")
                    for k in common:
                        if norm_old[k] != norm_new[k]:
                            report.append(f"【别名映射】修改 '{k}': {norm_old[k]} -> {norm_new[k]}")

                else:
                    label = self.widgets.get(key, {}).get('label', key)
                    report.append(f"【{label}】: {old_value} -> {new_value}")

        return report


if __name__ == '__main__':
    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)
    win = SettingsWindow()
    win.show()
    sys.exit(app.exec_())