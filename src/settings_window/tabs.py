#tabs.py
# 这个文件定义了设置界面中各个选项卡的构建逻辑，使用了工厂模式来创建不同的设置页面
from PyQt5 import QtCore 
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, 
                             QLabel, QLineEdit, QSpinBox, QDoubleSpinBox, 
                             QCheckBox, QPushButton, QColorDialog, QMessageBox, 
                             QFormLayout, QScrollArea, QDialog, QComboBox, QGroupBox,
                             QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog)
from src import config
    # --- TABS ---
class SettingsTabsBuilder:
  @staticmethod
  def create_general_tab(parent):
      tab = QWidget()
      layout = QFormLayout()
      
      parent.add_row(layout, "语言 (Language):", 'current_language', 'combo', items=['zh', 'en'])
      
      gb = QGroupBox("日志与调试")
      gl = QFormLayout(gb)
      parent.add_row(gl, "日志等级:", 'LOG_LEVEL', 'combo', items=['DEBUG', 'INFO', 'WARNING', 'ERROR'])
      parent.add_row(gl, "调试模式:", 'debug_mode', 'bool')
      parent.add_row(gl, "调试倍率:", 'debug_time_factor', 'double', min=0.1, max=20.0)
      layout.addRow(gb)
      
      # 声音配置整合在此或地图配置中，此处放入通用区域
      sb = QGroupBox("提示声音设置（具体提示音设定请参考resources里面的配置文件）")
      sl = QFormLayout(sb)
      parent.add_row(sl, "音量 (0-100):", 'ALERT_SOUND_VOLUME', 'spin', max=100)
      parent.add_row(sl, "同名警告冷却 (秒):", 'ALERT_SOUND_COOLDOWN', 'spin', max=60)
      layout.addRow(sb)

      tab.setLayout(layout)
      parent.tabs.addTab(tab, "常规设置")
  
  @staticmethod
  def create_interface_tab(parent):
      tab = QWidget()
      layout = QFormLayout()
      
      parent.add_row(layout, "主窗口位置:", 'MAIN_WINDOW_POS', 'point')
      parent.add_row(layout, "主窗口宽度:", 'MAIN_WINDOW_WIDTH', 'spin', max=2000)
      parent.add_row(layout, "背景颜色:", 'MAIN_WINDOW_BG_COLOR', 'color')
      parent.add_row(layout, "表格字体大小:", 'TABLE_FONT_SIZE', 'spin', min=8, max=72)
      parent.add_row(layout, "表格高度:", 'TABLE_HEIGHT', 'spin', max=1000)

      mb = QGroupBox("笔记 (Memo) 设置")
      ml = QFormLayout(mb)
      parent.add_row(ml, "透明度 (0-1):", 'MEMO_OPACITY', 'double', step=0.1)
      parent.add_row(ml, "持续时间 (ms):", 'MEMO_DURATION', 'spin', max=60000)
      parent.add_row(ml, "淡出时间 (ms):", 'MEMO_FADE_TIME', 'spin', max=5000)
      layout.addRow(mb)

      tab.setLayout(layout)
      parent.tabs.addTab(tab, "界面显示")

  @staticmethod
  def create_map_settings_tab(parent):
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
      parent.add_row(gl_layout, "距离左侧 (X Offset):", 'TOAST_OFFSET_X', 'spin', max=3000)
      parent.add_row(gl_layout, "距离顶部 (Y Offset):", 'TOAST_OFFSET_Y', 'spin', max=2000)
      parent.add_row(gl_layout, "每行高度 (Line Height):", 'TOAST_LINE_HEIGHT', 'spin', max=200)
      parent.add_row(gl_layout, "字体大小 (Font Size):", 'TOAST_FONT_SIZE', 'spin', max=100)
      layout.addRow(gb_layout)

      # 2. 地图事件逻辑
      gb_alert = QGroupBox("地图事件逻辑 (Map Events)")
      gl_alert = QFormLayout(gb_alert)
      parent.add_row(gl_alert, "提前提醒时间 (秒):", 'MAP_ALERT_SECONDS', 'spin')
      parent.add_row(gl_alert, "警告阈值 (秒):", 'MAP_ALERT_WARNING_THRESHOLD_SECONDS', 'spin')
      parent.add_row(gl_alert, "正常倒计时颜色:", 'MAP_ALERT_NORMAL_COLOR', 'color')
      parent.add_row(gl_alert, "警告倒计时颜色:", 'MAP_ALERT_WARNING_COLOR', 'color')
      layout.addRow(gb_alert)

      # 3. 搜索关键词
      parent.add_row(layout, "地图搜索别名映射:", 'MAP_SEARCH_KEYWORDS', 'dict')

      # 4. 自定义倒计时配置
      gb_cd = QGroupBox("自定义倒计时 (Custom Countdown)")
      gl_cd = QFormLayout(gb_cd)
      parent.add_row(gl_cd, "最大同时存在数量:", 'COUNTDOWN_MAX_CONCURRENT', 'spin', min=1, max=10)
      parent.add_row(gl_cd, "警告阈值 (秒):", 'COUNTDOWN_WARNING_THRESHOLD_SECONDS', 'spin')
      parent.add_row(gl_cd, "显示颜色:", 'COUNTDOWN_DISPLAY_COLOR', 'color')
      
      # 使用新的倒计时列表编辑器
      parent.add_row(gl_cd, "倒计时选项列表:", 'COUNTDOWN_OPTIONS', 'countdown_list')
      layout.addRow(gb_cd)

      scroll.setWidget(content)
      parent.tabs.addTab(scroll, "地图与倒计时")

  @staticmethod
  def create_mutation_settings_tab(parent):
      """因子提示配置标签页"""
      scroll = QScrollArea()
      scroll.setWidgetResizable(True)
      content = QWidget()
      layout = QFormLayout(content)

      # 1. 倒计时
      gb_alert = QGroupBox("倒计时与警告")
      gl_alert = QFormLayout(gb_alert)
      parent.add_row(gl_alert, "提前提示时间 (秒):", 'MUTATOR_ALERT_SECONDS', 'spin')
      parent.add_row(gl_alert, "警告阈值时间 (秒):", 'MUTATOR_WARNING_THRESHOLD_SECONDS', 'spin')
      parent.add_row(gl_alert, "正常文本颜色:", 'MUTATOR_NORMAL_COLOR', 'color')
      parent.add_row(gl_alert, "警告文本颜色:", 'MUTATOR_WARNING_COLOR', 'color')
      layout.addRow(gb_alert)

      # 3. 提示布局
      gb_layout = QGroupBox("因子图标消息设置 (占窗口大小的比例大小)")
      gl_layout = QFormLayout(gb_layout)
      parent.add_row(gl_layout, "每行高度 (Line Height):", 'MUTATOR_ALERT_LINE_HEIGHT', 'spin', max=200)
      parent.add_row(gl_layout, "字体大小 (Font Size):", 'MUTATOR_ALERT_FONT_SIZE', 'spin', max=100)
      parent.add_row(gl_layout, "图标透明度:", 'MUTATOR_ICON_TRANSPARENCY', 'double')
      label_hint = QLabel("以下填入的是占窗口大小的比例的位移,数字越大越靠近右/下")
      label_hint.setStyleSheet("color: gray; font-size: 10pt; font-style: italic;")
      gl_layout.addRow(label_hint)
      
      parent.add_row(gl_layout, "距离顶部 (Y Offset):", 'MUTATOR_ALERT_OFFSET_Y', 'spin', max=2000)
      parent.add_row(gl_layout, "距离左侧 (X Offset):", 'MUTATOR_ALERT_OFFSET_X', 'spin', max=3000)
      layout.addRow(gb_layout)

      scroll.setWidget(content)
      parent.tabs.addTab(scroll, "因子提醒")

  @staticmethod
  def create_hotkey_tab(parent):
      tab = QWidget()
      layout = QFormLayout()
      
      parent.add_row(layout, "地图切换快捷键:", 'MAP_SHORTCUT', 'hotkey')
      parent.add_row(layout, "锁定窗口快捷键:", 'LOCK_SHORTCUT', 'hotkey')
      parent.add_row(layout, "截图快捷键:", 'SCREENSHOT_SHORTCUT', 'hotkey')
      parent.add_row(layout, "笔记临时显示:", 'MEMO_TEMP_SHORTCUT', 'hotkey')
      parent.add_row(layout, "笔记开关显示:", 'MEMO_TOGGLE_SHORTCUT', 'hotkey')
      parent.add_row(layout, "自定义倒计时菜单:", 'COUNTDOWN_SHORTCUT', 'hotkey')
      
      tab.setLayout(layout)
      parent.tabs.addTab(tab, "快捷键")

  @staticmethod
  def create_general_rec_tab(parent):
      """图像识别设置标签页"""
      scroll = QScrollArea()
      scroll.setWidgetResizable(True)
      content = QWidget()
      layout = QFormLayout(content)
      
      layout.addRow(QLabel("<b>[ 高级设置 ] 修改此处可能导致识别失效...</b>"))
      
      # 种族因子识别区
      gb_icon = QGroupBox("种族/因子识别区域")
      gl_icon = QFormLayout(gb_icon)
      parent.add_row(gl_icon, "因子识别区域:", 'MUTATOR_AND_ENEMY_RACE_RECOGNIZER_ROI', 'roi')
      parent.add_row(gl_icon, "AI 种族识别区域:", 'ENEMY_COMP_RECOGNIZER_ROI', 'roi')
      layout.addRow(gb_icon)
      
      # 净网行动多语言 ROI - 注意这里现在正确调用了类方法
      gb_mw = QGroupBox("净网行动多语言识别区域 (ROI)")
      mw_layout = QVBoxLayout(gb_mw)
      roi_tabs = SettingsTabsBuilder.create_roi_tabs(parent) # 调用类方法创建 ROI 编辑器的标签页
      mw_layout.addWidget(roi_tabs)
      layout.addRow(gb_mw)

      # 偏移量
      parent.add_row(layout, "单英雄时坐标偏移:", 'MALWARFARE_HERO_OFFSET', 'spin')
      parent.add_row(layout, "原生双雄时坐标偏移:", 'MALWARFARE_ZWEIHAKA_OFFSET', 'spin')
      parent.add_row(layout, "录像播放时坐标偏移:", 'MALWARFARE_REPLAY_OFFSET', 'spin')
      
      scroll.setWidget(content)
      parent.tabs.addTab(scroll, "识别设置")

  @staticmethod
  def create_roi_tabs(parent):
      """[类方法] 创建中英双语 ROI 编辑器"""
      roi_tab_widget = QTabWidget()
      parent.roi_widgets = {} 

      # 从副本读取数据，确保“取消”逻辑生效
      current_roi = parent.current_config.get('MALWARFARE_ROI', getattr(config, 'MALWARFARE_ROI', {}))

      for lang in ['zh', 'en']:
          page = QWidget()
          layout = QFormLayout(page)
          parent.roi_widgets[lang] = {}
          regions = {'purified_count': '净化节点', 'time': '时间', 'paused': '暂停标识'}
          
          for key, label in regions.items():
              val = current_roi.get(lang, {}).get(key, ((0,0),(0,0)))
              (x1, y1), (x2, y2) = val
              roi_data = parent.create_roi_widget(x1, y1, x2, y2)
              parent.roi_widgets[lang][key] = roi_data['spins']
              layout.addRow(label, roi_data['box'])
              
          roi_tab_widget.addTab(page, "中文 (ZH)" if lang == 'zh' else "英文 (EN)")
      return roi_tab_widget

  @staticmethod
  def create_data_management_tab(parent):
      """Excel 数据备份与恢复"""
      tab = QWidget()
      layout = QVBoxLayout(tab)
      
      # 地图数据组
      map_gb = QGroupBox("地图配置管理")
      m_layout = QHBoxLayout(map_gb)
      btn_exp = QPushButton("导出全部地图配置"); btn_imp = QPushButton("导入 Excel 配置")
      
      # 导出逻辑：需要从数据库获取全量数据
      btn_exp.clicked.connect(lambda: parent.on_export_data('map'))
      btn_imp.clicked.connect(lambda: parent.on_import_excel('map'))
      
      m_layout.addWidget(btn_exp); m_layout.addWidget(btn_imp)
      layout.addWidget(map_gb)
      layout.addStretch()
      parent.tabs.addTab(tab, "数据管理")