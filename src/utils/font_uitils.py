#font_utils.py
import os
from PyQt5.QtGui import QFontDatabase
from src.utils.fileutil import get_resources_dir


def set_font_size(widget, size_px):
    font = widget.font()
    font.setPixelSize(size_px) # 或者 setPointSize
    widget.setFont(font)
    
# 加载字体并返回字体家族列表

def load_font_role_from_dir(font_dir):
    db = QFontDatabase()
    if not os.path.exists(font_dir):
        return None, None

    for fname in os.listdir(font_dir):
        if not fname.lower().endswith((".ttf", ".otf")):
            continue

        path = os.path.join(font_dir, fname)
        # 将字体加载进内存
        font_id = QFontDatabase.addApplicationFont(path)
        if font_id == -1:
            continue

        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            family = families[0]
            # 获取该文件对应的精确 Style（如 Bold, Medium）
            styles = db.styles(family)
            style = styles[0] if styles else None
            return family, style

    return None, None

def load_first_font_family_from_category_dir(category_dir):
    real_font_dir = os.path.join(get_resources_dir(), "fonts", category_dir)
    return load_font_role_from_dir(real_font_dir)