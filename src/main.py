#main.py
import os
import sys
from datetime import datetime, timedelta
from src.utils.fileutil import get_project_root, get_resources_dir

# 检查当前目录是否存在config.py文件，如果存在则添加当前目录到sys.path
src_dir = os.path.join(get_project_root(), "src")
if os.path.exists(os.path.join(src_dir, "config.py")):
    sys.path.insert(0, src_dir)

from src.utils.windows_dpi import configure_process_dpi, configure_qt_fixed_pixel_environment

# 固定物理像素 UI：必须在导入 PyQt / 创建 QApplication 前完成。
configure_qt_fixed_pixel_environment()
dpi_awareness_mode = configure_process_dpi()

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

# 固定物理像素 UI：禁止 Qt 根据 Windows 缩放比例自动放大窗口、字体和 pixmap。
QApplication.setAttribute(Qt.AA_DisableHighDpiScaling, True)
if hasattr(Qt, "AA_Use96Dpi"):
    QApplication.setAttribute(Qt.AA_Use96Dpi, True)
QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, False)

# 禁用原生对话框和原生小部件，保持窗口行为统一。
QApplication.setAttribute(Qt.AA_DontUseNativeDialogs)
QApplication.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings)

from src.qt_gui import TimerWindow
import src.utils.logging_util as logging_util
from src.utils.font_uitils import load_first_font_family_from_category_dir
from src.utils.ui_coordinate_debug import log_startup_dpi
from src import config

# 日志文件管理：当日志文件超过 1MB 时，保留最近 7 天的日志
def rotate_log_file(log_path, max_size_mb=1, days_to_keep=7):
    if not os.path.exists(log_path):
        return

    # 1. 检查文件大小 (转换 MB 为 Bytes)
    if os.path.getsize(log_path) > max_size_mb * 1024 * 1024:
        print(f"Log file exceeds {max_size_mb}MB, cleaning up old entries...")

        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        remaining_lines = []

        with open(log_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    # 提取每行开头的日期部分 "2026-02-16"
                    date_str = line.split(' ')[0]
                    log_date = datetime.strptime(date_str, '%Y-%m-%d')

                    if log_date >= cutoff_date:
                        remaining_lines.append(line)
                except (ValueError, IndexError):
                    # 如果行格式不符合预期（如换行符），保留该行
                    remaining_lines.append(line)

        # 2. 写回保留的内容
        with open(log_path, 'w', encoding='utf-8') as f:
            f.writelines(remaining_lines)


def setup_mixed_fonts(app):
    # ===== 加载主 UI 字体 =====
    # 假设你把字体放在 "primary" 文件夹下
    u_family, u_style = load_first_font_family_from_category_dir("primary")

    # 兜底方案
    if not u_family:
        u_family, u_style = "Microsoft YaHei", None

    config.FONT_PRIMARY = u_family
    config.FONT_PRIMARY_STYLE = u_style

    font = QFont(u_family)
    font.setPixelSize(int(config.UI_FONT_SIZE))
    if u_style:
        font.setStyleName(u_style)
    app.setFont(font)


def main():
    rotate_log_file('Keiframe.log')
    logging_util.setup_logger()


    app = QApplication(sys.argv)
    setup_mixed_fonts(app)
    log_startup_dpi(logging_util.get_logger(__name__), dpi_awareness_mode, app)

    timer = TimerWindow()

    #
    #show_fence.show_square()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
