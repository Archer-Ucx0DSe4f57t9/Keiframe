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
    QFrame, QProxyStyle, QStyle, QApplication
)
from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QRect, QSize
from PyQt5.QtGui import QKeyEvent, QColor, QKeySequence, QPainter

from src import config
from src.utils.logging_util import get_logger
from src.utils.fileutil import get_resources_dir, get_project_root
from src.utils.excel_utils import ExcelUtil
from src.utils.data_validator import DataValidator
from src.db import map_daos, mutator_daos
from src.settings_window.widgets import (
    HotkeyInput, ColorInput,
    ThemedComboBox, ThemedSpinBox, ThemedDoubleSpinBox
)
from src.settings_window.title_bar import AeroTitleBar
from src.settings_window.theme import build_settings_qss
from src.settings_window.dpi_scaling import (
    get_settings_window_dpi_scale,
    scale_px,
    scale_qss_px,
)
from src.settings_window.complex_inputs import DictInput, DictTable, CountdownOptionsInput
from src.settings_window.tabs import SettingsTabsBuilder
from src.settings_window.setting_data_handler import SettingsHandler

class SwitchButton(QCheckBox):
    """iPhone 风格细长开关"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setText("")
        self.setFixedSize(46, 24)

    def sizeHint(self):
        return QSize(46, 24)
    
    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        checked = self.isChecked()

        track_rect = self.rect().adjusted(1, 1, -1, -1)
        radius = track_rect.height() / 2

        knob_margin = max(2, round(self.height() * 0.125))
        knob_size = max(1, self.height() - knob_margin * 2)

        if checked:
            track_color = QColor(52, 199, 89)      # iOS 绿色
            border_color = QColor(52, 199, 89)
            knob_x = self.width() - knob_size - knob_margin
        else:
            track_color = QColor(74, 74, 74)
            border_color = QColor(105, 105, 105)
            knob_x = knob_margin

        painter.setPen(border_color)
        painter.setBrush(track_color)
        painter.drawRoundedRect(track_rect, radius, radius)

        knob_rect = QRect(knob_x, knob_margin, knob_size, knob_size)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(245, 245, 245))
        painter.drawEllipse(knob_rect)


class SettingsWindow(QDialog):
    settings_saved = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Dialog | Qt.FramelessWindowHint)
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
        self._dpi, self._dpi_scale = get_settings_window_dpi_scale(parent)

        # 无边框 / Alpha 透明顶层窗口 / 自定义缩放参数
        self._resize_margin = self._px(8)
        self._resizing = False
        self._resize_edges = set()
        self._resize_start_pos = QPoint()
        self._resize_start_geom = QRect()

        self._setup_window_shell()

        self.setWindowTitle("系统设置 / Settings")
        initial_w, initial_h = self._fit_size_to_available_screen(self._px(1000), self._px(980))
        min_w, min_h = self._fit_size_to_available_screen(self._px(920), self._px(820))
        self.resize(initial_w, initial_h)
        self.setMinimumSize(min_w, min_h)
        self._center_on_available_screen()

        self._settings_open_logged = False

        self.init_ui()
        self.apply_dark_theme()
        self.disable_all_spinbox_wheels()

    # =========================
    # 窗口外壳
    # =========================
    def _px(self, value):
        return scale_px(value, self._dpi_scale)

    def _target_screen(self):
        if self.main_window is not None:
            try:
                center = self.main_window.frameGeometry().center()
                screen = QApplication.screenAt(center)
                if screen is not None:
                    return screen
            except Exception:
                pass

            try:
                screen = self.main_window.screen()
                if screen is not None:
                    return screen
            except Exception:
                pass

        return self.screen() or QApplication.primaryScreen()

    def _available_geometry(self):
        screen = self._target_screen()
        return screen.availableGeometry() if screen is not None else None

    def _fit_size_to_available_screen(self, width, height):
        available = self._available_geometry()
        if available is None:
            return width, height

        max_w = max(1, available.width())
        max_h = max(1, available.height())
        return min(width, max_w), min(height, max_h)

    def _clamp_to_available_screen(self):
        available = self._available_geometry()
        if available is None:
            return

        target_w = min(self.width(), available.width())
        target_h = min(self.height(), available.height())
        if self.width() != target_w or self.height() != target_h:
            self.resize(target_w, target_h)

        self._clamp_position_to_available_screen()

    def _clamp_position_to_available_screen(self):
        available = self._available_geometry()
        if available is None:
            return

        max_x = available.right() - self.width() + 1
        max_y = available.bottom() - self.height() + 1
        x = min(max(self.x(), available.left()), max_x)
        y = min(max(self.y(), available.top()), max_y)
        self.move(x, y)

    def _center_on_available_screen(self):
        available = self._available_geometry()
        if available is None:
            return

        x = available.left() + (available.width() - self.width()) // 2
        y = available.top() + (available.height() - self.height()) // 2
        self.move(x, y)
        self._clamp_to_available_screen()


    def _setup_window_shell(self):
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.setMouseTracking(True)

    def apply_dark_theme(self):
        self.setStyleSheet(scale_qss_px(build_settings_qss(font_px=12), self._dpi_scale))

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
        outer_layout.setContentsMargins(self._px(12), self._px(12), self._px(12), self._px(12))
        outer_layout.setSpacing(0)

        self.window_frame = QFrame()
        self.window_frame.setObjectName("windowFrame")
        self.window_frame.setAttribute(Qt.WA_StyledBackground, True)
        self.window_frame.setAutoFillBackground(False)
        self.window_frame.setMouseTracking(True)

        outer_layout.addWidget(self.window_frame)

        frame_layout = QVBoxLayout(self.window_frame)
        frame_layout.setContentsMargins(self._px(1), self._px(1), self._px(1), self._px(1))
        frame_layout.setSpacing(0)

        self.title_bar = AeroTitleBar(self, "系统设置 / Settings")
        if hasattr(self.title_bar, "apply_dpi_scale"):
            self.title_bar.apply_dpi_scale(self._dpi_scale)
        frame_layout.addWidget(self.title_bar)

        self.content_area = QFrame()
        self.content_area.setObjectName("contentArea")
        frame_layout.addWidget(self.content_area)

        content_layout = QVBoxLayout(self.content_area)
        content_layout.setContentsMargins(self._px(16), self._px(14), self._px(16), self._px(16))
        content_layout.setSpacing(self._px(12))

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
        builder.create_auto_alert_tab(self)
        builder.create_map_settings_tab(self)
        builder.create_mutation_settings_tab(self)
        builder.create_hotkey_tab(self)
        builder.create_general_rec_tab(self)

        content_layout.addWidget(self.tabs)

        bottom_bar = QFrame()
        bottom_bar.setObjectName("bottomBar")
        btn_layout = QHBoxLayout(bottom_bar)
        btn_layout.setContentsMargins(0, self._px(4), 0, 0)
        btn_layout.setSpacing(self._px(10))

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
        self._clamp_position_to_available_screen()
        QtCore.QTimer.singleShot(0, self._finish_initial_show_layout)

    def _finish_initial_show_layout(self):
        """首次显示后只做一次延迟布局刷新，避免同步重绘顶层窗口。"""
        self._refresh_current_tab_layout()
        self._clamp_position_to_available_screen()
        self._log_settings_open_geometry()

    def _refresh_current_tab_layout(self):
        """刷新当前页签布局，保证首次打开时表格和滚动区域正确显示。"""
        if not hasattr(self, "tabs") or self.tabs is None:
            return

        current = self.tabs.currentWidget()
        if current is None:
            return

        widgets_to_refresh = [current]

        for area in current.findChildren(QScrollArea):
            widgets_to_refresh.append(area)
            inner = area.widget()
            if inner is not None:
                widgets_to_refresh.append(inner)

        widgets_to_refresh.extend([self.tabs, self.content_area, self.window_frame])

        seen = set()
        for widget in widgets_to_refresh:
            if widget is None or id(widget) in seen:
                continue
            seen.add(id(widget))

            layout = self._safe_get_qt_layout(widget)
            if layout is not None:
                layout.invalidate()
                layout.activate()

            widget.updateGeometry()
            widget.update()

        for table in current.findChildren(QTableWidget):
            table.updateGeometry()
            table.viewport().update()
            table.update()

        self.updateGeometry()
        self.update()

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

    def _rect_to_tuple(self, rect):
        return (rect.x(), rect.y(), rect.width(), rect.height())

    def _log_settings_open_geometry(self):
        """打开设置窗口时记录一次 DPI 和几何信息，便于排查定位问题。"""
        if self._settings_open_logged:
            return

        self._settings_open_logged = True
        screen = self._target_screen()
        screen_name = screen.name() if screen is not None else "unknown"
        available = screen.availableGeometry() if screen is not None else QRect()
        title_geom = self.title_bar.geometry() if hasattr(self, "title_bar") else QRect()
        title_visible = self.title_bar.isVisible() if hasattr(self, "title_bar") else False

        self.logger.info(
            "设置窗口 DPI=%s scale=%.2f screen=%s available=%s geometry=%s "
            "title_bar=%s title_visible=%s",
            self._dpi,
            self._dpi_scale,
            screen_name,
            self._rect_to_tuple(available),
            self._rect_to_tuple(self.geometry()),
            self._rect_to_tuple(title_geom),
            title_visible,
        )

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

    def _format_tuple_line_value(self, key, val):
        """用于把 tuple/list/set 显示成 100,150 这种用户友好的格式。"""
        if key == 'SUPPLY_EXCLUDED_MAX_VALUES':
            if isinstance(val, (tuple, list, set)):
                return ",".join(str(int(v)) for v in val)
        return str(val)


    def _parse_tuple_line_value(self, key, text):
        """用于把 100,150 / (100, 150) / [100, 150] 转回 tuple，避免保存时类型变化。"""
        if key == 'SUPPLY_EXCLUDED_MAX_VALUES':
            text = str(text).strip()
            if not text:
                return tuple()

            # 兼容:
            # 100,150
            # (100, 150)
            # [100, 150]
            # 100 150
            nums = re.findall(r"-?\d+", text)
            return tuple(int(n) for n in nums)

        return text
        
    def add_row(self, layout, label_text, key, widget_type, **kwargs):
        val = self.current_config.get(key)
        if val is None and widget_type != 'dict':
            self.logger.warning(f"配置项 '{key}' 未初始化，跳过显示")
            return

        widget = None
        if widget_type == 'line':
            widget = QLineEdit(self._format_tuple_line_value(key, val))
        elif widget_type == 'spin':
            widget = ThemedSpinBox()
            widget.setRange(kwargs.get('min', 0), kwargs.get('max', 9999))
            widget.setValue(int(val))
        elif widget_type == 'double':
            widget = ThemedDoubleSpinBox()
            widget.setRange(kwargs.get('min', 0.0), kwargs.get('max', 1.0))
            widget.setSingleStep(kwargs.get('step', 0.01))
            widget.setValue(float(val))
        elif widget_type == 'bool':
            widget = QCheckBox()
            widget.setChecked(bool(val))
        elif widget_type == 'switch':
            widget_data = self.create_switch_widget(bool(val))
            self.widgets[key] = {
                'widget': widget_data['button'],
                'type': 'switch',
                'label': label_text
            }
            layout.addRow(label_text, widget_data['box'])
            return
        elif widget_type == 'combo':
            widget = QComboBox()
            combo_items = kwargs.get('items', [])
            current_val = val

            for item in combo_items:
                # 支持 [(显示文本, 保存值), ...]
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    display_text = str(item[0])
                    data_value = item[1]
                    widget.addItem(display_text, data_value)
                else:
                    # 兼容旧写法：["zh", "en"] 这种
                    text = str(item)
                    widget.addItem(text, text)

            # 优先按 data 匹配当前配置值
            idx = widget.findData(current_val)
            if idx < 0:
                idx = widget.findText(str(current_val))
            if idx >= 0:
                widget.setCurrentIndex(idx)
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
            sb = ThemedSpinBox()
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
            sb = ThemedSpinBox()
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

    def create_switch_widget(self, checked: bool):
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)

        switch = SwitchButton()
        switch.setChecked(bool(checked))

        status = QLabel()
        status.setMinimumWidth(58)

        def refresh():
            if switch.isChecked():
                status.setText("已启用")
                status.setStyleSheet("color: rgb(100, 255, 150); font-weight: bold;")
            else:
                status.setText("已关闭")
                status.setStyleSheet("color: rgb(160, 160, 160); font-weight: bold;")

        switch.toggled.connect(refresh)
        refresh()

        h.addWidget(switch)
        h.addWidget(status)
        h.addStretch()

        return {
            "box": box,
            "button": switch,
            "status": status,
        }

    def get_ui_values(self):
        new_values = {}
        for key, item in self.widgets.items():
            widget = item['widget']
            w_type = item['type']

            val = None
            if w_type in ('line', 'hotkey', 'color'):
                val = widget.text()
                if w_type == 'line':
                    val = self._parse_tuple_line_value(key, val)
            elif w_type == 'spin':
                val = widget.value()
            elif w_type == 'double':
                val = round(widget.value(), 3)
            elif w_type == 'bool':
                val = widget.isChecked()
            elif w_type == 'switch':
                val = widget.isChecked()
            elif w_type == 'combo':
                data_val = widget.currentData()
                val = data_val if data_val is not None else widget.currentText()
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
    
    

