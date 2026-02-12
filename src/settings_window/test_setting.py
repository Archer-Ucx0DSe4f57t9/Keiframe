import sys
import os
# 确保能找到 src 目录
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtWidgets import QApplication
from src.settings_window.settings_window import SettingsWindow
from src.db.db_manager import DBManager
from src.db import map_daos,mutator_daos
# 1. 模拟一个父窗口环境
class FakeMainWindow:
    def __init__(self):
        # 如果你有真实的测试数据库路径，填在这里；否则填 None
        self.db_manager = DBManager()
        # 获取数据库连接
        self.maps_db = self.db_manager.get_maps_conn()
        self.mutators_db = self.db_manager.get_mutators_conn()
    def x(self): return 100
    def y(self): return 100

def run_test():
    app = QApplication(sys.argv)
    
    # 2. 准备模拟环境
    parent = FakeMainWindow()
    
    # 3. 启动窗口
    demo = SettingsWindow(parent=parent)
    
    # --- 自动化测试指令 (可选) ---
    print(f"当前加载了 {len(demo.widgets)} 个配置项")
    
    # 模拟切换到第三个 Tab (地图设置)
    demo.tabs.setCurrentIndex(2)
    
    demo.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    run_test()