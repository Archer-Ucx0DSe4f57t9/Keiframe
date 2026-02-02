#db_manager.py
#数据库管理器，负责创建和管理数据库连接
import sqlite3
from src.utils.fileutil import get_resources_dir


class DBManager:
    def __init__(self):
        self.maps_db_path = get_resources_dir("db", "maps.db")
        self.mutators_db_path = get_resources_dir("db", "mutators.db")
        print(f"Maps DB Path: {self.maps_db_path}")
        print(f"Mutators DB Path: {self.mutators_db_path}")
        self._maps_conn = None
        self._mutators_conn = None

    def get_maps_conn(self):
        if self._maps_conn is None:
            self._maps_conn = sqlite3.connect(
                self.maps_db_path,
                check_same_thread=False
            )
            self._maps_conn.row_factory = sqlite3.Row
        return self._maps_conn

    def get_mutators_conn(self):
        if self._mutators_conn is None:
            self._mutators_conn = sqlite3.connect(
                self.mutators_db_path,
                check_same_thread=False
            )
            self._mutators_conn.row_factory = sqlite3.Row
        return self._mutators_conn

    def close_all(self):
        if self._maps_conn:
            self._maps_conn.close()
        if self._mutators_conn:
            self._mutators_conn.close()
