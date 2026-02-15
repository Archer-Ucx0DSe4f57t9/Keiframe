# 映射表定义
MAP_HEADER_MAP = {
        'map_name': '地图名称',
        'time_label': '提醒时间点 (格式 分:秒)',
        'count_value': '已净化节点数（净网专用）',
        'event_text': '事件提醒内容',
        'army_text': '补充（科技等级/混合体/...）',
        'sound_filename': '语音文件名',
        'hero_text': '风暴英雄'
    }

MUTATOR_HEADER_MAP = {
    'mutator_name': '突变因子名称',
    'time_label': '提醒时间点 (格式 分:秒)',
    'content_text': '因子效果/提醒内容',
    'sound_filename': '语音文件名'
}

#名称到简略中文名称映射，将来迁移到语言模块
mutator_names_to_CHS = {'部署': '部署', '小软': '小软', '裂隙': '裂隙', '杀戮': '杀戮',
                        '炸弹': '炸弹', '风暴': '风暴', '部署神族': '部署神族'}
