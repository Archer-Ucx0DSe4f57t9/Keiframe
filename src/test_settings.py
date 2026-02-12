import sys
import os
from PyQt5.QtWidgets import QApplication
from src.settings_window.settings_window import SettingsWindow

# 1. 模拟一个 MockMainWindow
class MockMainWindow:
    def __init__(self):
        # 模拟设置窗口需要的数据库连接
        self.maps_db = None # 如果需要真实测试，可以连一个测试用的 :memory: 数据库
        self.mutators_db = None
        
    def x(self): return 100 # 模拟主窗口位置获取
    def y(self): return 100

def test_ui_integration():
    app = QApplication(sys.argv)
    
    # 实例化模拟的主窗口
    mock_parent = MockMainWindow()
    
    # 启动设置窗口
    win = SettingsWindow(parent=mock_parent)
    
    # --- 自动化操作模拟 ---
    # 模拟用户切换 Tab
    win.tabs.setCurrentIndex(1) # 切换到“界面显示”
    
    # 模拟用户修改主窗口宽度
    if 'MAIN_WINDOW_WIDTH' in win.widgets:
        spin_box = win.widgets['MAIN_WINDOW_WIDTH']['widget']
        spin_box.setValue(500)
        print(f"模拟修改宽度为: {spin_box.value()}")

    # 模拟点击保存按钮
    # win.on_save() 
    
    win.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    test_ui_integration()