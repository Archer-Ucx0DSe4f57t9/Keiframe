# -*- coding.py: utf-8 -*-

import os
import json
import sys
import cv2

# current region
current_region = 'kr'  # 当前地区 / Current region
current_language = 'zh'  # 当前语言 / Current language

# 快捷键
MAP_SHORTCUT = 'ctrl + shift + ['  # 地图快捷键 / Map shortcut key
LOCK_SHORTCUT = 'ctrl + shift + ]'  # 锁定快捷键 / Lock shortcut key
SCREENSHOT_SHORTCUT = 'ctrl + shift + -'  # 截图快捷键 / Screenshot shortcut key


# 窗体设置项(主界面位置)
MAIN_WINDOW_X = 1000
MAIN_WINDOW_Y = 1049
# 主窗口透明度配置 ，最后一个200为透明度，前面三个数是RGB数值，具体可以网上查一下选一个自己喜欢的颜色，0完全透明、255完全不透明 / 0 fully transparent, 255 fully opaque
MAIN_WINDOW_BG_COLOR = 'rgba(43, 43, 43, 200)'  # 主界面背景设置
# 窗体宽度 注意这里没有对按钮之类的宽度进行适配，改了之后主要影响的是表格中文字显示的宽度
MAIN_WINDOW_WIDTH = 200  # 主窗口宽度 / Main window width

# 表格字体大小
TABLE_FONT_SIZE = 12  # 表格字体大小 / Table font size
TABLE_HEIGHT = 150  # 表格高度
TABLE_NEXT_FONT_COLOR = (0, 255, 128)  # 表格下一个事件字体颜色 绿色/ Table font color
TABLE_NEXT_FONT_BG_COLOR = (0, 255, 128, 30)  # 表格下一个事件背景颜色，最后一个值是透明度

# === 提示信息显示位置配置 (像素偏移) ===
# 基准点为游戏窗口(SC2)的左上角 (0, 0)
# 向右为 X 正方向，向下为 Y 正方向
TOAST_OFFSET_X = 19 #提示框距离左侧边框的像素距离 0.01*1920
TOAST_OFFSET_Y = 540 # 第一条提示距离顶部边框的像素距离 0.5*1080
TOAST_LINE_HEIGHT = 32 # 提示框行高 (像素，如果设为 0 则自动根据窗口高度计算，建议设置固定值以配合像素定位)
TOAST_FONT_SIZE = 20 # 提示文字大小 (像素)

# 地图提醒配置
MAP_ALERT_SECONDS = 30  # 提前提醒时间（秒）/ Time before alert (in seconds)
MAP_ALERT_WARNING_THRESHOLD_SECONDS = 10  # 倒计时转为警告颜色的阈值（秒）
MAP_ALERT_NORMAL_COLOR = 'rgb(239, 255, 238)'  # 倒计时提醒的正常颜色
MAP_ALERT_WARNING_COLOR = 'rgb(255, 0, 0)'  # 倒计时提醒的警告颜色

# 突变因子提醒配置
MUTATOR_ALERT_SECONDS = 49  # 突变因子提前提醒时间（秒）/ Mutation factor alert time (in seconds)，我还没做多重提醒，最长间隔就是49秒
MUTATOR_WARNING_THRESHOLD_SECONDS = 10  # 倒计时转为警告颜色的阈值（秒）
MUTATOR_NORMAL_COLOR = 'rgb(255, 255, 255)'  # 倒计时提醒的正常颜色
MUTATOR_WARNING_COLOR = 'rgb(255, 0, 0)'  # 倒计时提醒的警告颜色
MUTATOR_ALERT_OFFSET_Y = 324 # 提示列表距离顶部边框的像素距离 (原 0.35 -> 324px)
MUTATOR_ALERT_OFFSET_X = 19 # 提示框距离左侧边框的像素距离 (原 0.01 -> 19px)
MUTATOR_ALERT_LINE_HEIGHT = 32 # 提示框单行高度 (原 0.03 -> 32px)
MUTATOR_ALERT_FONT_SIZE = 19 # 提示文字大小 (原 0.6 * LineHeight -> 19px)

