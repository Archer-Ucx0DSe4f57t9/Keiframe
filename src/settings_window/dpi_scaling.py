import re

from src.utils.windows_dpi import get_dpi_for_window, get_system_dpi


def get_settings_window_dpi(parent_window=None) -> int:
    """从已存在的父主窗口读取 DPI；没有父窗口时退回系统 DPI。"""
    if parent_window is not None:
        try:
            dpi = get_dpi_for_window(int(parent_window.winId()))
            if dpi and dpi > 0:
                return int(dpi)
        except Exception:
            pass

    dpi = get_system_dpi()
    if dpi and dpi > 0:
        return int(dpi)

    return 96


def get_settings_window_dpi_scale(parent_window=None):
    """返回设置窗口手动缩放使用的 DPI 和相对 96 DPI 的比例。"""
    dpi = get_settings_window_dpi(parent_window)
    return dpi, max(1.0, float(dpi) / 96.0)


def scale_px(value, scale: float) -> int:
    """按设置窗口 DPI 缩放一个像素值。"""
    return int(round(float(value) * float(scale)))


def scale_qss_px(qss: str, scale: float) -> str:
    """缩放 QSS 中显式写出的 px 数值。"""
    if not qss or abs(scale - 1.0) < 0.001:
        return qss

    def repl(match):
        raw_value = float(match.group(1))
        return f"{scale_px(raw_value, scale)}px"

    return re.sub(r"(-?\d+(?:\.\d+)?)px", repl, qss)