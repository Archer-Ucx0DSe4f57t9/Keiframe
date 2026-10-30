import win32gui
import win32con
import win32api

from src.utils.game_viewport import centered_aspect_crop
from src.utils.logging_util import get_logger

logger = get_logger('window_utils')

class WindowHandleManager:
    
    def __init__(self, titles=["StarCraft II", "《星际争霸II》"]):

        self.titles = titles
        self.cached_hwnd = None

    def _find_window(self):
        for title in self.titles:
            hwnd = win32gui.FindWindow(None, title)
            if hwnd:
                return hwnd
        return None

    def get_hwnd(self):
        if self.cached_hwnd:
            if win32gui.IsWindow(self.cached_hwnd):
                return self.cached_hwnd
        new_hwnd = self._find_window()
        self.cached_hwnd = new_hwnd
        return new_hwnd

manager = WindowHandleManager()


def get_sc2_client_geometry():
    """获取 SC2 原始客户区在桌面上的物理像素坐标。"""
    hwnd = manager.get_hwnd()
    try:
        if hwnd:
            content_rect = win32gui.GetClientRect(hwnd)
            content_left_top = win32gui.ClientToScreen(hwnd, (content_rect[0], content_rect[1]))
            content_right_bottom = win32gui.ClientToScreen(hwnd, (content_rect[2], content_rect[3]))

            x = content_left_top[0]
            y = content_left_top[1]
            w = content_right_bottom[0] - x
            h = content_right_bottom[1] - y
            return x, y, w, h
    except Exception as e:
        logger.warning(f"获取'星际争霸2'客户区几何信息失败: {e}")
    return None


def get_sc2_window_geometry():
    """
    获取供识别和覆盖层使用的 16:9 游戏视口。

    真全屏时 Windows 会把 SC2 客户区暴露为游戏分辨率（例如
    2560x1440），因此这里会原样返回。无边框或窗口化运行在带鱼屏时，
    则返回客户区正中央的 16:9 区域，自动排除两侧区域。
    """
    client_geometry = get_sc2_client_geometry()
    if not client_geometry:
        return None

    viewport = centered_aspect_crop(client_geometry)
    return viewport.as_tuple() if viewport else None


def is_sc2_fullscreen():
    hwnd = manager.get_hwnd()
    if not hwnd:
        return False

    try:
        rect = win32gui.GetWindowRect(hwnd)
        monitor = _get_monitor_rect(hwnd)
        if not monitor:
            return False

        # 独占全屏会改变显示模式；此时 MonitorFromWindow 返回的正是
        # 游戏分辨率。使用所在显示器而不是主屏幕可兼容多显示器。
        tolerance = 2
        return all(
            abs(actual - expected) <= tolerance
            for actual, expected in zip(rect, monitor)
        )
    except Exception as e:
        logger.warning(f"判断'星际争霸2'全屏状态失败: {e}")
        return False


def get_sc2_monitor_geometry():
    """Return the desktop rectangle of the monitor currently hosting SC2."""
    hwnd = manager.get_hwnd()
    if not hwnd:
        return None
    try:
        return _get_monitor_rect(hwnd)
    except Exception as e:
        logger.warning(f"获取'星际争霸2'所在显示器失败: {e}")
        return None


def _get_monitor_rect(hwnd):
    """返回指定窗口所在显示器的桌面矩形。"""
    monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
    if not monitor:
        return None
    info = win32api.GetMonitorInfo(monitor)
    return tuple(info["Monitor"])

#判断是不是无边框窗口，以标题栏为准
def get_window_style():
    hwnd = manager.get_hwnd()
    if not hwnd:
        return False
    style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)

    has_titlebar = bool(style & win32con.WS_CAPTION)#有没有标题栏
    #has_minbox   = bool(style & win32con.WS_MINIMIZEBOX)#有没有最小化
    #has_maxbox   = bool(style & win32con.WS_MAXIMIZEBOX)#有没有最大化
    #has_sysmenu  = bool(style & win32con.WS_SYSMENU)#有没有关闭按钮

    return has_titlebar

#判断游戏窗口是否已经激活
def is_game_active() -> bool:
    hwnd = manager.get_hwnd()
    if not hwnd:
        return False
    # 1. 获取当前前景窗口的句柄
    foreground_hwnd = win32gui.GetForegroundWindow()

    # 2. 检查窗口是否最小化
    # IsIconic 函数用于判断窗口是否最小化
    is_minimized = win32gui.IsIconic(hwnd)

    # 3. 检查窗口是否可见
    # isWindowVisible 函数用于判断窗口是否可见（不是隐藏状态）
    # 注意：即使窗口被其他窗口完全遮挡，只要它没有被设置为隐藏，这个函数也会返回 True
    is_visible = win32gui.IsWindowVisible(hwnd)
    
    # 综合判断:
    # - 目标窗口必须是当前的前景窗口 (hwnd == foreground_hwnd)
    # - 目标窗口不能是最小化状态 (not is_minimized)
    # - 目标窗口本身是可见的 (is_visible)
    if hwnd == foreground_hwnd and not is_minimized and is_visible:
        return True
    else:
        return False
