#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSV -> SQLite 迁移脚本（maps / mutator / enemies）
可反复运行（幂等），错误定位到文件/行/列。
改路径后直接运行：python migrate_all_configs.py
"""

import sqlite3
import csv
import json
import traceback
from pathlib import Path
from typing import List, Tuple

# ====== 配置区：修改为你的路径 ======
BASE_CSV_DIR = Path()
MAPS_CSV_DIR = BASE_CSV_DIR / "maps"/"new"       # 存放地图 CSV 的目录
MUTATOR_CSV_DIR = BASE_CSV_DIR / "mutator" # 存放突变因子 CSV 的目录
ENEMIES_CSV_DIR = BASE_CSV_DIR / "enemy_comps" # 存放敌方构成 CSV 的目录

BASE_DB_DIR = Path("config_db")            # 输出 sqlite DB 的目录
# =======================================

# ===== Helper: parse time strings to integer seconds =====
def parse_time_to_seconds(t: str) -> int:
    """
    支持 "MM:SS" 或 "HH:MM:SS" 或 "M:SS" 等。返回总秒数。
    抛出 ValueError 如果格式不对或数值非法。
    """
    t = t.strip()
    if not t:
        raise ValueError("empty time string")
    parts = t.split(':')
    try:
        if len(parts) == 2:
            m, s = parts
            return int(m) * 60 + int(s)
        elif len(parts) == 3:
            h, m, s = parts
            return int(h) * 3600 + int(m) * 60 + int(s)
        else:
            raise ValueError(f"unsupported time format: {t}")
    except Exception as ex:
        raise ValueError(f"invalid time '{t}': {ex}")

# ====== DB schema SQL ======
MAPS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS map_rows (
    config_name TEXT NOT NULL,
    time_label  TEXT NOT NULL,
    time_value  INTEGER NOT NULL,
    count_value  TEXT,
    event_text  TEXT,
    army_text   TEXT,
    sound_text  TEXT,
    hero_text   TEXT,
    PRIMARY KEY (config_name, time_value)
);
"""

MUTATOR_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS mutator_rows (
    config_name   TEXT NOT NULL,
    time_label    TEXT NOT NULL,
    time_value    INTEGER NOT NULL,
    content_text  TEXT,
    sound_filename TEXT,
    PRIMARY KEY (config_name, time_value)
);
"""

ENEMIES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS enemy_composition (
    config_name TEXT NOT NULL,
    tier        TEXT NOT NULL,   -- e.g., t1,t2...
    units       TEXT,            -- 原始单位字符串 (可以包含空格分隔多个关键单位)
    PRIMARY KEY (config_name, tier)
);
"""

# ====== Core migration functions ======
def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)

