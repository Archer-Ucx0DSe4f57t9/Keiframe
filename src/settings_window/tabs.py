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
        
        parent.add_row(layout, "当前游戏语言 (Game Language):", 'current_game_language', 'combo', items=['zh', 'en'])
        
        gb = QGroupBox("日志与调试设置 (Logging & Debugging)")
        gl = QFormLayout(gb)
        parent.add_row(gl, "日志等级:", 'LOG_LEVEL', 'combo', items=['DEBUG', 'INFO', 'WARNING', 'ERROR'])
        parent.add_row(gl, "调试模式:", 'debug_mode', 'bool')
        parent.add_row(gl, "调试倍率:", 'debug_time_factor', 'double', min=0.1, max=20.0)
        layout.addRow(gb)
        
        # 声音配置整合在此或地图配置中，此处放入通用区域
        sb = QGroupBox("提示声音设置(Alert Sound Settings)")
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
        
        # 4. 自定义倒计时配置
        gb_cd = QGroupBox("自定义倒计时 (Custom Countdown)")
        gl_cd = QFormLayout(gb_cd)
        parent.add_row(gl_cd, "最大同时存在数量:", 'COUNTDOWN_MAX_CONCURRENT', 'spin', min=1, max=10)
        parent.add_row(gl_cd, "警告时间 (秒):", 'COUNTDOWN_WARNING_THRESHOLD_SECONDS', 'spin')
        parent.add_row(gl_cd, "显示颜色:", 'COUNTDOWN_DISPLAY_COLOR', 'color')
        
        # 使用新的倒计时列表编辑器
        parent.add_row(gl_cd, "倒计时选项列表:", 'COUNTDOWN_OPTIONS', 'countdown_list')
        layout.addRow(gb_cd)

        tab.setLayout(layout)
        parent.tabs.addTab(tab, "界面显示")

    @staticmethod
    def create_map_settings_tab(parent):
        """地图与倒计时标签页"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QFormLayout(content)

        # 1. 地图事件逻辑
        gb_alert = QGroupBox("地图事件倒计时设置(Map Event Countdown)")
        gl_alert = QFormLayout(gb_alert)
        SettingsTabsBuilder._add_compact_row(parent, gl_alert, "时间设定 (秒):", [
                ("提示时间:", 'MAP_ALERT_SECONDS', 'spin', {}),
                ("警告时间:", 'MAP_ALERT_WARNING_THRESHOLD_SECONDS', 'spin', {})
            ])
        parent.add_row(gl_alert, "正常文本颜色:", 'MAP_ALERT_NORMAL_COLOR', 'color')
        parent.add_row(gl_alert, "警告文本颜色:", 'MAP_ALERT_WARNING_COLOR', 'color')
        layout.addRow(gb_alert)

        # 2. 提示框通用布局 (Toast Layout)
        gb_layout = QGroupBox("地图事件提示位置设置 (Map Event Toast Layout)")
        gl_layout = QFormLayout(gb_layout)
        hint = QLabel("游戏画面左上角为基准点(0,0),数字越大越靠近右/下")
        hint.setStyleSheet("color: gray; font-size: 10pt; font-style: italic;")
        gl_layout.addRow(hint)
        SettingsTabsBuilder._add_compact_row(parent, gl_layout, "坐标偏移:", [
            ("左侧 (X):", 'TOAST_OFFSET_X', 'spin', {'max': 3000}),
            ("顶部 (Y):", 'TOAST_OFFSET_Y', 'spin', {'max': 2000})
        ])
        SettingsTabsBuilder._add_compact_row(parent, gl_layout, "字体布局:", [
            ("行高:", 'TOAST_LINE_HEIGHT', 'spin', {'max': 200}),
            ("字号:", 'TOAST_FONT_SIZE', 'spin', {'max': 100})
        ])
        layout.addRow(gb_layout)

        # 3. 搜索关键词
        parent.add_row(layout, "地图搜索别名映射:", 'MAP_SEARCH_KEYWORDS', 'dict')

        scroll.setWidget(content)
        parent.tabs.addTab(scroll, "地图提醒")
        

    @staticmethod
    def create_mutation_settings_tab(parent):
        """因子提示配置标签页"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QFormLayout(content)

        # 1. 倒计时
        gb_alert = QGroupBox("突变因子倒计时设置 (Mutation Countdown)")
        gl_alert = QFormLayout(gb_alert)
        SettingsTabsBuilder._add_compact_row(parent, gl_alert, "时间设定 (秒):", [
            ("提示时间:", 'MUTATOR_ALERT_SECONDS', 'spin', {}),
            ("警告时间:", 'MUTATOR_WARNING_THRESHOLD_SECONDS', 'spin', {})
        ])
        parent.add_row(gl_alert, "正常文本颜色:", 'MUTATOR_NORMAL_COLOR', 'color')
        parent.add_row(gl_alert, "警告文本颜色:", 'MUTATOR_WARNING_COLOR', 'color')
        layout.addRow(gb_alert)

        # 3. 提示布局
        gb_layout = QGroupBox("因子图标消息设置 (Icon & Text Layout)")
        gl_layout = QFormLayout(gb_layout)
        label_hint = QLabel("游戏画面左上角为基准点(0,0),数字越大越靠近右/下")
        label_hint.setStyleSheet("color: gray; font-size: 10pt; font-style: italic;")
        gl_layout.addRow(label_hint)
        SettingsTabsBuilder._add_compact_row(parent, gl_layout, "坐标偏移:", [
            ("左侧 (X):", 'MUTATOR_ALERT_OFFSET_X', 'spin', {'max': 3000}),
            ("顶部 (Y):", 'MUTATOR_ALERT_OFFSET_Y', 'spin', {'max': 2000})
        ])
        SettingsTabsBuilder._add_compact_row(parent, gl_layout, "字体布局:", [
            ("行高:", 'MUTATOR_ALERT_LINE_HEIGHT', 'spin', {'max': 200}),
            ("字号:", 'MUTATOR_ALERT_FONT_SIZE', 'spin', {'max': 100})
        ])
        parent.add_row(gl_layout, "图标透明度:", 'MUTATOR_ICON_TRANSPARENCY', 'double')
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
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # 1. 顶部导入导出按钮组
        io_gb = QGroupBox("数据备份与恢复 (Excel)")
        io_layout = QHBoxLayout(io_gb)
        for t, label in [('map', '地图配置'), ('mutator', '突变因子')]:
            btn_exp = QPushButton(f"导出{label}")
            btn_imp = QPushButton(f"导入{label}")
            btn_exp.clicked.connect(lambda _, x=t: parent.on_export_data(x))
            btn_imp.clicked.connect(lambda _, x=t: parent.on_import_excel(x))
            io_layout.addWidget(btn_exp)
            io_layout.addWidget(btn_imp)
        layout.addWidget(io_gb)

        # --- 2. 背板数据查看/编辑区 ---
        view_gb = QGroupBox("背板数据在线编辑")
        view_layout = QVBoxLayout(view_gb)
        
        # 二级联动下拉框
        sel_layout = QHBoxLayout()
        type_combo = QComboBox(); type_combo.addItems(["地图 (Map)", "突变因子 (Mutator)"])
        name_combo = QComboBox()
        sel_layout.addWidget(QLabel("类型:")); sel_layout.addWidget(type_combo)
        sel_layout.addWidget(QLabel("目标:")); sel_layout.addWidget(name_combo)
        sel_layout.addStretch()
        view_layout.addLayout(sel_layout)

        # 数据表格
        from src.settings_window.complex_inputs import UniversalConfigTable
        data_table = UniversalConfigTable()
        view_layout.addWidget(data_table)

        # 编辑按钮组
        edit_btn_layout = QHBoxLayout()
        add_btn = QPushButton("添加行"); del_btn = QPushButton("删除行")
        save_db_btn = QPushButton("同步到数据库 (Save to DB)")
        save_db_btn.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold;")
        
        edit_btn_layout.addWidget(add_btn); edit_btn_layout.addWidget(del_btn)
        edit_btn_layout.addStretch()
        edit_btn_layout.addWidget(save_db_btn)
        view_layout.addLayout(edit_btn_layout)
        layout.addWidget(view_gb)

        # --- 3. 逻辑绑定 ---
        def on_type_changed():
            name_combo.clear()
            is_map = type_combo.currentIndex() == 0
            is_mutator =type_combo.currentIndex() == 1
            res = parent.data_handler.get_names_by_type('map' if is_map else 'mutator')
            if is_map: name_combo.addItems(res)
            else:
                for raw, chs in res: name_combo.addItem(chs, raw)
            on_name_changed()

        def on_name_changed():
            is_map = type_combo.currentIndex() == 0
            is_mutator =type_combo.currentIndex() == 1
            config_type = 'map' if is_map else 'mutator'
            raw_name = name_combo.currentText() if is_map else name_combo.currentData()
            
            if raw_name:
                data = parent.data_handler.get_data_by_name(config_type, raw_name)
                # 修复报错：传入注册表字典
                data_table.update_table(config_type, data, raw_name, parent.data_handler.BACKPLANE_REGISTRY)

        def do_save_to_db():
            is_map = type_combo.currentIndex() == 0
            is_mutator =type_combo.currentIndex() == 1
            cfg_type = 'map' if is_map else 'mutator'
            raw_name = name_combo.currentText() if is_map else name_combo.currentData()
            try:
                # 1. 这里会触发正则校验
                table_data = data_table.get_table_data()
                
                # 2. 如果校验通过，执行保存
                success, msg = parent.data_handler.save_backplane_to_db(cfg_type, raw_name, table_data)
                if success:
                    QMessageBox.information(parent, "成功", msg)
                else:
                    QMessageBox.critical(parent, "错误", msg)
                    
            except ValueError as e:
                # 捕获正则校验失败的错误
                QMessageBox.warning(parent, "格式错误", str(e))
            except Exception as e:
                QMessageBox.critical(parent, "系统错误", f"同步异常: {str(e)}")

        # 信号连接
        type_combo.currentIndexChanged.connect(on_type_changed)
        name_combo.currentIndexChanged.connect(on_name_changed)
        add_btn.clicked.connect(data_table.add_new_row)
        del_btn.clicked.connect(data_table.remove_selected_row)
        save_db_btn.clicked.connect(do_save_to_db)

        on_type_changed() # 初始加载
        parent.tabs.addTab(tab, "背板信息")
      
    ''''辅助函数合集'''
    @staticmethod
    def _create_widget_only(parent, key, widget_type, label_text, **kwargs):
        """内部工具：仅创建并注册控件，不添加到布局，供组合行使用"""
        val = parent.current_config.get(key)
        widget = None
        
        if widget_type == 'spin':
            widget = QSpinBox()
            widget.setRange(kwargs.get('min', 0), kwargs.get('max', 9999))
            widget.setValue(int(val) if val is not None else 0)
        elif widget_type == 'double':
            widget = QDoubleSpinBox()
            widget.setRange(kwargs.get('min', 0.0), kwargs.get('max', 1.0))
            widget.setSingleStep(kwargs.get('step', 0.01))
            widget.setValue(float(val) if val is not None else 0.0)
        
        if widget:
            # 禁用滚轮并注册到主窗口的 widgets 字典，确保保存逻辑生效
            widget.setFocusPolicy(QtCore.Qt.StrongFocus)
            widget.installEventFilter(parent)
            parent.widgets[key] = {'widget': widget, 'type': widget_type, 'label': label_text}
        return widget

    @staticmethod
    def _add_compact_row(parent, layout, row_label, items):
        """将多个控件放入一行 QFormLayout"""
        container = QWidget()
        h_layout = QHBoxLayout(container)
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(10)

        for label, key, w_type, kwargs in items:
            h_layout.addWidget(QLabel(label))
            widget = SettingsTabsBuilder._create_widget_only(parent, key, w_type, label, **kwargs)
            if widget:
                h_layout.addWidget(widget)
        
        h_layout.addStretch()
        layout.addRow(row_label, container)