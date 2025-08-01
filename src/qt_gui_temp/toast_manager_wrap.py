from toast_manager import ToastManager

def init_toast(self):
        """初始化Toast提示组件"""
        self.toast_manager = ToastManager(self)

def show_toast(self, message, duration=None, force_show=False):
    """显示Toast提示"""
    self.toast_manager.show_map_toast(message, duration, force_show)

def hide_toast(self):
    """隐藏Toast提示"""
    self.toast_manager.hide_toast()