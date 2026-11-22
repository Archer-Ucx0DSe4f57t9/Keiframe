import sys

from src import config
from src.utils.windows_dpi import get_dpi_for_window, get_system_dpi


def dpi_debug_enabled() -> bool:
    return bool(getattr(config, "DPI_DEBUG_LOG", False))


def _rect_to_tuple(rect):
    if rect is None:
        return None
    return (rect.x(), rect.y(), rect.width(), rect.height())


def _win32_game_rects():
    if not sys.platform.startswith("win"):
        return None, None, None, None

    try:
        import win32gui
        from src.utils import window_utils

        hwnd = window_utils.manager.get_hwnd()
        if not hwnd:
            return None, None, None, None

        window_rect = win32gui.GetWindowRect(hwnd)
        client_rect = win32gui.GetClientRect(hwnd)
        client_left_top = win32gui.ClientToScreen(hwnd, (client_rect[0], client_rect[1]))
        client_right_bottom = win32gui.ClientToScreen(hwnd, (client_rect[2], client_rect[3]))
        client_on_screen = (
            client_left_top[0],
            client_left_top[1],
            client_right_bottom[0] - client_left_top[0],
            client_right_bottom[1] - client_left_top[1],
        )
        return hwnd, window_rect, client_rect, client_on_screen
    except Exception:
        return None, None, None, None


def log_startup_dpi(logger, awareness_mode, app):
    try:
        from PyQt5.QtCore import PYQT_VERSION_STR, QT_VERSION_STR

        logger.debug("DPI awareness mode: %s", awareness_mode)
        logger.debug("Qt binding and Qt version: PyQt5 %s / Qt %s", PYQT_VERSION_STR, QT_VERSION_STR)
        logger.debug("Windows system DPI: %s", get_system_dpi())
        logger.debug(
            "Qt high DPI env: QT_AUTO_SCREEN_SCALE_FACTOR=%s, QT_ENABLE_HIGHDPI_SCALING=%s, QT_SCALE_FACTOR=%s, QT_FONT_DPI=%s",
            __import__("os").environ.get("QT_AUTO_SCREEN_SCALE_FACTOR"),
            __import__("os").environ.get("QT_ENABLE_HIGHDPI_SCALING"),
            __import__("os").environ.get("QT_SCALE_FACTOR"),
            __import__("os").environ.get("QT_FONT_DPI"),
        )

        if dpi_debug_enabled():
            for screen in app.screens():
                logger.debug(
                    "Qt screen name=%s geometry=%s available=%s logicalDpi=%.2f physicalDpi=%.2f devicePixelRatioF=%.3f",
                    screen.name(),
                    _rect_to_tuple(screen.geometry()),
                    _rect_to_tuple(screen.availableGeometry()),
                    screen.logicalDotsPerInch(),
                    screen.physicalDotsPerInch(),
                    screen.devicePixelRatio(),
                )
    except Exception as exc:
        logger.debug("DPI startup logging failed: %s", exc, exc_info=True)


def log_qt_window_geometry(logger, label, qt_window=None, expected_geometry=None):
    if not dpi_debug_enabled():
        return

    try:
        hwnd, window_rect, client_rect, client_on_screen = _win32_game_rects()
        logger.debug("[%s] GetDpiForWindow result: %s", label, get_dpi_for_window(hwnd))
        logger.debug("[%s] Game GetWindowRect: %s", label, window_rect)
        logger.debug("[%s] Game GetClientRect: %s", label, client_rect)
        logger.debug("[%s] Game client rect on screen: %s", label, client_on_screen)
        if client_on_screen:
            logger.debug("[%s] Game client physical size: %sx%s", label, client_on_screen[2], client_on_screen[3])

        if qt_window is not None:
            screen = qt_window.screen()
            if screen is not None:
                logger.debug(
                    "[%s] Qt screen name=%s logicalDpi=%.2f physicalDpi=%.2f devicePixelRatioF=%.3f",
                    label,
                    screen.name(),
                    screen.logicalDotsPerInch(),
                    screen.physicalDotsPerInch(),
                    screen.devicePixelRatio(),
                )

            actual = _rect_to_tuple(qt_window.geometry())
            frame = _rect_to_tuple(qt_window.frameGeometry())
            logger.debug("[%s] Expected overlay geometry: %s", label, expected_geometry)
            logger.debug("[%s] Actual overlay geometry: %s", label, actual)
            logger.debug("[%s] Actual overlay frameGeometry: %s", label, frame)

            if expected_geometry and actual:
                dx = actual[0] - expected_geometry[0]
                dy = actual[1] - expected_geometry[1]
                dw = actual[2] - expected_geometry[2]
                dh = actual[3] - expected_geometry[3]
                logger.debug("[%s] Position delta: (%s, %s)", label, dx, dy)
                logger.debug("[%s] Size delta: (%s, %s)", label, dw, dh)
    except Exception as exc:
        logger.debug("[%s] DPI geometry logging failed: %s", label, exc, exc_info=True)