# 提醒配置：
ALERT_SOUND_COOLDOWN = 10 # 同名警告最短间隔（秒），低于间隔的音频不播放
ALERT_SOUND_VOLUME = 90 # 音量大小（0-100正整数）

# 突变因子提示位置配置
MUTATOR_ICON_TRANSPARENCY = 0.7  # 突变因子图标透明度 / Mutator icon transparency

# wiki url
WIKI_URL = 'https://starcraft.huijiwiki.com/wiki/合作任务/'  # Wiki链接 / Wiki URL

# 搜索特殊关键词
MAP_SEARCH_KEYWORDS = {
    "火车": "湮灭快车",
    "黑杀": "黑暗杀星",
    "天锁": "天界封锁",
    "庙a": "往日神庙-A",
    "庙b": "往日神庙-B",
    "撕裂a": "虚空撕裂-左",
    "撕裂b": "虚空撕裂-右",
    "地勤": "机会渺茫-人虫",
    "地勤p": "机会渺茫-神",
    "零件": "聚铁成兵",
    "杀毒": "净网行动",
    "穿梭机": "虚空降临",
    "记者": "熔火危机",
    # 可以继续添加……
}


# 笔记配置
MEMO_OPACITY = 1.0        # 图片显示的透明度 (0.0 - 1.0)
MEMO_DURATION = 5000      # 临时显示时的持续时间 (毫秒)，不含淡出时间
MEMO_FADE_TIME = 1000     # 淡出动画时间 (毫秒)

# 笔记快捷键
MEMO_TEMP_SHORTCUT = '-'  # 临时显示快捷键
MEMO_TOGGLE_SHORTCUT = 'backslash' # 持续开关快捷键


# === 倒计时功能配置 ===
# 格式: {'time': 秒数, 'label': '显示名称', 'sound': '音频文件名'}
COUNTDOWN_OPTIONS = [
    {'time': 120, 'label': '神器/二三哥', 'sound': 'alert.wav'},
    {'time': 100,  'label': '基地',   'sound': 'alert.wav'},
    {'time': 60, 'label': 'bb/孵化场',   'sound': 'alert.wav'},
    {'time': 90, 'label': '大哥巢', 'sound': 'alert.wav'},
]

# 最大同时存在的倒计时数量
COUNTDOWN_MAX_CONCURRENT = 3

# 倒计时警告阈值
COUNTDOWN_WARNING_THRESHOLD_SECONDS = 10

# 默认颜色
COUNTDOWN_DISPLAY_COLOR = "rgb(0, 255, 255)"

# 倒计时快捷键
COUNTDOWN_SHORTCUT = "`"

# 倒计时显示位置 (相对于SC2窗口的百分比)
COUNTDOWN_DISPLAY_Y_PERCENT = 0.15 
COUNTDOWN_DISPLAY_FONT_SIZE = 24




# 调试模式配置
debug_mode = False  # 设置为True启用调试模式 / Set to True to enable debug mode
debug_time_factor = 5.0  # 调试模式下的时间流速因子 / Time flow factor in debug mode

# 日志级别配置
LOG_LEVEL = 'WARNING'  # 日志级别，可选值：DEBUG, INFO, WARNING, ERROR, CRITICAL / Log level, available values: DEBUG, INFO, WARNING, ERROR, CRITICAL


#############################
# 下面配置主要用于图像识别
#############################
DEBUG_SHOW_ENEMY_INFO_SQUARE = False  # 是否显示敌方单位信息框 / Whether to show enemy unit information boxes
GAME_SCREEN = 0
GAME_SCREEN_DPI = 96
# 96 DPI	100%	标准 1080p 显示器
# 120 DPI	125%	2K 显示器常用
# 144 DPI	150%	2K 或 4K 显示器常用
# 192 DPI	200%	4K 显示器常用
# 288 DPI	300%	8K 显示器可能使用

