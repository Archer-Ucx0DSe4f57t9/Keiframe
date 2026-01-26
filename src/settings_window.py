import json
import os, sys
import copy
import re
from PyQt5 import QtCore 
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, 
                             QLabel, QLineEdit, QSpinBox, QDoubleSpinBox, 
                             QCheckBox, QPushButton, QColorDialog, QMessageBox, 
                             QFormLayout, QScrollArea, QDialog, QComboBox, QGroupBox,
                             QTableWidget, QTableWidgetItem, QHeaderView)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QKeyEvent, QColor, QKeySequence

from src import config  # 导入你现有的 config.py 作为默认值
from src.logging_util import get_logger
from src.fileutil import get_resources_dir, get_project_root

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

class DictTable(QTableWidget):
    """字典编辑器表格 - 第二列改为下拉选择"""
    def __init__(self, data_dict, map_list, parent=None):
        super().__init__(0, 2, parent)
        self.map_list = map_list # 外部传入的地图全名列表
        self.setHorizontalHeaderLabels(["简写关键词 (Key)", "地图全名 (Value)"])
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.setMinimumHeight(150)
        
         # 连接点击事件到编辑
        self.cellClicked.connect(self.on_click_to_edit)
        
        row = 0
        for k, v in data_dict.items():
            self.add_new_row(str(k), str(v))
            row += 1

    def on_click_to_edit(self, row, col):
        """单击单元格时，如果是第一列（关键词），立即进入编辑模式"""
        if col == 0:
            self.edit(self.model().index(row, col))
    
    def add_new_row(self, key_text="", value_text=""):
        """添加一行，并为第二列设置下拉框"""
        row = self.rowCount()
        self.insertRow(row)
        
        # 第一列：手动输入关键词
        self.setItem(row, 0, QTableWidgetItem(key_text))
        
        # 第二列：下拉选择地图全名
        combo = QComboBox()
        combo.addItems(self.map_list)
        if value_text in self.map_list:
            combo.setCurrentText(value_text)
        elif self.map_list:
            combo.setCurrentIndex(0)
            
        self.setCellWidget(row, 1, combo)

    def get_data(self):
        data = {}
        for r in range(self.rowCount()):
            k_item = self.item(r, 0)
            v_widget = self.cellWidget(r, 1) # 获取下拉框控件
            if k_item and isinstance(v_widget, QComboBox):
                k = k_item.text().strip()
                v = v_widget.currentText()
                if k and v:
                    data[k] = v
        return data

class DictInput(QWidget):
    """字典编辑器容器"""
    def __init__(self, data_dict, map_list, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0,0,0,0)
        
        self.table = DictTable(data_dict, map_list) # 传入地图列表
        
        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton("添加行")
        self.del_btn = QPushButton("删除选中行")
        self.add_btn.clicked.connect(lambda: self.table.add_new_row())
        self.del_btn.clicked.connect(self.del_row)
        
        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.del_btn)
        
        self.layout.addWidget(self.table)
        self.layout.addLayout(btn_layout)

    def add_row(self):
        self.table.insertRow(self.table.rowCount())
    
    def del_row(self):
        r = self.table.currentRow()
        if r >= 0:
            self.table.removeRow(r)
    
    def value(self):
        return self.table.get_data()

