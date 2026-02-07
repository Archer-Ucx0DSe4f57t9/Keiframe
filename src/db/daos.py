#daos.py
#dbs 相关的数据访问对象 (DAO) 定义
#负责与数据库进行交互，执行查询和数据操作




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
    SELECT * FROM mutator_meta ORDER BY sort_order ASC;
    """
    cur = conn.execute(sql)
    rows = cur.fetchall()
    return  [row[0] for row in rows]

def get_all_notify_mutator_names(conn):
    sql = """
    SELECT mutator_name FROM mutator_meta WHERE need_notify = 1 ORDER BY sort_order ASC;
    """
    cur = conn.execute(sql)
    rows = cur.fetchall()
    return  [row[0] for row in rows]
#测试代码
if __name__ == "__main__":
    from src.db.db_manager import DBManager

    db_manager = DBManager()
    maps_conn = db_manager.get_maps_conn()
    mutators_conn = db_manager.get_mutators_conn()

    # 测试加载地图
    map_name = "克哈裂痕"
    mutator_name = "AggressiveDeploymentProtoss"
    mutators = load_mutator_by_name(mutators_conn, mutator_name)
    for mutator_row in mutators:
        print(mutator_row['mutator_name'], mutator_row['time_value'], mutator_row['content_text'])
    print(get_all_mutator_names(mutators_conn))
    print(get_all_notify_mutator_names(mutators_conn))