def migrate_maps(csv_dir: Path, db_path: Path):
    ensure_dir(db_path.parent)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(MAPS_TABLE_SQL)
    conn.commit()

    if not csv_dir.exists():
        print(f"[WARN] maps CSV dir not found: {csv_dir}")
        conn.close()
        return

    for csv_file in sorted(csv_dir.glob("*.csv")):
        config_name = csv_file.stem  # 用文件名（不含扩展）作为 config_name
        print(f"[maps] migrating: {csv_file} -> {db_path} (config_name={config_name})")
        with csv_file.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            for row_idx, parts in enumerate(reader, start=1):
                # 跳过空白行
                if not parts or all((not c.strip()) for c in parts):
                    continue
                # 去掉每列两端空白
                parts = [p.strip() for p in parts]
                try:
                    # 识别 time 所在列：
                    # 常见两种： time 在 parts[0]，或 count 在 parts[0] 且 time 在 parts[1]
                    if len(parts) >= 1 and ":" in parts[0]:
                        # time at parts[0]
                        time_text = parts[0]
                        count_value = ""  # 无 count
                        event_text = parts[1] if len(parts) >= 2 else ""
                        army_text = parts[2] if len(parts) >= 3 else ""
                        sound_text = parts[3] if len(parts) >= 4 else ""
                        hero_text = parts[4] if len(parts) >= 5 else ""
                    elif len(parts) >= 2 and ":" in parts[1]:
                        # count at parts[0], time at parts[1]  (e.g. 净网行动）
                        count_value = parts[0]
                        time_text = parts[1]
                        event_text = parts[2] if len(parts) >= 3 else ""
                        army_text = parts[3] if len(parts) >= 4 else ""
                        sound_text = parts[4] if len(parts) >= 5 else ""
                        hero_text = parts[5] if len(parts) >= 6 else ""
                    else:
                        # 都识别不到 time：把整行放到 event_text，time 必须给个序号（或跳过）
                        # 这里选择跳过并打印 warn
                        raise ValueError("cannot detect time column in this row")
                    # parse time -> seconds
                    time_value = parse_time_to_seconds(time_text)
                    # 插入或替换（幂等）
                    cur.execute("""
                        INSERT OR REPLACE INTO map_rows
                        (config_name, time_label, time_value, count_value, event_text, army_text, sound_text, hero_text)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (config_name, time_text, time_value, count_value, event_text, army_text, sound_text, hero_text))
                except Exception as ex:
                    print(f"[ERROR] maps {csv_file} line {row_idx}: {ex}")
                    # 可选：继续下一行，或选择 raise 停止。这里继续并记录 traceback
                    traceback.print_exc()
        conn.commit()
    conn.close()
    print("[maps] migration done.")


def migrate_mutators(csv_dir: Path, db_path: Path):
    ensure_dir(db_path.parent)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(MUTATOR_TABLE_SQL)
    conn.commit()

    if not csv_dir.exists():
        print(f"[WARN] mutator CSV dir not found: {csv_dir}")
        conn.close()
        return

    for csv_file in sorted(csv_dir.glob("*.csv")):
        config_name = csv_file.stem
        print(f"[mutator] migrating: {csv_file} -> {db_path} (config_name={config_name})")
        with csv_file.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            for row_idx, parts in enumerate(reader, start=1):
                if not parts or all((not c.strip()) for c in parts):
                    continue
                parts = [p.strip() for p in parts]
                try:
                    # 期望至少 3 列： time, content, sound
                    if len(parts) < 2:
                        raise ValueError("not enough columns for mutator row")
                    time_text = parts[0]
                    content_text = parts[1] if len(parts) >= 2 else ""
                    sound_filename = parts[2] if len(parts) >= 3 else ""
                    time_value = parse_time_to_seconds(time_text)
                    cur.execute("""
                        INSERT OR REPLACE INTO mutator_rows
                        (config_name, time_label, time_value, content_text, sound_filename)
                        VALUES (?, ?, ?, ?, ?)
                    """, (config_name, time_text, time_value, content_text, sound_filename))
                except Exception as ex:
                    print(f"[ERROR] mutator {csv_file} line {row_idx}: {ex}")
                    traceback.print_exc()
        conn.commit()
    conn.close()
    print("[mutator] migration done.")


def migrate_enemies(csv_dir: Path, db_path: Path):
    ensure_dir(db_path.parent)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(ENEMIES_TABLE_SQL)
    conn.commit()

    if not csv_dir.exists():
        print(f"[WARN] enemies CSV dir not found: {csv_dir}")
        conn.close()
        return

    for csv_file in sorted(csv_dir.glob("*.csv")):
        config_name = csv_file.stem
        print(f"[enemies] migrating: {csv_file} -> {db_path} (config_name={config_name})")
        with csv_file.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            for row_idx, parts in enumerate(reader, start=1):
                # 允许只有 tier 的空行（t1,）
                if not parts or all((not c.strip()) for c in parts):
                    continue
                parts = [p.strip() for p in parts]
                try:
                    tier = parts[0] if len(parts) >= 1 else ""
                    units = parts[1] if len(parts) >= 2 else ""
                    if not tier:
                        raise ValueError("empty tier column")
                    # 直接存 units 字符串，后续可解析空格或其它分隔符
                    cur.execute("""
                        INSERT OR REPLACE INTO enemy_composition (config_name, tier, units)
                        VALUES (?, ?, ?)
                    """, (config_name, tier, units))
                except Exception as ex:
                    print(f"[ERROR] enemies {csv_file} line {row_idx}: {ex}")
                    traceback.print_exc()
        conn.commit()
    conn.close()
    print("[enemies] migration done.")


# ====== Main entry ======
def main():
    ensure_dir(BASE_DB_DIR)

    maps_db = BASE_DB_DIR / "maps.db"
    mutator_db = BASE_DB_DIR / "mutators.db"
    enemies_db = BASE_DB_DIR / "enemies.db"

    migrate_maps(MAPS_CSV_DIR, maps_db)
    #migrate_mutators(MUTATOR_CSV_DIR, mutator_db)
    #migrate_enemies(ENEMIES_CSV_DIR, enemies_db)

    print("All migrations finished.")


if __name__ == "__main__":
    main()
