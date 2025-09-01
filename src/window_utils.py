import win32gui
import win32con
import win32api

from logging_util import get_logger

logger = get_logger('window_utils')
hwnd = win32gui.FindWindow(None, "StarCraft II")


#获取窗口内容区的左上角和坐标
def get_sc2_window_geometry() -> object:
    try:
        if hwnd:
            # 内容区大小（如果为窗口模式不含边框+标题栏）
            content_rect = win32gui.GetClientRect(hwnd)
            
            content_left_top = win32gui.ClientToScreen(hwnd, (content_rect[0], content_rect[1]))
            content_right_bottom = win32gui.ClientToScreen(hwnd, (content_rect[2], content_rect[3]))
            
            x = content_left_top[0]
            y = content_left_top[1]
            w = content_right_bottom[0] - x
            h = content_right_bottom[1] - y
            return x, y, w, h
    except Exception as e:
        logger.info(f"获取'StarCraft II'窗口几何信息失败: {e}")
    return None

#判断是不是全屏游戏
def is_sc2_fullscreen():
    # 获取窗口矩形
    rect = win32gui.GetWindowRect(hwnd)  # (left, top, right, bottom)
    win_width = rect[2] - rect[0]
    win_height = rect[3] - rect[1]

    # 获取屏幕分辨率
    screen_width = win32api.GetSystemMetrics(0)
    screen_height = win32api.GetSystemMetrics(1)

    # 判断是否和屏幕一样大
    return win_width == screen_width and win_height == screen_height

#判断是不是无边框窗口，以标题栏为准
def get_window_style():
    
    style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)

    has_titlebar = bool(style & win32con.WS_CAPTION)#有没有标题栏
    #has_minbox   = bool(style & win32con.WS_MINIMIZEBOX)#有没有最小化
    #has_maxbox   = bool(style & win32con.WS_MAXIMIZEBOX)#有没有最大化
    #has_sysmenu  = bool(style & win32con.WS_SYSMENU)#有没有关闭按钮

    return has_titlebar

