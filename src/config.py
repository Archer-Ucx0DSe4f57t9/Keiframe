# -*- coding: utf-8 -*-

# current region
current_region = 'kr'  # 当前地区 / Current region
current_language = 'zh'  # 当前语言 / Current language


# 调试模式配置
debug_mode = False  # 设置为True启用调试模式 / Set to True to enable debug mode
debug_time_factor = 5.0  # 调试模式下的时间流速因子 / Time flow factor in debug mode

# 日志级别配置
LOG_LEVEL = 'DEBUG'  # 日志级别，可选值：DEBUG, INFO, WARNING, ERROR, CRITICAL / Log level, available values: DEBUG, INFO, WARNING, ERROR, CRITICAL

# 快捷键
MAP_SHORTCUT = 'ctrl + shift + ['  # 地图快捷键 / Map shortcut key
LOCK_SHORTCUT = 'ctrl + shift + ]'  # 锁定快捷键 / Lock shortcut key
SCREENSHOT_SHORTCUT = 'ctrl + shift + -'  # 截图快捷键 / Screenshot shortcut key
SHOW_ARTIFACT_SHORTCUT = 'ctrl + shift + \\' 

# Toast提示配置
TOAST_ALLOWED = True  # 是否允许显示Toast提示 / Whether to allow displaying Toast notifications
TOAST_DURATION = 10000  # 显示时间（毫秒）/ Display time (in milliseconds)
TOAST_OPACITY = 0  # 背景透明度（0-255）/ Background opacity (0-255)
TOAST_POSITION = 0.9  # 垂直位置（窗口高度的比例）/ Vertical position (relative to window height)
TOAST_FONT_SIZE = 45  # 字体大小 / Font size
TOAST_FONT_COLOR = 'rgb(0, 191, 255)'  # 字体颜色 / Font color
TOAST_OUTLINE_COLOR = 'rgb(0, 0, 0)' #字体描边颜色/Outline Color

# 窗体设置项
MAIN_WINDOW_X = 1029
MAIN_WINDOW_Y = 1049
# 主窗口透明度配置 ，最后一个200为透明度，前面三个数是RGB数值，具体可以网上查一下选一个自己喜欢的颜色，0完全透明、255完全不透明 / 0 fully transparent, 255 fully opaque
MAIN_WINDOW_BG_COLOR = 'rgba(43, 43, 43, 200)' # 主界面背景设置
COMMANDER_SELECTOR_BG_COLOR = 'rgba(43, 43, 43, 200)'  # 指挥官选择器背景设置
# 窗体宽度 注意这里没有对按钮之类的宽度进行适配，改了之后主要影响的是表格中文字显示的宽度
MAIN_WINDOW_WIDTH = 167  # 主窗口宽度 / Main window width

# 表格字体大小
TABLE_FONT_SIZE = 12  # 表格字体大小 / Table font size
TABLE_HEIGHT = 150 # 表格高度
TABLE_NEXT_FONT_COLOR = [0, 255, 128]  # 表格下一个事件字体颜色 绿色/ Table font color
TABLE_NEXT_FONT_BG_COLOR = [0, 255, 128, 30] # 表格下一个事件背景颜色，最后一个值是透明度

# 时间提醒配置
TIME_ALERT_SECONDS = 30  # 提前提醒时间（秒）/ Time before alert (in seconds)

# 突变因子提醒配置
MUTATION_FACTOR_ALERT_SECONDS = 49  # 突变因子提前提醒时间（秒）/ Mutation factor alert time (in seconds)，我还没做多重提醒，最长间隔就是49秒
MUTATION_FACTOR_WARNING_THRESHOLD_SECONDS = 10# 倒计时转为警告颜色的阈值（秒）
MUTATION_FACTOR_ALERT_DURATION_SECONDS = 5  # 突变因子提醒持续时间（秒）/ Duration of mutation factor alert (in seconds)
MUTATION_FACTOR_NORMAL_COLOR = 'rgb(255, 255, 255)' # 倒计时提醒的正常颜色
MUTATION_FACTOR_WARNING_COLOR = 'rgb(255, 0, 0)'# 倒计时提醒的警告颜色
MUTATOR_DEPLOYMENT_COLOR = 'rgb(0, 255, 128)'  # 突变因子部署颜色 / Mutator deployment color
MUTATOR_RIFTS_COLOR = 'rgb(0, 255, 128)'  # 突变因子裂隙颜色 / Mutator rifts color
MUTATOR_PROPAGATOR_COLOR = 'rgb(0, 255, 128)'  # 突变因子传播者颜色 / Mutator propagator color
# 提醒大小(基于“StarCraft II”窗口的尺寸)
MUTATOR_ALERT_TOP_OFFSET_PERCENT = 0.40  # 提醒区域距离窗口顶部的百分比
MUTATOR_ALERT_LINE_HEIGHT_PERCENT = 0.04    # 每行提醒占窗口高度的百分比
MUTATOR_ALERT_FONT_SIZE_PERCENT_OF_LINE = 0.6 #字体大小占每行高度的百分比
MUTATOR_ALERT_HORIZONTAL_INDENT_PERCENT = 0.01 #距离游戏边框左侧的水平缩进


