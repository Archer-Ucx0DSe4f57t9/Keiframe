# qt_gui/utils.py
import ctypes
import os
import json
import config
from fileutil import get_resources_dir

def get_screen_resolution():
    user32 = ctypes.windll.user32
    width = user32.GetSystemMetrics(0)
    height = user32.GetSystemMetrics(1)
    return width, height

def get_text(self, key):
    """获取多语言文本"""
    try:
        config_path = get_resources_dir('resources', 'words.conf')
        with open(config_path, 'r', encoding='utf-8') as f:
            content = json.load(f)
            texts = content['qt_gui']
            if config.current_language in texts and key in texts[config.current_language]:
                return texts[config.current_language][key]
            return key
    except Exception as e:
        self.logger.error(f"加载语言配置文件失败: {str(e)}")
        return key