class CountdownOptionsTable(QTableWidget):
    """倒计时选项编辑器"""
    def __init__(self, options_list, parent=None):
        super().__init__(0, 3, parent) # 3列: 时间, 名称, 声音
        self.setHorizontalHeaderLabels(["秒数 (Time)", "名称 (Label)", "声音文件 (Sound)"])
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.setMinimumHeight(180)
        
        # 连接点击事件到编辑
        self.cellClicked.connect(self.on_click_to_edit)
        
        # 预先获取声音列表，避免重复IO
        self.sound_files = self.get_sound_files()
        
        for opt in options_list:
            t = opt.get('time', 60)
            l = opt.get('label', '')
            s = opt.get('sound', '')
            self.add_new_row(t, l, s)

    def on_click_to_edit(self, row, col):
        """单击单元格时，如果是第二列（名称），立即进入编辑模式"""
        # Column 1 是名称 (Label), Column 0 和 2 分别是 SpinBox 和 ComboBox，本身就需要点击操作
        if col == 1:
            self.edit(self.model().index(row, col))
  
    def add_new_row(self, time_val=60, label_text="倒计时", sound_text=""):
        row = self.rowCount()
        self.insertRow(row)
        
        # 1. 时间 (SpinBox)
        sb = QSpinBox()
        sb.setRange(1, 9999)
        sb.setValue(int(time_val))
        self.setCellWidget(row, 0, sb)
        
        # 2. 名称 (普通 Item，允许直接打字编辑)
        self.setItem(row, 1, QTableWidgetItem(str(label_text)))
        
        # 3. 声音 (下拉框)
        combo = QComboBox()
        # 添加一个空选项，代表无声音
        combo.addItem("")
        combo.addItems(self.sound_files)
        
        # 尝试选中已有的声音文件
        idx = combo.findText(sound_text)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        else:
            # 如果配置文件里有，但文件夹里没有，依然添加进去显示，防止配置丢失
            if sound_text:
                combo.addItem(sound_text)
                combo.setCurrentText(sound_text)
                
        self.setCellWidget(row, 2, combo)

    def get_data(self):
        data = []
        for r in range(self.rowCount()):
            sb = self.cellWidget(r, 0)
            label_item = self.item(r, 1)
            combo = self.cellWidget(r, 2)
            
            if sb and label_item and combo:
                entry = {
                    'time': sb.value(),
                    'label': label_item.text().strip(),
                    'sound': combo.currentText().strip()
                }
                data.append(entry)
        return data
      
    def get_sound_files(self):
        """获取 resources/sounds 目录下的所有声音文件名列表"""        
        sound_dir = get_resources_dir('sounds')
        files = []
        
        if os.path.exists(sound_dir):
            try:
                for f in os.listdir(sound_dir):
                    if os.path.isfile(os.path.join(sound_dir, f)):
                        files.append(f)
            except Exception:
                pass
        # 返回排序后的文件列表，方便查找
        return sorted(files)

class CountdownOptionsInput(QWidget):
    def __init__(self, options_list, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0,0,0,0)
        
        self.table = CountdownOptionsTable(options_list)
        
        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton("添加倒计时")
        self.del_btn = QPushButton("删除选中")
        self.add_btn.clicked.connect(lambda: self.table.add_new_row())
        self.del_btn.clicked.connect(self.del_row)
        
        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.del_btn)
        
        self.layout.addWidget(self.table)
        self.layout.addLayout(btn_layout)

    def del_row(self):
        r = self.table.currentRow()
        if r >= 0:
            self.table.removeRow(r)

    def value(self):
        return self.table.get_data()
      
      
