import json
import os
import copy
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, 
                             QLabel, QLineEdit, QSpinBox, QDoubleSpinBox, 
                             QCheckBox, QPushButton, QColorDialog, QMessageBox, 
                             QFormLayout, QScrollArea, QDialog, QComboBox)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QKeyEvent

import config  # 导入你现有的 config.py 作为默认值

# ==========================================
# 1. 自定义快捷键录制控件
# ==========================================
class HotkeyInput(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("点击此处按下快捷键...")
        self.setReadOnly(True)  # 防止用户手动输入文本
        self.current_keys = []

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        modifiers = event.modifiers()

        # 忽略单纯的修饰键按下
        if key in [Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta]:
            return

        # 构建快捷键字符串 (适配 keyboard 库的格式)
        keys = []
        if modifiers & Qt.ControlModifier:
            keys.append('ctrl')
        if modifiers & Qt.ShiftModifier:
            keys.append('shift')
        if modifiers & Qt.AltModifier:
            keys.append('alt')
        
        # 处理普通按键映射
        key_text =  QKeySequence(key).toString().lower()
        
        # 特殊符号处理 (根据需要扩展)
        if key == Qt.Key_BracketLeft: key_text = '['
        elif key == Qt.Key_BracketRight: key_text = ']'
        elif key == Qt.Key_Backslash: key_text = '\\'
        elif key == Qt.Key_Minus: key_text = '-'
        elif key == Qt.Key_Equal: key_text = '='
        elif key == Qt.Key_QuoteLeft: key_text = '`'

        keys.append(key_text)
        
        final_hotkey = " + ".join(keys)
        self.setText(final_hotkey)

from PyQt5.QtGui import QKeySequence # 补充导入

# ==========================================
# 2. 设置窗口主类
# ==========================================
class SettingsWindow(QDialog):
    # 定义一个信号，当配置保存后触发，传递新的配置字典
    settings_saved = pyqtSignal(dict)

    def __init__(self,parent = None):
        super().__init__(parent)
        self.setWindowTitle("系统设置 / Settings")
        self.resize(800, 600)
        self.settings_file = 'settings.json'
        
        # 加载初始配置
        self.current_config = self.load_config()
        self.original_config = copy.deepcopy(self.current_config) # 用于比对修改
        
        # 控件字典，用于后续获取值 {key_name: widget}
        self.widgets = {}

        self.init_ui()

    def load_config(self):
        """加载配置：优先读取 json，没有则使用 config.py 的值"""
        cfg = {}
        # 从 config.py 读取所有全大写或特定变量作为默认值
        # 这里为了演示，我手动映射关键字段，实际项目中可以遍历 dir(config)
        
        # === 默认值映射 (从 config.py 获取) ===
        default_cfg = {
            # 常规
            'current_region': getattr(config, 'current_region', 'kr'),
            'current_language': getattr(config, 'current_language', 'zh'),
            'LOG_LEVEL': getattr(config, 'LOG_LEVEL', 'WARNING'),
            'debug_mode': getattr(config, 'debug_mode', False),
            
            # 快捷键
            'MAP_SHORTCUT': getattr(config, 'MAP_SHORTCUT', ''),
            'LOCK_SHORTCUT': getattr(config, 'LOCK_SHORTCUT', ''),
            'SCREENSHOT_SHORTCUT': getattr(config, 'SCREENSHOT_SHORTCUT', ''),
            'MEMO_TEMP_SHORTCUT': getattr(config, 'MEMO_TEMP_SHORTCUT', ''),
            'MEMO_TOGGLE_SHORTCUT': getattr(config, 'MEMO_TOGGLE_SHORTCUT', ''),

            # 界面
            'TOAST_DURATION': getattr(config, 'TOAST_DURATION', 10000),
            'MAIN_WINDOW_BG_COLOR': getattr(config, 'MAIN_WINDOW_BG_COLOR', 'rgba(43, 43, 43, 200)'),
            'TABLE_FONT_SIZE': getattr(config, 'TABLE_FONT_SIZE', 12),

            # 游戏提醒
            'MAP_ALERT_SECONDS': getattr(config, 'MAP_ALERT_SECONDS', 30),
            'MEMO_OPACITY': getattr(config, 'MEMO_OPACITY', 1.0),
            
            # 图像识别 (示例部分)
            'GAME_SCREEN_DPI': getattr(config, 'GAME_SCREEN_DPI', 96),
            'GAME_ICO_RECONGIZE_CONFIDENCE': getattr(config, 'GAME_ICO_RECONGIZE_CONFIDENCE', 0.9),
            'DEBUG_SHOW_ENEMY_INFO_SQUARE': getattr(config, 'DEBUG_SHOW_ENEMY_INFO_SQUARE', False)
        }

        # 尝试读取 JSON 覆盖默认值
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    user_cfg = json.load(f)
                    default_cfg.update(user_cfg) # 更新
            except Exception as e:
                print(f"读取设置文件失败: {e}")
        
        return default_cfg

    def init_ui(self):
        main_layout = QVBoxLayout()
        self.tabs = QTabWidget()
        
        # === 创建分页 ===
        self.create_general_tab()   # 1. 常规设置
        self.create_interface_tab() # 2. 界面与显示
        self.create_alert_tab()     # 3. 游戏提醒
        self.create_hotkey_tab()    # 4. 快捷键
        self.create_image_rec_tab() # 5. 图像识别

        main_layout.addWidget(self.tabs)

        # === 底部按钮 ===
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("保存 (Save)")
        save_btn.clicked.connect(self.on_save)
        cancel_btn = QPushButton("取消 (Cancel)")
        cancel_btn.clicked.connect(self.reject)
        
        # 样式美化
        save_btn.setStyleSheet("background-color: #4CAF50; color: white; padding: 8px;")
        cancel_btn.setStyleSheet("padding: 8px;")

        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        
        main_layout.addLayout(btn_layout)
        self.setLayout(main_layout)

    # 辅助函数：添加一行设置
    def add_row(self, layout, label_text, key, widget_type, **kwargs):
        """
        layout: QFormLayout
        label_text: 中文显示名称
        key: config 中的变量名
        widget_type: 'line', 'spin', 'double', 'bool', 'combo', 'color', 'hotkey'
        """
        val = self.current_config.get(key)
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
            widget.setSingleStep(0.1)
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
        
        # 记录控件，以便获取值
        if widget:
            self.widgets[key] = {'widget': widget, 'type': widget_type, 'label': label_text}
            layout.addRow(label_text, widget)

    # ---------------- 分页构建 ----------------

    def create_general_tab(self):
        tab = QWidget()
        layout = QFormLayout()
        
        self.add_row(layout, "当前地区 (Region):", 'current_region', 'combo', items=['kr', 'cn', 'tw', 'us'])
        self.add_row(layout, "语言 (Language):", 'current_language', 'combo', items=['zh', 'en'])
        self.add_row(layout, "日志等级 (Log Level):", 'LOG_LEVEL', 'combo', items=['DEBUG', 'INFO', 'WARNING', 'ERROR'])
        self.add_row(layout, "调试模式 (Debug Mode):", 'debug_mode', 'bool')
        
        tab.setLayout(layout)
        self.tabs.addTab(tab, "常规设置")

    def create_interface_tab(self):
        tab = QWidget()
        layout = QFormLayout()
        
        self.add_row(layout, "Toast 显示时长 (ms):", 'TOAST_DURATION', 'spin', max=60000)
        self.add_row(layout, "主界面背景颜色 (RGBA):", 'MAIN_WINDOW_BG_COLOR', 'line') # 可以改造成颜色选择器
        self.add_row(layout, "表格字体大小:", 'TABLE_FONT_SIZE', 'spin', min=8, max=72)
        
        tab.setLayout(layout)
        self.tabs.addTab(tab, "界面与显示")

    def create_alert_tab(self):
        tab = QWidget()
        layout = QFormLayout()
        
        self.add_row(layout, "地图提前提醒 (秒):", 'MAP_ALERT_SECONDS', 'spin')
        self.add_row(layout, "笔记透明度 (0-1):", 'MEMO_OPACITY', 'double')
        
        tab.setLayout(layout)
        self.tabs.addTab(tab, "游戏提醒")

    def create_hotkey_tab(self):
        tab = QWidget()
        layout = QFormLayout()
        
        self.add_row(layout, "地图切换快捷键:", 'MAP_SHORTCUT', 'hotkey')
        self.add_row(layout, "锁定窗口快捷键:", 'LOCK_SHORTCUT', 'hotkey')
        self.add_row(layout, "截图快捷键:", 'SCREENSHOT_SHORTCUT', 'hotkey')
        self.add_row(layout, "笔记临时显示:", 'MEMO_TEMP_SHORTCUT', 'hotkey')
        self.add_row(layout, "笔记开关显示:", 'MEMO_TOGGLE_SHORTCUT', 'hotkey')

        tab.setLayout(layout)
        self.tabs.addTab(tab, "快捷键")

    def create_image_rec_tab(self):
        # 图像识别项非常多，使用滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content_widget = QWidget()
        layout = QFormLayout()
        
        layout.addRow(QLabel("<b>[ 高级设置 ] 修改此处可能导致识别失效</b>"))
        
        self.add_row(layout, "屏幕 DPI (96/120/144...):", 'GAME_SCREEN_DPI', 'spin', max=500)
        self.add_row(layout, "图标识别置信度 (0.1-1.0):", 'GAME_ICO_RECONGIZE_CONFIDENCE', 'double')
        self.add_row(layout, "显示敌方信息调试框:", 'DEBUG_SHOW_ENEMY_INFO_SQUARE', 'bool')
        
        # 这里可以继续添加所有的坐标配置，建议只开放常用微调项
        
        content_widget.setLayout(layout)
        scroll.setWidget(content_widget)
        self.tabs.addTab(scroll, "图像识别")

    # ---------------- 逻辑处理 ----------------

    def get_ui_values(self):
        """从控件中读取当前值"""
        new_values = {}
        for key, item in self.widgets.items():
            widget = item['widget']
            w_type = item['type']
            
            val = None
            if w_type == 'line' or w_type == 'hotkey':
                val = widget.text()
            elif w_type == 'spin':
                val = widget.value()
            elif w_type == 'double':
                val = round(widget.value(), 2)
            elif w_type == 'bool':
                val = widget.isChecked()
            elif w_type == 'combo':
                val = widget.currentText()
            
            new_values[key] = val
        return new_values

    def on_save(self):
        new_config = self.get_ui_values()
        changes = []
        
        # 比对差异
        for key, new_val in new_config.items():
            old_val = self.original_config.get(key)
            # 注意类型转换导致的虚假差异 (例如 '30' vs 30)
            if str(new_val) != str(old_val):
                label = self.widgets[key]['label']
                changes.append(f"【{label}】\n   原值: {old_val}  ->  新值: {new_val}")
        
        if not changes:
            QMessageBox.information(self, "提示", "没有检测到任何修改。")
            self.accept() 
            return

        # 弹出确认框
        confirm_text = "检测到以下修改，确认保存吗？\n\n" + "\n".join(changes)
        reply = QMessageBox.question(self, "确认修改", confirm_text, 
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            self.save_to_json(new_config)
            self.settings_saved.emit(new_config) # 发送信号通知主窗口更新
            self.original_config = copy.deepcopy(new_config) # 更新基准值
            self.accept()

    def save_to_json(self, config_data):
        try:
            # 写入 settings.json
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=4, ensure_ascii=False)
            
            QMessageBox.information(self, "成功", "设置已保存！\n部分设置可能需要重启程序才能生效。")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存失败: {str(e)}")

# 独立运行测试
if __name__ == '__main__':
    import sys
    app = QApplication(sys.argv)
    win = SettingsWindow()
    win.show()
    sys.exit(app.exec_())