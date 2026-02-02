#daos.py
#dbs 相关的数据访问对象 (DAO) 定义
from pypinyin import lazy_pinyin, Style
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
  return cur.fetchall()

# 获取所有不同的地图名称
def get_all_map_names(conn):
    sql = """
    SELECT DISTINCT map_name
    FROM map_configs
    """
    cur = conn.execute(sql)
    rows = cur.fetchall()
    return [row[0] for row in rows]

def load_mutators_for_time(conn, mutator_name):
  #键值：	"mutator_name",	"time_label", "time_value",	"content_text","sound_filename"
    sql = """
    SELECT *
    FROM mutator_configs
    WHERE mutator_name = ?
    ORDER BY time_value ASC
    """
    cur = conn.execute(sql, (mutator_name,))
    return cur.fetchall()
  
if __name__ == "__main__":
    from src.db.db_manager import DBManager

    db_manager = DBManager()
    maps_conn = db_manager.get_maps_conn()
    mutators_conn = db_manager.get_mutators_conn()

    # 测试加载地图
    map_name = "克哈裂痕"
    maps = load_map_by_name(maps_conn, map_name)
    for map_row in maps:
        print(map_row['map_name'], map_row['count_value'],map_row['time_label'],map_row['time_value'], map_row['event_text'], map_row['army_text'] ,map_row['sound_filename'],map_row['hero_text'])
    # 测试加载突变
    mutator_name = "AggressiveDeploymentProtoss"
    mutators = load_mutators_for_time(mutators_conn, mutator_name)
    for mutator_row in mutators:
        print(mutator_row['mutator_name'], mutator_row['time_value'], mutator_row['content_text'])
        
    print(get_all_map_names(maps_conn))