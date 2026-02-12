#complex_inputs.py
# 这个文件定义了设置界面中使用的复杂输入控件，如快捷键输入框和颜色选择器
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QPushButton, QComboBox, QSpinBox, QHeaderView
from src.utils.fileutil import get_resources_dir
import os


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