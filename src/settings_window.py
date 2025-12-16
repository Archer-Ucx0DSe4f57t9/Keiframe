import json
import os
import copy
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, 
                             QLabel, QLineEdit, QSpinBox, QDoubleSpinBox, 
                             QCheckBox, QPushButton, QColorDialog, QMessageBox, 
                             QFormLayout, QScrollArea, QDialog, QComboBox,QGroupBox)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QKeyEvent

import config  # 导入你现有的 config.py 作为默认值
from logging_util import get_logger

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
        self.logger = get_logger("setting window")
        
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
            # ===== 常规 =====
            'current_language': config.current_language,
            'LOG_LEVEL': config.LOG_LEVEL,
            'debug_mode': config.debug_mode,
            'debug_time_factor': config.debug_time_factor,

            # ===== 快捷键 =====
            'MAP_SHORTCUT': config.MAP_SHORTCUT,
            'LOCK_SHORTCUT': config.LOCK_SHORTCUT,
            'SCREENSHOT_SHORTCUT': config.SCREENSHOT_SHORTCUT,
            'SHOW_ARTIFACT_SHORTCUT': config.SHOW_ARTIFACT_SHORTCUT,
            'MEMO_TEMP_SHORTCUT': config.MEMO_TEMP_SHORTCUT,
            'MEMO_TOGGLE_SHORTCUT': config.MEMO_TOGGLE_SHORTCUT,

            # ===== Toast =====


            # ===== 主窗口 =====
            'MAIN_WINDOW_POS': (config.MAIN_WINDOW_X, config.MAIN_WINDOW_Y),
            'MAIN_WINDOW_WIDTH': config.MAIN_WINDOW_WIDTH,
            'MAIN_WINDOW_BG_COLOR': config.MAIN_WINDOW_BG_COLOR,

            # ===== 表格 =====
            'TABLE_FONT_SIZE': config.TABLE_FONT_SIZE,
            'TABLE_HEIGHT': config.TABLE_HEIGHT,

            # ===== 地图提醒 =====
            'MAP_ALERT_SECONDS': config.MAP_ALERT_SECONDS,
            'MAP_ALERT_WARNING_THRESHOLD_SECONDS': config.MAP_ALERT_WARNING_THRESHOLD_SECONDS,

            # ===== 突变因子提醒 =====
            'MUTATION_FACTOR_ALERT_SECONDS': config.MUTATION_FACTOR_ALERT_SECONDS,
            'MUTATION_FACTOR_WARNING_THRESHOLD_SECONDS': config.MUTATION_FACTOR_WARNING_THRESHOLD_SECONDS,

            # ===== 声音 =====
            'ALERT_SOUND_COOLDOWN': config.ALERT_SOUND_COOLDOWN,
            'ALERT_SOUND_VOLUME': config.ALERT_SOUND_VOLUME,

            # ===== 笔记 =====
            'MEMO_OPACITY': config.MEMO_OPACITY,
            'MEMO_DURATION': config.MEMO_DURATION,
            'MEMO_FADE_TIME': config.MEMO_FADE_TIME,

            # ===== 图像识别（仅可调部分）=====
            'GAME_SCREEN_DPI': config.GAME_SCREEN_DPI,
            'GAME_ICO_RECONGIZE_INTERVAL': config.GAME_ICO_RECONGIZE_INTERVAL,
            'GAME_ICO_RECONGIZE_CONFIDENCE': config.GAME_ICO_RECONGIZE_CONFIDENCE,
            'DEBUG_SHOW_ENEMY_INFO_SQUARE': config.DEBUG_SHOW_ENEMY_INFO_SQUARE,
            'GAME_ICO_RECONGIZE_INTERVAL': config.GAME_ICO_RECONGIZE_INTERVAL,
            'GAME_ICO_RECONGIZE_TIMEOUT': config.GAME_ICO_RECONGIZE_TIMEOUT,

            'GAME_ICON_POS_AMON_RACE': config.GAME_ICON_POS_AMON_RACE,
            'GAME_ICON_POS_AMON_TROOPS': config.GAME_ICON_POS_AMON_TROOPS,

            'MUTATOR_AND_ENEMY_RACE_RECOGNIZER_ROI': config.MUTATOR_AND_ENEMY_RACE_RECOGNIZER_ROI,
            'ENEMY_COMP_RECOGNIZER_ROI': config.ENEMY_COMP_RECOGNIZER_ROI,

            'MALWARFARE_PURIFIED_COUNT_TOP_LEFT_COORD': config.MALWARFARE_PURIFIED_COUNT_TOP_LEFT_COORD,
            'MALWARFARE_PURIFIED_COUNT_BOTTOMRIGHT_COORD': config.MALWARFARE_PURIFIED_COUNT_BOTTOMRIGHT_COORD,

            'MALWARFARE_TIME_TOP_LFET_COORD': config.MALWARFARE_TIME_TOP_LFET_COORD,
            'MALWARFARE_TIME_BOTTOM_RIGHT_COORD': config.MALWARFARE_TIME_BOTTOM_RIGHT_COORD,

            'MALWARFARE_PAUSED_TOP_LFET_COORD': config.MALWARFARE_PAUSED_TOP_LFET_COORD,
            'MALWARFARE_PAUSED_BOTTOM_RIGHT_COORD': config.MALWARFARE_PAUSED_BOTTOM_RIGHT_COORD,
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
        self.create_general_rec_tab() # 5. 通用图像识别
        self.create_mwf_rec_tab() # 6. 净网识别

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
        
        if val is None:
          self.logger.error( f"配置项 '{key}' 未在 load_config() 中初始化")
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
        elif widget_type == 'roi':
            widget = self.create_roi_widget(*val)
            self.widgets[key] = {
              'widget': widget['spins'],
              'type': 'roi',
              'label': label_text
            }
            layout.addRow(label_text, widget['box'])
            return
        elif widget_type == 'point':
            x, y = val
            widget = self.create_point_widget(x, y)
            self.widgets[key] = {
                'widget': widget['spins'],
                'type': 'point',
                'label': label_text
            }
            layout.addRow(label_text, widget['box'])
            return
        # 记录控件，以便获取值
        if widget:
            self.widgets[key] = {'widget': widget, 'type': widget_type, 'label': label_text}
            layout.addRow(label_text, widget)


    #辅助函数，针对roi内容
    def create_roi_widget(self, x1, y1, x2, y2):
      box = QWidget()
      h = QHBoxLayout(box)
      h.setContentsMargins(0, 0, 0, 0)
      h.setSpacing(4)

      def spin(v):
          sb = QSpinBox()
          sb.setRange(0, 10000)
          sb.setValue(int(v))
          sb.setFixedWidth(65)
          return sb

      def label(text):
          l = QLabel(text)
          l.setStyleSheet("color: #666;")
          return l

      # 左上
      h.addWidget(label("左上"))
      h.addWidget(label("X"))
      sb_x1 = spin(x1)
      h.addWidget(sb_x1)
      h.addWidget(label("Y"))
      sb_y1 = spin(y1)
      h.addWidget(sb_y1)

      h.addSpacing(10)

      # 右下
      h.addWidget(label("右下"))
      h.addWidget(label("X"))
      sb_x2 = spin(x2)
      h.addWidget(sb_x2)
      h.addWidget(label("Y"))
      sb_y2 = spin(y2)
      h.addWidget(sb_y2)

      h.addStretch()

      return {
          'box': box,
          'spins': [sb_x1, sb_y1, sb_x2, sb_y2]
      }
      
    #辅助函数，创建点
    def create_point_widget(self, x, y):
      box = QWidget()
      h = QHBoxLayout(box)
      h.setContentsMargins(0, 0, 0, 0)
      h.setSpacing(4)

      def spin(v):
          sb = QSpinBox()
          sb.setRange(0, 10000)
          sb.setValue(int(v))
          sb.setFixedWidth(70)
          return sb

      def label(t):
          l = QLabel(t)
          l.setStyleSheet("color:#666;")
          return l

      h.addWidget(label("X"))
      sb_x = spin(x)
      h.addWidget(sb_x)

      h.addSpacing(6)

      h.addWidget(label("Y"))
      sb_y = spin(y)
      h.addWidget(sb_y)

      h.addStretch()

      return {
          'box': box,
          'spins': [sb_x, sb_y]
      }
      
    #辅助函数，点打包
    def normalize_config(self, cfg: dict):
      point_map = {
          'MAIN_WINDOW_POS': ('MAIN_WINDOW_X', 'MAIN_WINDOW_Y'),
          # 以后需要再加
      }

      for k, (xk, yk) in point_map.items():
          if k in cfg:
              x, y = cfg.pop(k)
              cfg[xk] = x
              cfg[yk] = y
    # ---------------- 分页构建 ----------------

    def create_general_tab(self):
        tab = QWidget()
        layout = QFormLayout()

        
        logging_box = QGroupBox("日志和调试相关设置")
        logging_layout = QFormLayout(logging_box)
        self.add_row(logging_layout, "日志等级:", 'LOG_LEVEL', 'combo',
                    items=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'])
        self.add_row(logging_layout, "调试模式:", 'debug_mode', 'bool')
        self.add_row(logging_layout, "调试时间倍率:", 'debug_time_factor', 'double', min=0.1, max=20.0)
        
        layout.addRow(logging_box)
        
        #语言设置
        self.add_row(layout, "语言:", 'current_language', 'combo', items=['zh', 'en'])
        
        tab.setLayout(layout)
        self.tabs.addTab(tab, "常规设置")

    def create_interface_tab(self):
        tab = QWidget()
        layout = QFormLayout()
        


        self.add_row(layout, "主窗口位置:", 'MAIN_WINDOW_POS', 'point')
        self.add_row(layout, "主窗口宽度:", 'MAIN_WINDOW_WIDTH', 'spin', max=1000)
        self.add_row(layout, "主窗口背景 RGBA:", 'MAIN_WINDOW_BG_COLOR', 'line')

        self.add_row(layout, "表格字体大小:", 'TABLE_FONT_SIZE', 'spin', min=8, max=48)
        self.add_row(layout, "表格高度:", 'TABLE_HEIGHT', 'spin', max=500)
        
        tab.setLayout(layout)
        self.tabs.addTab(tab, "界面与显示")

    def create_alert_tab(self):
        tab = QWidget()
        layout = QFormLayout()
        
        self.add_row(layout, "地图提前提醒(秒):", 'MAP_ALERT_SECONDS', 'spin', max=300)
        self.add_row(layout, "警告阈值(秒):", 'MAP_ALERT_WARNING_THRESHOLD_SECONDS', 'spin')

        self.add_row(layout, "突变因子提前提醒时间:", 'MUTATION_FACTOR_ALERT_SECONDS', 'spin')
        self.add_row(layout, "突变警告时间:", 'MUTATION_FACTOR_WARNING_THRESHOLD_SECONDS', 'spin')

        self.add_row(layout, "同一提示音最短冷却(秒):", 'ALERT_SOUND_COOLDOWN', 'spin', max=60)
        self.add_row(layout, "音量(0-100):", 'ALERT_SOUND_VOLUME', 'spin', max=100)
        
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
        
    def create_general_rec_tab(self):
        # 净网识别项非常多，使用滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content_widget = QWidget()
        layout = QFormLayout()
        
        layout.addRow(QLabel("<b>[ 高级设置 ] 修改此处可能导致识别失效</b>"))
        
        #基本参数
        basic_box = QGroupBox("基础识别参数")
        basic_layout = QFormLayout(basic_box)

        self.add_row(basic_layout, "屏幕 DPI:", 'GAME_SCREEN_DPI', 'spin', max=400)
        self.add_row(basic_layout, "识别间隔(秒):", 'GAME_ICO_RECONGIZE_INTERVAL', 'spin', max=10)
        self.add_row(basic_layout, "识别超时(秒):", 'GAME_ICO_RECONGIZE_TIMEOUT', 'spin', max=600)
        self.add_row(basic_layout, "识别置信度:", 'GAME_ICO_RECONGIZE_CONFIDENCE', 'double', min=0.1, max=1.0)
        self.add_row(basic_layout, "显示调试框:", 'DEBUG_SHOW_ENEMY_INFO_SQUARE', 'bool')

        layout.addRow(basic_box)
        
        #图标识别区域
        icon_box = QGroupBox("图标识别区域 (像素坐标)")
        icon_layout = QFormLayout(icon_box)

        self.add_row(icon_layout, "种族图标:", 'GAME_ICON_POS_AMON_RACE', 'roi')
        self.add_row(icon_layout, "部队区域:", 'GAME_ICON_POS_AMON_TROOPS', 'roi')

        layout.addRow(icon_box)
        

        #因子和种族识别区域
        roi_box = QGroupBox("因子 & 敌方种族识别区域")
        roi_layout = QFormLayout(roi_box)

        self.add_row(
            roi_layout,
            "突变因子 + 敌方种族 ROI:",
            'MUTATOR_AND_ENEMY_RACE_RECOGNIZER_ROI',
            'roi'
        )

        self.add_row(
            roi_layout,
            "敌方 AI 组成 ROI:",
            'ENEMY_COMP_RECOGNIZER_ROI',
            'roi'
        )

        layout.addRow(roi_box)


        content_widget.setLayout(layout)
        scroll.setWidget(content_widget)
        self.tabs.addTab(scroll, "识别设置")

    def create_mwf_rec_tab(self):
        # 净网识别项非常多，使用滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content_widget = QWidget()
        layout = QFormLayout()
        
        layout.addRow(QLabel("<b>[ 高级设置 ] 修改此处可能导致识别失效</b>"))
        
        #基本参数
        basic_box = QGroupBox("基础识别参数")
        basic_layout = QFormLayout(basic_box)

        self.add_row(basic_layout, "屏幕 DPI:", 'GAME_SCREEN_DPI', 'spin', max=400)
        self.add_row(basic_layout, "识别间隔(秒):", 'GAME_ICO_RECONGIZE_INTERVAL', 'spin', max=10)
        self.add_row(basic_layout, "识别超时(秒):", 'GAME_ICO_RECONGIZE_TIMEOUT', 'spin', max=600)
        self.add_row(basic_layout, "识别置信度:", 'GAME_ICO_RECONGIZE_CONFIDENCE', 'double', min=0.1, max=1.0)
        self.add_row(basic_layout, "显示调试框:", 'DEBUG_SHOW_ENEMY_INFO_SQUARE', 'bool')

        layout.addRow(basic_box)
        
        #净网识别roi设置
        mw_box = QGroupBox("净网行动识别区域坐标 (Malwarefare)")
        mw_layout = QFormLayout(mw_box)

        self.add_row(mw_layout,"已净化 左上角:",'MALWARFARE_PURIFIED_COUNT_TOP_LEFT_COORD','point')
        self.add_row(mw_layout, "已净化 右下角:", 'MALWARFARE_PURIFIED_COUNT_BOTTOMRIGHT_COORD', 'point')

        self.add_row(mw_layout, "时间 左上角:", 'MALWARFARE_TIME_TOP_LFET_COORD', 'point')
        self.add_row(mw_layout, "时间 右下角:", 'MALWARFARE_TIME_BOTTOM_RIGHT_COORD', 'point')

        self.add_row(mw_layout, "暂停标识 左上角:", 'MALWARFARE_PAUSED_TOP_LFET_COORD', 'point')
        self.add_row(mw_layout, "暂停标识 右下角:", 'MALWARFARE_PAUSED_BOTTOM_RIGHT_COORD', 'point')

        layout.addRow(mw_box)

        
        content_widget.setLayout(layout)
        scroll.setWidget(content_widget)
        self.tabs.addTab(scroll, "净网识别")
    
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
            elif w_type == 'roi':
                val = tuple(sb.value() for sb in widget)
            elif w_type == 'point':
                val = tuple(sb.value() for sb in widget)
                        
            new_values[key] = val
        return new_values

    def on_save(self):
      new_config = self.get_ui_values()

      changes = []

      # ① 先用 UI key 对比
      for key, new_val in new_config.items():
          old_val = self.original_config.get(key)
          if str(new_val) != str(old_val):
              label = self.widgets[key]['label']
              changes.append(
                  f"【{label}】\n   原值: {old_val}  ->  新值: {new_val}"
              )

      if not changes:
          QMessageBox.information(self, "提示", "没有检测到任何修改。")
          self.accept()
          return

      confirm_text = "检测到以下修改，确认保存吗？\n\n" + "\n".join(changes)
      reply = QMessageBox.question(
          self, "确认修改",
          confirm_text,
          QMessageBox.Yes | QMessageBox.No,
          QMessageBox.No
      )

      if reply == QMessageBox.Yes:
          # ② 只在最终保存前 normalize
          self.normalize_config(new_config)

          self.save_to_json(new_config)
          self.settings_saved.emit(new_config)

          self.original_config = copy.deepcopy(new_config)
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