# ==========================================
# 2. 设置窗口主类
# ==========================================
class SettingsWindow(QDialog):
    settings_saved = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.setWindowTitle("系统设置 / Settings")
        self.resize(900, 700)
        self.settings_file = os.path.join(get_project_root(), 'settings.json')
        self.logger = get_logger("setting window")
        
        self.current_config = self.load_config()
        self.original_config = copy.deepcopy(self.current_config)
        self.widgets = {}

        self.init_ui()
        self.disable_all_spinbox_wheels()

    def disable_all_spinbox_wheels(self):
        """遍历并禁用所有 SpinBox 的滚轮事件防止误操作"""
        for spin in self.findChildren((QSpinBox, QDoubleSpinBox)):
            spin.setFocusPolicy(Qt.StrongFocus) # 只有点击后才能输入
            spin.installEventFilter(self) # 安装过滤器
    
    def eventFilter(self, source, event):
        """拦截滚轮事件"""
        if event.type() == QtCore.QEvent.Wheel and isinstance(source, (QSpinBox, QDoubleSpinBox)):
            return True # 拦截事件，不向下传递
        return super().eventFilter(source, event)
            
    def load_config(self):
        """加载配置"""
        default_cfg = {
            # ===== 常规 =====
            'current_language': getattr(config, 'current_language', 'zh'),
            'LOG_LEVEL': getattr(config, 'LOG_LEVEL', 'WARNING'),
            'debug_mode': getattr(config, 'debug_mode', False),
            'debug_time_factor': getattr(config, 'debug_time_factor', 5.0),

            # ===== 快捷键 =====
            'MAP_SHORTCUT': getattr(config, 'MAP_SHORTCUT', ''),
            'LOCK_SHORTCUT': getattr(config, 'LOCK_SHORTCUT', ''),
            'SCREENSHOT_SHORTCUT': getattr(config, 'SCREENSHOT_SHORTCUT', ''),
            'MEMO_TEMP_SHORTCUT': getattr(config, 'MEMO_TEMP_SHORTCUT', ''),
            'MEMO_TOGGLE_SHORTCUT': getattr(config, 'MEMO_TOGGLE_SHORTCUT', ''),
            'COUNTDOWN_SHORTCUT': getattr(config, 'COUNTDOWN_SHORTCUT', ''),

            # ===== 主窗口与界面 =====
            'MAIN_WINDOW_POS': (getattr(config, 'MAIN_WINDOW_X', 1000), getattr(config, 'MAIN_WINDOW_Y', 100)),
            'MAIN_WINDOW_WIDTH': getattr(config, 'MAIN_WINDOW_WIDTH', 200),
            'MAIN_WINDOW_BG_COLOR': getattr(config, 'MAIN_WINDOW_BG_COLOR', 'rgba(43, 43, 43, 200)'),
            'TABLE_FONT_SIZE': getattr(config, 'TABLE_FONT_SIZE', 12),
            'TABLE_HEIGHT': getattr(config, 'TABLE_HEIGHT', 150),

            # ===== 地图事件配置 =====
            'MAP_ALERT_SECONDS': getattr(config, 'MAP_ALERT_SECONDS', 30),
            'MAP_ALERT_WARNING_THRESHOLD_SECONDS': getattr(config, 'MAP_ALERT_WARNING_THRESHOLD_SECONDS', 10),
            'MAP_ALERT_NORMAL_COLOR': getattr(config, 'MAP_ALERT_NORMAL_COLOR', 'rgb(239, 255, 238)'),
            'MAP_ALERT_WARNING_COLOR': getattr(config, 'MAP_ALERT_WARNING_COLOR', 'rgb(255, 0, 0)'),
            'TOAST_OFFSET_X': getattr(config, 'TOAST_OFFSET_X', 19),
            'TOAST_OFFSET_Y': getattr(config, 'TOAST_OFFSET_Y', 540),
            'TOAST_LINE_HEIGHT': getattr(config, 'TOAST_LINE_HEIGHT', 32),
            'TOAST_FONT_SIZE': getattr(config, 'TOAST_FONT_SIZE', 20),
            'MAP_SEARCH_KEYWORDS': getattr(config, 'MAP_SEARCH_KEYWORDS', {}),

            # ===== 突变事件配置 =====
            'MUTATOR_ALERT_SECONDS': getattr(config, 'MUTATOR_ALERT_SECONDS', 49),
            'MUTATOR_WARNING_THRESHOLD_SECONDS': getattr(config, 'MUTATOR_WARNING_THRESHOLD_SECONDS', 10),
            'MUTATOR_NORMAL_COLOR': getattr(config, 'MUTATOR_NORMAL_COLOR', 'rgb(255, 255, 255)'),
            'MUTATOR_WARNING_COLOR': getattr(config, 'MUTATOR_WARNING_COLOR', 'rgb(255, 0, 0)'),

            'MUTATOR_ALERT_OFFSET_X': getattr(config, 'MUTATOR_ALERT_OFFSET_X', 19),
            'MUTATOR_ALERT_OFFSET_Y': getattr(config, 'MUTATOR_ALERT_OFFSET_Y', 324),
            'MUTATOR_ALERT_LINE_HEIGHT': getattr(config, 'MUTATOR_ALERT_LINE_HEIGHT', 32),
            'MUTATOR_ALERT_FONT_SIZE': getattr(config, 'MUTATOR_ALERT_FONT_SIZE', 19),
            
            'MUTATOR_ICON_TRANSPARENCY': getattr(config, 'MUTATOR_ICON_TRANSPARENCY', 0.7),
            
            # ===== 自定义倒计时配置 =====
            'COUNTDOWN_OPTIONS': getattr(config, 'COUNTDOWN_OPTIONS', []),
            'COUNTDOWN_MAX_CONCURRENT': getattr(config, 'COUNTDOWN_MAX_CONCURRENT', 3),
            'COUNTDOWN_WARNING_THRESHOLD_SECONDS': getattr(config, 'COUNTDOWN_WARNING_THRESHOLD_SECONDS', 10),
            'COUNTDOWN_DISPLAY_COLOR': getattr(config, 'COUNTDOWN_DISPLAY_COLOR', 'rgb(0, 255, 255)'),

            # ===== 声音配置 =====
            'ALERT_SOUND_COOLDOWN': getattr(config, 'ALERT_SOUND_COOLDOWN', 10),
            'ALERT_SOUND_VOLUME': getattr(config, 'ALERT_SOUND_VOLUME', 90),

            # ===== 笔记 =====
            'MEMO_OPACITY': getattr(config, 'MEMO_OPACITY', 1.0),
            'MEMO_DURATION': getattr(config, 'MEMO_DURATION', 5000),
            'MEMO_FADE_TIME': getattr(config, 'MEMO_FADE_TIME', 1000),

            # ===== 图像识别 =====
            '''
            'GAME_SCREEN_DPI': getattr(config, 'GAME_SCREEN_DPI', 96),
            'GAME_ICO_RECONGIZE_INTERVAL': getattr(config, 'GAME_ICO_RECONGIZE_INTERVAL', 1),
            'GAME_ICO_RECONGIZE_CONFIDENCE': getattr(config, 'GAME_ICO_RECONGIZE_CONFIDENCE', 0.9),
            'DEBUG_SHOW_ENEMY_INFO_SQUARE': getattr(config, 'DEBUG_SHOW_ENEMY_INFO_SQUARE', False),
            'GAME_ICO_RECONGIZE_TIMEOUT': getattr(config, 'GAME_ICO_RECONGIZE_TIMEOUT', 300),
            '''

            'GAME_ICON_POS_AMON_RACE': getattr(config, 'GAME_ICON_POS_AMON_RACE', [45, 300, 36, 36]),
            'GAME_ICON_POS_AMON_TROOPS': getattr(config, 'GAME_ICON_POS_AMON_TROOPS', [1710, 938, 1904, 1035]),

            'MUTATOR_AND_ENEMY_RACE_RECOGNIZER_ROI': getattr(config, 'MUTATOR_AND_ENEMY_RACE_RECOGNIZER_ROI', (1850, 50, 1920, 800)),
            'ENEMY_COMP_RECOGNIZER_ROI': getattr(config, 'ENEMY_COMP_RECOGNIZER_ROI', (1450, 373 ,1920 ,800)),

            'MALWARFARE_PURIFIED_COUNT_TOP_LEFT_COORD': getattr(config, 'MALWARFARE_PURIFIED_COUNT_TOP_LEFT_COORD', (298, 85)),
            'MALWARFARE_PURIFIED_COUNT_BOTTOMRIGHT_COORD': getattr(config, 'MALWARFARE_PURIFIED_COUNT_BOTTOMRIGHT_COORD', (334, 103)),
            'MALWARFARE_TIME_TOP_LFET_COORD': getattr(config, 'MALWARFARE_TIME_TOP_LFET_COORD', (431, 85)),
            'MALWARFARE_TIME_BOTTOM_RIGHT_COORD': getattr(config, 'MALWARFARE_TIME_BOTTOM_RIGHT_COORD', (475, 103)),
            'MALWARFARE_PAUSED_TOP_LFET_COORD': getattr(config, 'MALWARFARE_PAUSED_TOP_LFET_COORD', (343, 85)),
            'MALWARFARE_PAUSED_BOTTOM_RIGHT_COORD': getattr(config, 'MALWARFARE_PAUSED_BOTTOM_RIGHT_COORD', (420, 103)),
            'MALWARFARE_HERO_OFFSET':getattr(config, 'MALWARFARE_HERO_OFFSET', 97),
            'MALWARFARE_ZWEIHAKA_OFFSET':getattr(config, 'MALWARFARE_ZWEIHAKA_OFFSET', 181),
            'MALWARFARE_REPLAY_OFFSET':getattr(config, 'MALWARFARE_REPLAY_OFFSET', 49),

        }

        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    user_cfg = json.load(f)
                    default_cfg.update(user_cfg)
            except Exception as e:
                self.logger.error(f"读取设置文件失败: {e}")
        
        return default_cfg

    def init_ui(self):
        main_layout = QVBoxLayout()
        self.tabs = QTabWidget()
        
        self.create_general_tab()       # 1. 常规设置
        self.create_interface_tab()     # 2. 界面与显示
        self.create_map_settings_tab()  # 3. 地图提醒 (Map Config)
        self.create_mutation_settings_tab() # 4. 因子提示配置 (Mutation Config)
        self.create_hotkey_tab()        # 5. 快捷键
        self.create_general_rec_tab()   # 6. 图像设置

        main_layout.addWidget(self.tabs)

        btn_layout = QHBoxLayout()
        save_btn = QPushButton("保存 (Save)")
        save_btn.clicked.connect(self.on_save)
        cancel_btn = QPushButton("取消 (Cancel)")
        cancel_btn.clicked.connect(self.reject)
        
        save_btn.setStyleSheet("background-color: #4CAF50; color: white; padding: 8px;")
        cancel_btn.setStyleSheet("padding: 8px;")

        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        
        main_layout.addLayout(btn_layout)
        self.setLayout(main_layout)

    def get_available_maps(self):
        """根据当前设置的语言读取地图文件列表"""
        # 获取当前 UI 中选择的语言（而不是 config 里的，这样可以实时预览切换）
        lang = "zh"
        if 'current_language' in self.widgets:
            lang = self.widgets['current_language']['widget'].currentText()
        else:
            lang = self.current_config.get('current_language', 'zh')

        # 计算路径
        maps_dir = get_resources_dir(os.path.join('maps', lang))
        
        map_files = []
        if os.path.exists(maps_dir):
            try:
                # 读取文件列表，过滤掉后缀名
                for f in os.listdir(maps_dir):
                    if os.path.isfile(os.path.join(maps_dir, f)):
                        name, _ = os.path.splitext(f)
                        map_files.append(name)
            except Exception as e:
                self.logger.error(f"读取地图列表失败: {e}")
        
        return sorted(map_files)
      
      
    def add_row(self, layout, label_text, key, widget_type, **kwargs):
        val = self.current_config.get(key)
        if val is None and widget_type != 'dict': # dict可能为空字典
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
            map_list = self.get_available_maps()
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
        
        def spin(v):
            sb = QSpinBox()
            sb.setRange(0, 10000)
            sb.setValue(int(v))
            sb.setFixedWidth(65)
            return sb
        
        h.addWidget(QLabel("左上:"))
        spins = [spin(x1), spin(y1), spin(x2), spin(y2)]
        h.addWidget(spins[0]); h.addWidget(spins[1])
        h.addWidget(QLabel("右下:"))
        h.addWidget(spins[2]); h.addWidget(spins[3])
        h.addStretch()
        return {'box': box, 'spins': spins}

    def normalize_config(self, cfg: dict):
        point_map = {'MAIN_WINDOW_POS': ('MAIN_WINDOW_X', 'MAIN_WINDOW_Y')}
        for k, (xk, yk) in point_map.items():
            if k in cfg:
                x, y = cfg.pop(k)
                cfg[xk] = x; cfg[yk] = y

    def create_point_widget(self, x, y,show_get_btn = False):
        """修改位置组件：增加获取当前位置按钮"""
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        
        def create_spin(v):
            sb = QSpinBox()
            sb.setRange(-10000, 10000)
            sb.setValue(int(v))
            sb.setFixedWidth(70)
            # 同样禁用滚轮
            sb.setFocusPolicy(Qt.StrongFocus)
            sb.installEventFilter(self)
            return sb
          
        spin_x = create_spin(x)
        spin_y = create_spin(y)
        
        h.addWidget(QLabel("X:")); h.addWidget(spin_x)
        h.addWidget(QLabel("Y:")); h.addWidget(spin_y)
        
        # 只有需要显示按钮时才进入此逻辑
        if show_get_btn:
            btn_get_pos = QPushButton("获取当前位置")
            btn_get_pos.setToolTip("读取主窗口当前在屏幕上的坐标")
            
            def update_to_current():
                # 此时 self.main_window 已经在 __init__ 中定义
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
    # --- TABS ---

    def create_general_tab(self):
        tab = QWidget()
        layout = QFormLayout()
        
        self.add_row(layout, "语言 (Language):", 'current_language', 'combo', items=['zh', 'en'])
        
        gb = QGroupBox("日志与调试")
        gl = QFormLayout(gb)
        self.add_row(gl, "日志等级:", 'LOG_LEVEL', 'combo', items=['DEBUG', 'INFO', 'WARNING', 'ERROR'])
        self.add_row(gl, "调试模式:", 'debug_mode', 'bool')
        self.add_row(gl, "调试倍率:", 'debug_time_factor', 'double', min=0.1, max=20.0)
        layout.addRow(gb)
        
        # 声音配置整合在此或地图配置中，此处放入通用区域
        sb = QGroupBox("提示声音设置（具体提示音设定请参考resources里面的配置文件）")
        sl = QFormLayout(sb)
        self.add_row(sl, "音量 (0-100):", 'ALERT_SOUND_VOLUME', 'spin', max=100)
        self.add_row(sl, "同名警告冷却 (秒):", 'ALERT_SOUND_COOLDOWN', 'spin', max=60)
        layout.addRow(sb)

        tab.setLayout(layout)
        self.tabs.addTab(tab, "常规设置")

    def create_interface_tab(self):
        tab = QWidget()
        layout = QFormLayout()
        
        self.add_row(layout, "主窗口位置:", 'MAIN_WINDOW_POS', 'point')
        self.add_row(layout, "主窗口宽度:", 'MAIN_WINDOW_WIDTH', 'spin', max=2000)
        self.add_row(layout, "背景颜色:", 'MAIN_WINDOW_BG_COLOR', 'color')
        self.add_row(layout, "表格字体大小:", 'TABLE_FONT_SIZE', 'spin', min=8, max=72)
        self.add_row(layout, "表格高度:", 'TABLE_HEIGHT', 'spin', max=1000)

        mb = QGroupBox("笔记 (Memo) 设置")
        ml = QFormLayout(mb)
        self.add_row(ml, "透明度 (0-1):", 'MEMO_OPACITY', 'double', step=0.1)
        self.add_row(ml, "持续时间 (ms):", 'MEMO_DURATION', 'spin', max=60000)
        self.add_row(ml, "淡出时间 (ms):", 'MEMO_FADE_TIME', 'spin', max=5000)
        layout.addRow(mb)

        tab.setLayout(layout)
        self.tabs.addTab(tab, "界面显示")

    def create_map_settings_tab(self):
        """地图与倒计时标签页"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QFormLayout(content)

        # 1. 提示框通用布局 (Toast Layout)
        gb_layout = QGroupBox("提示框通用布局 (地图 & 倒计时) - 像素偏移 (Pixel Offset)")
        gl_layout = QFormLayout(gb_layout)
        hint = QLabel("基准点为游戏窗口左上角 (0, 0)")
        hint.setStyleSheet("color: gray; font-style: italic;")
        gl_layout.addRow(hint)
        self.add_row(gl_layout, "距离左侧 (X Offset):", 'TOAST_OFFSET_X', 'spin', max=3000)
        self.add_row(gl_layout, "距离顶部 (Y Offset):", 'TOAST_OFFSET_Y', 'spin', max=2000)
        self.add_row(gl_layout, "每行高度 (Line Height):", 'TOAST_LINE_HEIGHT', 'spin', max=200)
        self.add_row(gl_layout, "字体大小 (Font Size):", 'TOAST_FONT_SIZE', 'spin', max=100)
        layout.addRow(gb_layout)

        # 2. 地图事件逻辑
        gb_alert = QGroupBox("地图事件逻辑 (Map Events)")
        gl_alert = QFormLayout(gb_alert)
        self.add_row(gl_alert, "提前提醒时间 (秒):", 'MAP_ALERT_SECONDS', 'spin')
        self.add_row(gl_alert, "警告阈值 (秒):", 'MAP_ALERT_WARNING_THRESHOLD_SECONDS', 'spin')
        self.add_row(gl_alert, "正常倒计时颜色:", 'MAP_ALERT_NORMAL_COLOR', 'color')
        self.add_row(gl_alert, "警告倒计时颜色:", 'MAP_ALERT_WARNING_COLOR', 'color')
        layout.addRow(gb_alert)

        # 3. 搜索关键词
        self.add_row(layout, "地图搜索别名映射:", 'MAP_SEARCH_KEYWORDS', 'dict')

        # 4. 自定义倒计时配置
        gb_cd = QGroupBox("自定义倒计时 (Custom Countdown)")
        gl_cd = QFormLayout(gb_cd)
        self.add_row(gl_cd, "最大同时存在数量:", 'COUNTDOWN_MAX_CONCURRENT', 'spin', min=1, max=10)
        self.add_row(gl_cd, "警告阈值 (秒):", 'COUNTDOWN_WARNING_THRESHOLD_SECONDS', 'spin')
        self.add_row(gl_cd, "显示颜色:", 'COUNTDOWN_DISPLAY_COLOR', 'color')
        
        # 使用新的倒计时列表编辑器
        self.add_row(gl_cd, "倒计时选项列表:", 'COUNTDOWN_OPTIONS', 'countdown_list')
        layout.addRow(gb_cd)

        scroll.setWidget(content)
        self.tabs.addTab(scroll, "地图与倒计时")

    def create_mutation_settings_tab(self):
        """因子提示配置标签页"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QFormLayout(content)

        # 1. 倒计时
        gb_alert = QGroupBox("倒计时与警告")
        gl_alert = QFormLayout(gb_alert)
        self.add_row(gl_alert, "提前提示时间 (秒):", 'MUTATOR_ALERT_SECONDS', 'spin')
        self.add_row(gl_alert, "警告阈值时间 (秒):", 'MUTATOR_WARNING_THRESHOLD_SECONDS', 'spin')
        self.add_row(gl_alert, "正常文本颜色:", 'MUTATOR_NORMAL_COLOR', 'color')
        self.add_row(gl_alert, "警告文本颜色:", 'MUTATOR_WARNING_COLOR', 'color')
        layout.addRow(gb_alert)

        # 3. 提示布局
        gb_layout = QGroupBox("因子图标消息设置 (占窗口大小的比例大小)")
        gl_layout = QFormLayout(gb_layout)
        self.add_row(gl_layout, "每行高度 (Line Height):", 'MUTATOR_ALERT_LINE_HEIGHT', 'spin', max=200)
        self.add_row(gl_layout, "字体大小 (Font Size):", 'MUTATOR_ALERT_FONT_SIZE', 'spin', max=100)
        self.add_row(gl_layout, "图标透明度:", 'MUTATOR_ICON_TRANSPARENCY', 'double')
        label_hint = QLabel("以下填入的是占窗口大小的比例的位移,数字越大越靠近右/下")
        label_hint.setStyleSheet("color: gray; font-size: 10pt; font-style: italic;")
        gl_layout.addRow(label_hint)
        
        self.add_row(gl_layout, "距离顶部 (Y Offset):", 'MUTATOR_ALERT_OFFSET_Y', 'spin', max=2000)
        self.add_row(gl_layout, "距离左侧 (X Offset):", 'MUTATOR_ALERT_OFFSET_X', 'spin', max=3000)
        layout.addRow(gb_layout)

        scroll.setWidget(content)
        self.tabs.addTab(scroll, "因子提醒")

    def create_hotkey_tab(self):
        tab = QWidget()
        layout = QFormLayout()
        
        self.add_row(layout, "地图切换快捷键:", 'MAP_SHORTCUT', 'hotkey')
        self.add_row(layout, "锁定窗口快捷键:", 'LOCK_SHORTCUT', 'hotkey')
        self.add_row(layout, "截图快捷键:", 'SCREENSHOT_SHORTCUT', 'hotkey')
        self.add_row(layout, "笔记临时显示:", 'MEMO_TEMP_SHORTCUT', 'hotkey')
        self.add_row(layout, "笔记开关显示:", 'MEMO_TOGGLE_SHORTCUT', 'hotkey')
        self.add_row(layout, "自定义倒计时菜单:", 'COUNTDOWN_SHORTCUT', 'hotkey')
        
        tab.setLayout(layout)
        self.tabs.addTab(tab, "快捷键")

    def create_general_rec_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QFormLayout(content)
        
        layout.addRow(QLabel("<b>[ 高级设置 ] 修改此处可能导致识别失效，如需修改，请截图完整游戏窗口，在photoshop等可查看图片内容具体坐标辅助下修改</b>"))
        
        '''
        gb_basic = QGroupBox("基础参数")
        gl_basic = QFormLayout(gb_basic)
        self.add_row(gl_basic, "屏幕 DPI:", 'GAME_SCREEN_DPI', 'spin', max=500)
        self.add_row(gl_basic, "识别间隔 (秒):", 'GAME_ICO_RECONGIZE_INTERVAL', 'spin', max=10)
        self.add_row(gl_basic, "识别超时 (秒):", 'GAME_ICO_RECONGIZE_TIMEOUT', 'spin', max=600)
        self.add_row(gl_basic, "最低置信度:", 'GAME_ICO_RECONGIZE_CONFIDENCE', 'double')
        self.add_row(gl_basic, "显示调试框:", 'DEBUG_SHOW_ENEMY_INFO_SQUARE', 'bool')
        layout.addRow(gb_basic)
        '''
        
        gb_icon = QGroupBox("种族/因子识别区域")
        gl_icon = QFormLayout(gb_icon)
        self.add_row(gl_icon, "因子识别区域:", 'MUTATOR_AND_ENEMY_RACE_RECOGNIZER_ROI', 'roi')
        self.add_row(gl_icon, "AI 种族识别区域:", 'ENEMY_COMP_RECOGNIZER_ROI', 'roi')
        layout.addRow(gb_icon)
        
        gb_mw = QGroupBox("净网行动识别区域坐标 (Malwarfare)")
        gl_mw = QFormLayout(gb_mw)
        self.add_row(gl_mw, "已净化 (左上):", 'MALWARFARE_PURIFIED_COUNT_TOP_LEFT_COORD', 'point')
        self.add_row(gl_mw, "已净化 (右下):", 'MALWARFARE_PURIFIED_COUNT_BOTTOMRIGHT_COORD', 'point')
        self.add_row(gl_mw, "时间 (左上):", 'MALWARFARE_TIME_TOP_LFET_COORD', 'point')
        self.add_row(gl_mw, "时间 (右下):", 'MALWARFARE_TIME_BOTTOM_RIGHT_COORD', 'point')
        self.add_row(gl_mw, "暂停标识 (左上):", 'MALWARFARE_PAUSED_TOP_LFET_COORD', 'point')
        self.add_row(gl_mw, "单英雄时坐标偏移:", 'MALWARFARE_HERO_OFFSET', 'spin')
        self.add_row(gl_mw, "原生双雄时坐标偏移:", 'MALWARFARE_ZWEIHAKA_OFFSET', 'spin')
        self.add_row(gl_mw, "录像播放时坐标偏移:", 'MALWARFARE_REPLAY_OFFSET', 'spin')
        
        layout.addRow(gb_mw)
        

        scroll.setWidget(content)
        self.tabs.addTab(scroll, "识别设置")


    def get_ui_values(self):
        new_values = {}
        for key, item in self.widgets.items():
            widget = item['widget']
            w_type = item['type']
            
            val = None
            if w_type == 'line' or w_type == 'hotkey' or w_type == 'color':
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
            elif w_type == 'countdown_list': # [新增]
                val = widget.value()
            
            new_values[key] = val
        return new_values

    def on_save(self):
      new_config = self.get_ui_values()
      changes = []
      for key, new_val in new_config.items():
          old_val = self.original_config.get(key)
          
          # 将对比双方都转为 list 进行数值比对，消除 (1,2) vs [1,2] 的差异
          c_old = list(old_val) if isinstance(old_val, (list, tuple)) else old_val
          c_new = list(new_val) if isinstance(new_val, (list, tuple)) else new_val
          
          if c_old != c_new:
              label = self.widgets[key]['label']
              changes.append(f"【{label}】 {old_val} -> {new_val}")

      if not changes:
            QMessageBox.information(self, "提示", "没有检测到任何修改。")
            self.accept()
            return

      reply = QMessageBox.question(self, "确认修改", 
                                     "检测到以下修改，确认保存吗？\n\n" + "\n".join(changes[:10]) + 
                                     ("\n..." if len(changes)>10 else ""), 
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
      if reply == QMessageBox.Yes:
            self.normalize_config(new_config)
            self.save_to_json(new_config)
            self.settings_saved.emit(new_config)
            self.original_config = copy.deepcopy(new_config)
            self.accept()

    def save_to_json(self, config_data):
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=4, ensure_ascii=False)
            QMessageBox.information(self, "成功", "设置已保存！\n部分设置需要重启程序才能生效。")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存失败: {str(e)}")

# 独立运行测试
if __name__ == '__main__':
    import sys
    from PyQt5.QtWidgets import QApplication
    app = QApplication(sys.argv)
    win = SettingsWindow()
    win.show()
    sys.exit(app.exec_())