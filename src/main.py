#main.py
import os
import sys
from src.utils.fileutil import get_project_root, get_resources_dir
from PyQt5.QtGui import QFontDatabase, QFont

# 检查当前目录是否存在config.py文件，如果存在则添加当前目录到sys.path
src_dir = os.path.join(get_project_root(),"src")
if os.path.exists(os.path.join(src_dir, "config.py")):
    sys.path.insert(0, src_dir)
    print(f"启动并使用外部配置文件: {os.path.join(src_dir, 'config.py')}")


# 防止系统 / 用户环境污染 Qt 行为
os.environ.pop("QT_DEVICE_PIXEL_RATIO", None)

# 官方推荐 DPI 机制
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QGuiApplication
from qt_gui import TimerWindow
import src.utils.logging_util as logging_util
from src.utils.font_uitils import load_first_font_family_from_category_dir
import image_util
import config
import show_fence



def setup_mixed_fonts(app):
    # ===== 加载主 UI 字体 =====
    # 假设你把字体放在 "primary" 文件夹下
    u_family, u_style = load_first_font_family_from_category_dir("primary")
    
    # 兜底方案
    if not u_family:
        u_family, u_style = "Microsoft YaHei", None

    config.FONT_PRIMARY = u_family
    config.FONT_PRIMARY_STYLE = u_style

    font = QFont(u_family, config.UI_FONT_SIZE)
    if u_style:
        font.setStyleName(u_style)
    app.setFont(font)

    '''
    # ===== 加载 Message 字体 =====
    # 假设你把字体放在 "message" 文件夹下
    m_family, m_style = load_first_font_family_from_category_dir("message")
    
    
    if not m_family:
        print("未找到 Message 字体，使用 UI 字体作为后备")
        m_family, m_style = u_family, u_style

    config.FONT_MESSAGE = m_family
    config.FONT_MESSAGE_STYLE = m_style

    print(f"UI Font: {u_family} ({u_style})")
    print(f"MSG Font: {m_family} ({m_style})")
    '''
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
    setup_mixed_fonts(app)
    
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
