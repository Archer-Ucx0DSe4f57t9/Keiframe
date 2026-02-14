# src/db/mutator_daos.py

# 根据突变名称加载突变配置
def load_mutator_by_name(conn, mutator_name):
  #键值：	"mutator_name",	"time_label", "time_value",	"content_text","sound_filename"
    sql = """
    SELECT *
    FROM mutator_configs
    WHERE mutator_name = ?
    ORDER BY time_value ASC
    """
    cur = conn.execute(sql, (mutator_name,))
    rows = cur.fetchall()
    result = []
    # 组织结果为字典列表，便于日后数据库修改
    for r in rows:
        result.append({
            "mutator_name": r["mutator_name"],
            "time": {
                "label": r["time_label"],
                "value": r["time_value"],
            },
            "content": r["content_text"],
            "sound": r["sound_filename"],
        })
    return result

# 获取所有突变列表
def get_all_mutator_names(conn):
    sql = """
    SELECT mutator_name FROM mutator_meta ORDER BY sort_order ASC;
    """
    cur = conn.execute(sql)
    rows = cur.fetchall()
    return  [row[0] for row in rows]

# 获取需要通知的突变列表
def get_all_notify_mutator_names(conn):
    sql = """
    SELECT mutator_name FROM mutator_meta WHERE need_notify = 1 ORDER BY sort_order ASC;
    """
    cur = conn.execute(sql)
    rows = cur.fetchall()
    return  [row[0] for row in rows]

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

def bulk_import_mutator_configs(conn, data_list):
    """批量导入突变配置"""
    sql = """
    INSERT OR REPLACE INTO mutator_configs 
    (mutator_name, time_label, time_value, content_text, sound_filename)
    VALUES (?, ?, ?, ?, ?)
    """
    processed_data = []
    for item in data_list:
        t_val = item.get('time_value')
        if t_val is None:
            t_val = convert_time_to_seconds(str(item['time_label']))
        processed_data.append((
            item['mutator_name'], item['time_label'], t_val, 
            item.get('content_text'), item.get('sound_filename')
        ))


    conn.executemany(sql, processed_data)
    conn.commit()