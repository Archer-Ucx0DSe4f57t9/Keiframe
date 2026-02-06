# src/db/map_daos.py

# 根据地图名称加载地图配置
def load_map_by_name(conn, map_name):
  #键值：	"map_name","time_label"，	"time_value","count_value",	"event_text",	"army_text"，"sound_filename"，"hero_text"
    if map_name =='净网行动':
    # 特殊排序逻辑：优先按 已净化节点count_value 升序，其次按 倒计时 time_value 降序,
    # 最后再按 波次T>压制塔 event_text 特定规则排序
        sql = """
        SELECT *
        FROM map_configs
        WHERE map_name = ?
        ORDER BY
            count_value ASC,
            time_value DESC,
            CASE
                WHEN event_text GLOB 'T[0-9]*' THEN 1
                ELSE 0
            END DESC,
            event_text ASC
        """
    else:
    # 一般排序逻辑：按 time_value 升序
        sql = """
        SELECT *
        FROM map_configs
        WHERE map_name = ?
        ORDER BY time_value ASC
        """
    cur = conn.execute(sql, (map_name,))
    rows = cur.fetchall()

    result = []
    # 组织结果为字典列表，便于日后数据库修改
    for r in rows:
        result.append({
            "map_name": r["map_name"],
            "time": {
                "label": r["time_label"],
                "value": r["time_value"],
            },
            "count": r["count_value"],
            "event": r["event_text"],
            "army": r["army_text"],
            "sound": r["sound_filename"],
            "hero": r["hero_text"],
        })
    return result

# 获取所有不同的地图名称
def get_all_map_names(conn):
    sql = """
    SELECT * FROM maps
    """
    cur = conn.execute(sql)
    rows = cur.fetchall()
    return [row[0] for row in rows]


# === 关键词管理 ===

# 搜索关键词对应的地图列表
def search_maps_by_keyword(conn, keyword):
    sql = """
    SELECT map_name
    FROM map_keywords
    WHERE keyword = ?
    ORDER BY priority DESC
    """
    cur = conn.execute(sql, (keyword,))
    return [row[0] for row in cur.fetchall()]

# 获取所有搜索关键词映射
def get_all_keywords(conn):
    """获取所有搜索关键词映射"""
    sql = "SELECT keyword, map_name FROM map_keywords ORDER BY priority DESC"
    cur = conn.execute(sql)
    # 返回字典格式，方便业务层直接使用
    return {row[0]: row[1] for row in cur.fetchall()}

# 批量更新关键词（清空并重建）
def update_keywords_batch(conn, keyword_dict):
    """批量更新关键词（清空并重建）"""
    conn.execute("DELETE FROM map_keywords")
    sql = "INSERT INTO map_keywords (keyword, map_name) VALUES (?, ?)"
    conn.executemany(sql, keyword_dict.items())
    conn.commit()

# === Excel 导入支持 ===
def convert_time_to_seconds(time_str):
    """将 'mm:ss' 格式的时间转换为秒数整数"""
    try:
        if ':' in time_str:
            m, s = map(int, time_str.split(':'))
            return m * 60 + s
        return int(time_str)
    except:
        return 0

def bulk_import_map_configs(conn, data_list):
    """
    批量导入地图配置。
    data_list 中的 time_label 如果是 '1:20' 格式，将自动计算 time_value。
    """
    sql = """
    INSERT OR REPLACE INTO map_configs 
    (map_name, time_label, time_value, count_value, event_text, army_text, sound_filename, hero_text)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    processed_data = []
    for item in data_list:
        # 自动换算：$$TotalSeconds = Minutes \times 60 + Seconds$$
        t_val = convert_time_to_seconds(str(item['time_label']))
        processed_data.append((
            item['map_name'], item['time_label'], t_val, item.get('count_value'),
            item.get('event_text'), item.get('army_text'), item.get('sound_filename'), item.get('hero_text')
        ))
    
    conn.executemany(sql, processed_data)
    conn.commit()