'''
GAME_ICON_POS_AMON_RACE = [45, 300, 36, 36]  #
GAME_ICON_POS_AMON_TROOPS = [1710, 938, 1904, 1035]  #
GAME_ICON_POS_SHOW = True
GAME_ICON_POS_SHOW_RELOAD_INTERVAL = 5  # 秒
GAME_ICO_RECONGIZE_INTERVAL = 1  # 秒
GAME_ICO_RECONGIZE_CONFIDENCE = 0.9  # 0-1 越高识别率越高，但是也会导致误识别
GAME_ICO_RECONGIZE_TIMEOUT = 300  # 秒



TROOP_ICON_SIZE = 50
TROOP_HYBRID_ICON_COLOR = 'rgb(0, 255, 128)'
TROOP_HYBRCONT_FONT_SIZE = 20

ARTIFACTS_IMG_SCALE_RATIO = 0.7
ARTIFACTS_IMG_GRAY = False
ARTIFACTS_IMG_OPACITY = 0.5
ARTIFACTS_POS_死亡摇篮 = [600 / 1174, 483 / 876, 40, 40]  # [x占图像的比例, y占图像的比例, width px, height px]
ARTIFACTS_POS_湮灭快车 = [830 / 1987, 1050 / 1353, 40, 40]
ARTIFACTS_POS_净网行动 = [398 / 1496, 688 / 996, 40, 40]
ARTIFACTS_POS_营救矿工 = [1080 / 1755, 391 / 844, 40, 40]
ARTIFACTS_POS_亡者之夜 = [468 / 1242, 495 / 938, 40, 40]
ARTIFACTS_POS_熔火危机 = [730 / 1783, 1200 / 1334, 40, 40]
'''

#突变因子和敌方种族识别区域（默认1920）
MUTATOR_AND_ENEMY_RACE_RECOGNIZER_ROI = (1800, 50, 1920, 800)

#敌方ai识别区域识别区域（默认1920）
ENEMY_COMP_RECOGNIZER_ROI = (1450, 373 ,1920 ,800)

#净网行动限定
#以下是1920*1080窗口英文模式下的参数。
MALWARFARE_PURIFIED_COUNT_TOP_LEFT_COORD = (298, 85)
MALWARFARE_PURIFIED_COUNT_BOTTOMRIGHT_COORD = (334, 103)

MALWARFARE_TIME_TOP_LFET_COORD = (431, 85)
MALWARFARE_TIME_BOTTOM_RIGHT_COORD = (475, 103)

MALWARFARE_PAUSED_TOP_LFET_COORD = (343, 85)
MALWARFARE_PAUSED_BOTTOM_RIGHT_COORD = (420, 103)
BASE_RESOLUTION_WIDTH = 1920.0 # 基准分辨率宽度(窗口模式下的1920)

# 模板文件夹的相对路径
MALWARFARE_TEMPLATE_DIR = 'char_templates_1920w' # 建议与基准分辨率匹配

# roi 下英雄y轴方向下偏移量
MALWARFARE_HERO_OFFSET = 97
MALWARFARE_ZWEIHAKA_OFFSET = 181
MALWARFARE_REPLAY_OFFSET = 49

#############################
# 净网行动识别用
#############################


