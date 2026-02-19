# widgets.py
# 这个文件定义了设置界面中使用的自定义控件，如快捷键输入框和颜色选择器
from PyQt5.QtWidgets import QLineEdit, QWidget, QHBoxLayout, QPushButton, QColorDialog
from PyQt5.QtGui import QKeyEvent, QColor,QKeySequence
from PyQt5.QtCore import Qt
import re

# ==========================================
# 1. 自定义控件
# ==========================================

class HotkeyInput(QLineEdit):
    """快捷键录制控件"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("点击此处按下快捷键...")
        self.setReadOnly(True)
        self.current_keys = []
        
    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        modifiers = event.modifiers()
        if key in [Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta]:
            return
        keys = []
        if modifiers & Qt.ControlModifier: keys.append('ctrl')
        if modifiers & Qt.ShiftModifier: keys.append('shift')
        if modifiers & Qt.AltModifier: keys.append('alt')
        
        key_text = QKeySequence(key).toString().lower()
        # 特殊符号映射
        key_map = {
            Qt.Key_BracketLeft: '[', Qt.Key_BracketRight: ']', 
            Qt.Key_Backslash: '\\', Qt.Key_Minus: '-', 
            Qt.Key_Equal: '=', Qt.Key_QuoteLeft: '`'
        }
        if key in key_map:
            key_text = key_map[key]

        keys.append(key_text)
        self.setText(" + ".join(keys))

class ColorInput(QWidget):
    """颜色选择控件 (文本框 + 选择按钮)"""
    def __init__(self, color_str, parent=None):
        super().__init__(parent)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0,0,0,0)
        self.line = QLineEdit(str(color_str))
        self.btn = QPushButton("选择")
        self.btn.setFixedWidth(50)
        self.btn.clicked.connect(self.pick_color)
        self.layout.addWidget(self.line)
        self.layout.addWidget(self.btn)
        self.update_btn_style()
        self.line.textChanged.connect(self.update_btn_style)

    def pick_color(self):
        c = self.parse_color(self.line.text())
        new_c = QColorDialog.getColor(c, self, "选择颜色", QColorDialog.ShowAlphaChannel)
        if new_c.isValid():
            if new_c.alpha() == 255:
                s = f"rgb({new_c.red()}, {new_c.green()}, {new_c.blue()})"
            else:
                s = f"rgba({new_c.red()}, {new_c.green()}, {new_c.blue()}, {new_c.alpha()})"
            self.line.setText(s)

    def parse_color(self, s):
        m = re.match(r'rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*(\d+))?\)', s)
        if m:
            r, g, b = map(int, m.groups()[:3])
            a = int(m.group(4)) if m.group(4) else 255
            return QColor(r, g, b, a)
        return QColor(s) if QColor(s).isValid() else QColor(255, 255, 255)

    def update_btn_style(self):
        c = self.parse_color(self.line.text())
        if c.isValid():
             # 使用 border 使得白色也能看清
             self.btn.setStyleSheet(f"background-color: {c.name(QColor.HexArgb)}; border: 1px solid gray;")
    
    def text(self):
        return self.line.text()
      

