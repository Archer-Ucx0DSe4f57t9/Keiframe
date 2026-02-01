import sqlite3
import os

def init_database():
    conn = sqlite3.connect('app_assets.db')
    cursor = conn.cursor()

    # 1. 创建地图配置表
    cursor.execute('''CREATE TABLE IF NOT EXISTS map_configs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        map_tag TEXT,           -- 如 'OblivionExpress'
        map_name_zh TEXT,       -- 如 '湮灭快车'
        is_malwarfare INTEGER,  -- 0或1
        mwf_count_val TEXT,
        time_text TEXT,
        time_seconds INTEGER,
        event_val TEXT,
        army_val TEXT,
        sound_val TEXT,
        hero_val TEXT,
        raw_line TEXT
    )''')

    # 2. 突变因子表
    cursor.execute('''CREATE TABLE IF NOT EXISTS mutators (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mutator_tag TEXT,       -- 如 'Propagators'
        mutator_name_zh TEXT,
        time_seconds INTEGER,
        content_text TEXT,
        sound_filename TEXT
    )''')

    # 3. 创建敌方构成表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS enemy_compositions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tier TEXT,
            units TEXT
        )
    ''')

    # 4.倒计时列表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS countdown_timers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            time_seconds TEXT,
            label_name_zh TEXT,
            sound_filename TEXT
        )
    ''')

    conn.commit()
    conn.close()
    print("数据库初始化完成")

if __name__ == "__main__":
    init_database()