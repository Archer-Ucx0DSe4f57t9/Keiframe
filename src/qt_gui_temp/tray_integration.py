from tray_manager import TrayManager

def init_tray(self):
    """初始化系统托盘"""
    self.tray_manager = TrayManager(self)