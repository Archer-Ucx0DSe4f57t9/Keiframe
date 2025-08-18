import win32gui
from logging_util import get_logger

logger = get_logger('window_utils')

def get_sc2_window_geometry() -> object:
    try:
        hwnd = win32gui.FindWindow(None, "StarCraft II")
        if hwnd:
            rect = win32gui.GetWindowRect(hwnd)
            x = rect[0]
            y = rect[1]
            w = rect[2] - x
            h = rect[3] - y
            # print(f'found StarCraft II with {x}, {y}, {w}, {h}')
            return x, y, w, h
    except Exception as e:
        logger.error(f"获取'StarCraft II'窗口几何信息失败: {e}")
    return None
