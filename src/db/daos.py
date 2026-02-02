#daos.py
#dbs 相关的数据访问对象 (DAO) 定义
def load_map_by_name(conn, map_name):
    sql = """
    SELECT *
    FROM map_configs
    WHERE map_name = ?
    ORDER BY time_value ASC
    """
    cur = conn.execute(sql, (map_name,))
    return cur.fetchall()
  
def load_mutators_for_time(conn, mutator_name):
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
    map_name = "净网行动"
    maps = load_map_by_name(maps_conn, map_name)
    for map_row in maps:
        print(dict(map_row))

    # 测试加载突变
    mutator_name = "AggressiveDeploymentProtoss"
    mutators = load_mutators_for_time(mutators_conn, mutator_name)
    for mutator_row in mutators:
        print(dict(mutator_row)) # 加上 dict() 转换，打印更清晰