# === 算法参数配置 (Master Config 2026) ===
# 结构: OCR_CONFIG[lang][color_type]
OCR_CONFIG = {
    'zh': {
        # 黄色中文 (HSV方案 - 宽范围)
        'yellow': {
            'method': 'hsv',
            'h_min': 21, 'h_max': 35,
            's_min': 50, 'v_min': 50,
            'thresh': 110,
            'morph_op': None  # HSV模式下通常不需要闭运算，如有需要可设为 (cv2.MORPH_CLOSE, 1)
        },
        # 绿色中文 (G-R 方案 - 降阈值防断笔)
        'green': {
            'method': 'green_minus_red',
            'tophat': 3,
            'thresh': 30,
            'morph_op': (cv2.MORPH_ERODE, 2), # (操作类型, 次数)
            'normalize': True
        },
        # 蓝色中文 (蓝通道 - 强去纹理)
        'blue': {
            'method': 'blue_channel',
            'tophat': 4,
            'thresh': 29,
            'morph_op': (cv2.MORPH_ERODE, 2)
        },
        # 橙色中文 (通用 R-B)
        'orange': {
            'method': 'red_minus_blue',
            'tophat': 3,
            'thresh': 41,
            'morph_op': (cv2.MORPH_ERODE, 1)
        }
    },
    'en': {
        # 黄色英文 (HSV方案 - 窄范围解决6/8粘连)
        'yellow': {
            'method': 'hsv',
            'h_min': 28, 'h_max': 35,
            's_min': 50, 'v_min': 50,
            'thresh': 110,
            'morph_op': None
        },
        # 绿色英文 (G-R 方案 - 高阈值去光晕)
        'green': {
            'method': 'green_minus_red',
            'tophat': 0,
            'thresh': 60,
            'morph_op': (cv2.MORPH_OPEN, 1), # 开运算
            'normalize': False
        },
        # 蓝色英文 (蓝通道 - 锐利)
        'blue': {
            'method': 'blue_channel',
            'tophat': 4,
            'thresh': 45,
            'morph_op': (cv2.MORPH_ERODE, 2)
        },
        # 橙色英文 (同中文通用)
        'orange': {
            'method': 'red_minus_blue',
            'tophat': 3,
            'thresh': 41,
            'morph_op': (cv2.MORPH_ERODE, 1)
        }
    }
}

# === 目录名映射 ===
# 根据当前的 self.lang 和 target_color 找到对应的文件夹名
# 例如: ('zh', 'blue') -> 'zh_blue'
def get_template_folder(lang, color):
    return f"{lang}_{color}"

#############################
# 配置用参数，如无必要请勿修改
#############################
MUTATOR_WIDTH = 27 #UI界面突变图标区域宽度

#############################
# 读取外部配置相关
#############################

CONFIG_FILE_NAME = 'settings.json'

def get_settings_path():
    """根据运行环境计算 settings.json 的绝对路径 (项目根目录)"""
    if getattr(sys, 'frozen', False):
        # 打包环境 (EXE): 使用可执行文件所在的目录
        project_root = os.path.dirname(sys.executable)
    else:
        # 源码环境: config.py 在 src/ 中，需要向上两级目录到达项目根目录
        current_dir = os.path.dirname(os.path.abspath(__file__)) # /project/src
        project_root = os.path.dirname(current_dir) # /project/

    return os.path.join(project_root, CONFIG_FILE_NAME)


def load_external_settings():
    """尝试加载外部 JSON 配置并覆盖当前模块的变量"""
    CONFIG_PATH = get_settings_path()
    
    if not os.path.exists(CONFIG_PATH):
        return

    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            settings = json.load(f)
            
        g = globals()
        
        for key, value in settings.items():
            # 只有当变量已经在 config.py 中定义过时才进行覆盖（防止注入未知变量）
            if key in g:
                # 如果 JSON 里的值是列表，且 config.py 原始值是元组，则转换
                if isinstance(value, list) and isinstance(g[key], tuple):
                    g[key] = tuple(value)
                else:
                    # 其他类型（int, float, str, bool）直接赋值
                    g[key] = value
        
    except Exception as e:
        # 打印错误，但不中断程序运行
        print(f"警告：加载外部配置失败，将使用默认值。错误信息: {e}")

# 执行加载
load_external_settings()