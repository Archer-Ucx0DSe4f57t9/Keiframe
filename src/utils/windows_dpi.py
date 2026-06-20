import ctypes
import os
import sys


_DPI_AWARENESS_MODE = None


def configure_qt_fixed_pixel_environment():
    """在导入 PyQt 前关闭 Qt 自动 UI 缩放。"""
    for key in (
        "QT_DEVICE_PIXEL_RATIO",
        "QT_SCALE_FACTOR",
        "QT_FONT_DPI",
    ):
        os.environ.pop(key, None)

    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "0"
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"


def configure_process_dpi() -> str:
    """
    将进程设置为 DPI aware，让 Win32 和 Qt 窗口坐标使用桌面物理像素。
    可以安全重复调用。
    """
    global _DPI_AWARENESS_MODE
    if _DPI_AWARENESS_MODE is not None:
        return _DPI_AWARENESS_MODE

    if not sys.platform.startswith("win"):
        _DPI_AWARENESS_MODE = "not_windows"
        return _DPI_AWARENESS_MODE

    try:
        awareness_context = ctypes.c_void_p(-4)  # 每显示器 DPI 感知 V2
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(awareness_context):
            _DPI_AWARENESS_MODE = "per_monitor_v2"
            return _DPI_AWARENESS_MODE
    except Exception:
        pass

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # 每显示器 DPI 感知
        _DPI_AWARENESS_MODE = "per_monitor_v1"
        return _DPI_AWARENESS_MODE
    except Exception:
        pass

    try:
        ctypes.windll.user32.SetProcessDPIAware()
        _DPI_AWARENESS_MODE = "system_dpi_aware"
        return _DPI_AWARENESS_MODE
    except Exception:
        _DPI_AWARENESS_MODE = "failed"
        return _DPI_AWARENESS_MODE


def get_system_dpi():
    if not sys.platform.startswith("win"):
        return None

    try:
        return int(ctypes.windll.user32.GetDpiForSystem())
    except Exception:
        pass

    try:
        hdc = ctypes.windll.user32.GetDC(0)
        try:
            return int(ctypes.windll.gdi32.GetDeviceCaps(hdc, 88))  # 水平 DPI
        finally:
            ctypes.windll.user32.ReleaseDC(0, hdc)
    except Exception:
        return None


def get_dpi_for_window(hwnd):
    if not sys.platform.startswith("win") or not hwnd:
        return None

    try:
        return int(ctypes.windll.user32.GetDpiForWindow(int(hwnd)))
    except Exception:
        return None
