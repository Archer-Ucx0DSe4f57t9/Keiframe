#settings_window.py
import json
import os, sys
import copy
import re
from PyQt5 import QtCore 
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, 
                             QLabel, QLineEdit, QSpinBox, QDoubleSpinBox, 
                             QCheckBox, QPushButton, QColorDialog, QMessageBox, 
                             QFormLayout, QScrollArea, QDialog, QComboBox, QGroupBox,
                             QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QKeyEvent, QColor, QKeySequence

from src import config  # 导入你现有的 config.py 作为默认值
from src.utils.logging_util import get_logger
from src.utils.fileutil import get_resources_dir, get_project_root
from src.utils.excel_utils import ExcelUtil
from src.utils.data_validator import DataValidator
from src.db import map_daos, mutator_daos
from src.settings_window.widgets import HotkeyInput, ColorInput
from src.settings_window.complex_inputs import DictInput, DictTable, CountdownOptionsInput, CountdownOptionsInput  
from src.settings_window.tabs import SettingsTabsBuilder
from src.settings_window.setting_data_handler import SettingsHandler

      
      
# ==========================================
# 2. 设置窗口主类
# ==========================================
class SettingsWindow(QDialog):
    settings_saved = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings_file = os.path.join(get_project_root(), 'settings.json')
        self.data_handler = SettingsHandler(
            self.settings_file,
            maps_db=parent.maps_db if parent else None, 
            mutators_db=parent.mutators_db if parent else None)
        self.main_window = parent
        self.setWindowTitle("系统设置 / Settings")
        self.resize(900, 700)
        
        self.logger = get_logger("setting window")
        
        self.current_config = self.data_handler.load_config()
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

    def init_ui(self):
        main_layout = QVBoxLayout()
        self.tabs = QTabWidget()
        
        builder = SettingsTabsBuilder()
        builder.create_general_tab(self)       # 1. 常规设置
        builder.create_interface_tab(self)     # 2. 界面与显示
        builder.create_map_settings_tab(self)  # 3. 地图提醒 (Map Config)
        builder.create_mutation_settings_tab(self) # 4. 因子提示配置 (Mutation Config)
        builder.create_hotkey_tab(self)        # 5. 快捷键
        builder.create_general_rec_tab(self)   # 6. 图像设置
        builder.create_data_management_tab(self) # 7. 数据管理
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

    def _collect_roi_data(self):
        """
        遍历存储在 self.roi_widgets 中的 QSpinBox，
        将其转换为嵌套字典格式：{lang: {region: ((x1, y1), (x2, y2))}}
        """
        nested_roi = {}
        for lang in ['zh', 'en']:
            nested_roi[lang] = {}
            # self.roi_widgets 在 tabs.py 的 create_roi_tabs 中被初始化
            if lang in self.roi_widgets:
                for region, spins in self.roi_widgets[lang].items():
                    # spins 是 [QSpinBox(x1), QSpinBox(y1), QSpinBox(x2), QSpinBox(y2)]
                    nested_roi[lang][region] = (
                        (spins[0].value(), spins[1].value()), 
                        (spins[2].value(), spins[3].value())
                    )
        return nested_roi

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

    def on_import_excel(self, config_type):
        """导入 Excel 配置，调用 SettingsHandler 进行验证和处理"""
        path, _ = QFileDialog.getOpenFileName(self, "选择 Excel 文件", "", "Excel Files (*.xlsx)")
        if not path: return

        # 调用 handler 的验证导入逻辑
        success, result = self.data_handler.validate_and_import(path, config_type)

        if success:
            QMessageBox.information(self, "导入成功", result)
        else:
            # 如果验证失败，弹出详细的错误列表
            error_msg = "\n".join(result[:15]) # 最多显示15条错误
            if len(result) > 15:
                error_msg += f"\n... 以及其他 {len(result)-15} 个错误"
            
            QMessageBox.warning(self, "导入校验失败", f"发现数据问题，请修正：\n\n{error_msg}")

    def on_export_data(self, config_type):
        """将数据库中的配置导出为 Excel"""
        path, _ = QFileDialog.getSaveFileName(self, "选择保存位置", f"export_{config_type}.xlsx", "Excel Files (*.xlsx)")
        if not path: return

        try:
            all_data = []
            if config_type == 'map':
                conn = self.main_window.maps_db
                for name in map_daos.get_all_map_names(conn):
                    rows = map_daos.load_map_by_name(conn, name)
                    for r in rows:
                        all_data.append({
                            'map_name': r['map_name'],
                            'time_label': r['time']['label'],
                            'count_value': r['count'],
                            'event_text': r['event'],
                            'army_text': r['army'],
                            'sound_filename': r['sound'],
                            'hero_text': r['hero']
                        })
                ExcelUtil.export_configs(all_data, path, 'map')
            # 此处可继续添加 mutator 的导出逻辑...
            QMessageBox.information(self, "成功", f"数据已成功导出至: {path}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导出失败: {str(e)}")
    
    def on_save(self):
        """保存配置：修复了数据分流顺序以及窗口驻留逻辑"""
        # 强制清除表格焦点，确保正在编辑的单元格内容被提交
        if self.focusWidget():
            self.focusWidget().clearFocus()

        # 1. 收集 UI 上的完整数据包
        new_values = self.get_ui_values()
        new_values['MALWARFARE_ROI'] = self._collect_roi_data() 
        
        # 2. 生成报告（此时 new_values 包含 MAP_SEARCH_KEYWORDS，对比才有效）
        changes = self._generate_changes_report(new_values)

        if not changes:
            QMessageBox.information(self, "提示", "没有检测到任何修改，请修改后再保存或点击取消。")
            return # 【修复】不再调用 self.accept()，窗口保持打开

        # 3. 弹出确认框
        reply = QMessageBox.question(self, "确认修改", 
                                    "检测到以下修改，确认保存吗？\n\n" + "\n".join(changes[:10]) + 
                                    ("\n..." if len(changes)>10 else ""), 
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            # 4. 【数据分流】：分出关键词交给数据库，剩下的进 JSON
            keywords = None
            if 'MAP_SEARCH_KEYWORDS' in new_values:
                keywords = new_values.pop('MAP_SEARCH_KEYWORDS')

            # 坐标项拆分 (X/Y 处理)
            self.normalize_config(new_values)
            
            # 5. 执行物理保存
            success, msg = self.data_handler.save_all(new_values, keywords)
            if success:
                QMessageBox.information(self, "保存成功", msg)
                self.settings_saved.emit(new_values)
                self.accept() # 只有成功保存才关闭
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
                # 获取旧值（优先从 original_config 拿，拿不到去 config.py 捞）
                old_value = self.original_config.get(key)
                if old_value is None:
                    old_value = getattr(config, key, None)
                
                # 标准化数据进行对比，消除 [[]] 和 (()) 的差异
                norm_old = self._normalize_data(old_value)
                norm_new = self._normalize_data(new_value)
                
                if norm_old != norm_new:
                    # --- 情况 1：处理 ROI 嵌套字典的细分报告 ---
                    if key == 'MALWARFARE_ROI':
                        old_roi = old_value if isinstance(old_value, dict) else {}
                        new_roi = new_value if isinstance(new_value, dict) else {}
                        for lang in ['zh', 'en']:
                            o_lang = old_roi.get(lang, {})
                            n_lang = new_roi.get(lang, {})
                            for reg, label in region_map.items():
                                # 内部对比也需标准化
                                if self._normalize_data(o_lang.get(reg)) != self._normalize_data(n_lang.get(reg)):
                                    l_name = lang_map.get(lang, lang)
                                    report.append(f"【ROI-{l_name}】{label}: {o_lang.get(reg)} -> {n_lang.get(reg)}")

                    # --- 情况 2：【重点】详细处理别名映射的字典变动 ---
                    elif key == 'MAP_SEARCH_KEYWORDS':
                        added = set(norm_new.keys()) - set(norm_old.keys())
                        removed = set(norm_old.keys()) - set(norm_new.keys())
                        common = set(norm_old.keys()) & set(norm_new.keys())
                        
                        if added: report.append(f"【别名映射】新增: {list(added)}")
                        if removed: report.append(f"【别名映射】删除: {list(removed)}")
                        for k in common:
                            if norm_old[k] != norm_new[k]:
                                report.append(f"【别名映射】修改 '{k}': {norm_old[k]} -> {norm_new[k]}")

                    # --- 情况 3：处理所有其他普通配置项 ---
                    else:
                        label = self.widgets.get(key, {}).get('label', key)
                        report.append(f"【{label}】: {old_value} -> {new_value}")

            return report
# 独立运行测试
if __name__ == '__main__':
    import sys
    from PyQt5.QtWidgets import QApplication
    app = QApplication(sys.argv)
    win = SettingsWindow()
    win.show()
    sys.exit(app.exec_())