# 突变因子提示位置配置
MUTATOR_TOAST_POSITION = 0.7  # 垂直位置（窗口高度的比例）/ Vertical position (relative to window height)
MUTATOR_ICON_TRANSPARENCY = 0.7  # 突变因子图标透明度 / Mutator icon transparency
TOAST_MUTATOR_FONT_SIZE = 30  # 突变因子提示字体大小 / Mutator toast font size
MUTATOR_DEPLOYMENT_POS = 0.2  # 突变因子部署位置 / Mutator deployment position
MUTATOR_PROPAGATOR_POS = 0.35  # 突变因子传播者位置 / Mutator propagator position
MUTATOR_RIFT_POS = 0.5  # 突变因子裂隙位置 / Mutator rift position
MUTATOR_KILLBOTS_POS = 0.65  # 突变因子杀戮机器人位置 / Mutator killbots position
MUTATOR_BOMBBOTS_POS = 0.8  # 突变因子炸弹机器人位置 / Mutator bombbots position

# wiki url
WIKI_URL = 'https://starcraft.huijiwiki.com/wiki/%E5%90%88%E4%BD%9C%E4%BB%BB%E5%8A%A1/%E7%AA%81%E5%8F%98%E5%88%97%E8%A1%A8'  # Wiki链接 / Wiki URL

# 指挥官头像布局
avatar = [
    ['raynor', 'kerrigan', 'artanis', 'swann', 'zagara', 'vorazun', 'karax', 'abathur', 'alarak', 'nova'],  # 第一行指挥官头像 / First row of commander avatars
    ['stukov', 'fenix', 'dehaka', 'horner', 'tychus', 'zeratul', 'stetmann', 'mengsk']  # 第二行指挥官头像 / Second row of commander avatars
]

# 替换指挥官黑名单 - Mutator commander blacklist
# 添加格式 如：BLACK_LIST = ['raynor', 'kerrigan']， 这样在替换界面点击随机时，就不会替换到这两个了
# If you add commanders like: BLACK_LIST = ['raynor', 'kerrigan'], they won't be selected in random replacement
BLACK_LIST = []
REPLACE_COMMANDER_FLAG = False


#搜索特殊关键词
MAP_SEARCH_KEYWORDS = {
    "火车": "湮灭快车",
    "黑杀": "黑暗杀星",
    "天锁": "天界封锁",
    "庙a":"往日神庙-A",
    "庙b":"往日神庙-B",
    "撕裂a":"虚空撕裂-左",
    "撕裂b":"虚空撕裂-右",
    "地勤":"机会渺茫",
    "零件":"聚铁成兵",
    "杀毒":"净网行动",
    "穿梭机":"虚空降临",
    # 可以继续添加……
}
#############################
# 下面配置主要用于图像识别
DEBUG_SHOW_ENEMY_INFO_SQUARE = False  # 是否显示敌方单位信息框 / Whether to show enemy unit information boxes
GAME_SCREEN = 0
GAME_SCREEN_DPI = 96
# 96 DPI	100%	标准 1080p 显示器
# 120 DPI	125%	2K 显示器常用
# 144 DPI	150%	2K 或 4K 显示器常用
# 192 DPI	200%	4K 显示器常用
# 288 DPI	300%	8K 显示器可能使用

GAME_ICON_POS_AMON_RACE = [45, 300, 36, 36] #  
GAME_ICON_POS_AMON_TROOPS = [1710, 938, 1904, 1035] # 
GAME_ICON_POS_SHOW = True 
GAME_ICON_POS_SHOW_RELOAD_INTERVAL = 5 # 秒 
GAME_ICO_RECONGIZE_INTERVAL = 1 # 秒
GAME_ICO_RECONGIZE_CONFIDENCE = 0.9 # 0-1 越高识别率越高，但是也会导致误识别
GAME_ICO_RECONGIZE_TIMEOUT = 300 # 秒

TROOP_ICON_SIZE = 50
TROOP_HYBRID_ICON_COLOR = 'rgb(0, 255, 128)'
TROOP_HYBRCONT_FONT_SIZE = 20

ARTIFACTS_IMG_SCALE_RATIO = 0.7
ARTIFACTS_IMG_GRAY = False
ARTIFACTS_IMG_OPACITY = 0.5
ARTIFACTS_POS_死亡摇篮 = [600/1174, 483/876, 40, 40] # [x占图像的比例, y占图像的比例, width px, height px]
ARTIFACTS_POS_湮灭快车 = [830/1987, 1050/1353, 40, 40]
ARTIFACTS_POS_净网行动 = [398/1496, 688/996, 40, 40]
ARTIFACTS_POS_营救矿工 = [1080/1755, 391/844, 40, 40]
ARTIFACTS_POS_亡者之夜 = [468/1242, 495/938, 40, 40]
ARTIFACTS_POS_熔火危机 = [730/1783, 1200/1334, 40, 40]

