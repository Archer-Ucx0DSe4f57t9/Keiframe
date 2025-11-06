import os
import sys
import re
import traceback
import json
import config
from fileutil import get_resources_dir, list_files

def get_text(window, key):
    """获取多语言文本 (原 TimerWindow.get_text)"""
    try:
        config_path = get_resources_dir('resources', 'words.conf')
        with open(config_path, 'r', encoding='utf-8') as f:
            content = json.load(f)
            texts = content['qt_gui']
            if config.current_language in texts and key in texts[config.current_language]:
                return texts[config.current_language][key]
            return key
    except Exception as e:
        window.logger.error(f"加载语言配置文件失败: {str(e)}")
        return key

def on_language_changed(window, lang):
    """处理语言切换事件 (原 TimerWindow.on_language_changed)"""
    # 1. 更新 config.py 中的语言配置
    if getattr(sys, 'frozen', False):  # 是否为打包的 exe
        base_dir = os.path.dirname(sys.executable)
        config_file = os.path.join(base_dir, 'config.py')
    else:
        # 假设 config.py 位于项目根目录下的 'src' 目录或上一级目录的 'src'
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_file = os.path.join(base_dir, 'src', 'config.py')

    window.logger.info(f"load config: {config_file}")

    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 使用正则表达式替换current_language的值
        new_content = re.sub(r"current_language\s*=\s*'[^']*'", f"current_language = '{lang}'", content)

        window.logger.info(f"update config: {config_file}")
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write(new_content)

        # 2. 更新config模块中的值
        config.current_language = lang

        # 3. 更新 commander_selector 的语言设置
        if hasattr(window, 'commander_selector'):
            window.commander_selector.set_language(lang)

        # 4. 重新加载地图列表
        resources_dir = get_resources_dir('resources', 'maps', lang)
        all_files = list_files(resources_dir) if resources_dir else []
        files = []
        for file_name in all_files:
        # 确保只处理 .csv 文件
            if file_name.lower().endswith('.csv'):
                # 移除 .csv 扩展名
                clean_name = file_name[:-4] 
                files.append(clean_name)

        # 清空并重新添加地图列表
        window.combo_box.clear()
        window.combo_box.addItems(files)

        # 5. 自动加载第一个地图并更新UI文本
        if files:
            # 调用 TimerWindow 中封装的 on_map_selected 接口 (它会转发给 map_loader)
            window.on_map_selected(files[0]) 

        # 6. 更新 UI 文本 (例如 replace_commander 按钮)
        window.replace_commander_btn.setText(get_text(window, 'replace_commander'))

        # 7. 重新初始化系统托盘菜单以更新语言选择标记
        window.init_tray()

    except Exception as e:
        window.logger.error(f'语言切换处理失败: {str(e)}')
        window.logger.error(traceback.format_exc())