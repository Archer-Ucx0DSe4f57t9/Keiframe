import os
import sys
from src.utils.fileutil import get_project_root

# 检查当前目录是否存在config.py文件，如果存在则添加当前目录到sys.path
src_dir = os.path.join(get_project_root(),"src")
if os.path.exists(os.path.join(src_dir, "config.py")):
    sys.path.insert(0, src_dir)
    print(f"使用外部配置文件: {os.path.join(src_dir, 'config.py')}")

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QGuiApplication
from qt_gui import TimerWindow
import src.utils.logging_util as logging_util
import image_util
import config
import show_fence

def main():
    logging_util.setup_logger()
    # 启用高DPI缩放
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    # 启用高DPI图标
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    # 禁用原生对话框和原生小部件，确保统一的DPI缩放
    QApplication.setAttribute(Qt.AA_DontUseNativeDialogs)
    QApplication.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings)

    app = QApplication(sys.argv)
    # 设置DPI缩放策略为PassThrough，确保精确的DPI缩放
    app.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    timer = TimerWindow()
    
    #
    show_fence.show_square()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
