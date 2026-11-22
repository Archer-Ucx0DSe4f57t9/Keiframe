#main.py
import os
import sys
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
    logging_util.initialize_logging()


    app = QApplication(sys.argv)
    setup_mixed_fonts(app)
    log_startup_dpi(logging_util.get_logger(__name__), dpi_awareness_mode, app)

    timer = TimerWindow()

    #
    #show_fence.show_square()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
