# 映射表定义
MAP_HEADER_MAP = {
    'map_name': '地图名称 (请勿修改)',
    'time_label': '提醒时间点 (格式 分:秒)',
    'count_value': '计数值 (如已净化节点数)',
    'event_text': '事件提醒内容',
    'army_text': '兵种/阵营信息',
    'sound_filename': '语音文件名 (需在resources/sounds中)',
    'hero_text': '英雄台词/备注'
}

MUTATOR_HEADER_MAP = {
    'mutator_name': '突变因子名称 (请勿修改)',
    'time_label': '提醒时间点 (格式 分:秒)',
    'content_text': '因子效果/提醒内容',
    'sound_filename': '语音文件名'
}

#名称到简略中文名称映射，用于提示显示,将来迁移到语言模块
mutator_names_to_CHS = {'AggressiveDeployment': '部署', 'Propagators': '小软', 'VoidRifts': '裂隙', 'KillBots': '杀戮',
                        'BoomBots': '炸弹', 'HeroesFromtheStorm': '风暴', 'AggressiveDeploymentProtoss': '部署神族'}
