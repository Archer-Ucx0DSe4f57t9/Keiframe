# src/utils/data_validator.py
import pandas as pd
from src.db import map_daos, mutator_daos
from src.utils.excel_utils import ExcelUtil

class DataValidator:
    def __init__(self, conn):
        """初始化时传入数据库连接"""
        self.conn = conn
        self._registry = {
            'map': {
                'id_field': 'map_name',
                'fetch_func': map_daos.get_all_map_names,
                'specific_rules': self._map_specific_rules
            },
            'mutator': {
                'id_field': 'mutator_name',
                'fetch_func': mutator_daos.get_all_mutator_names,
                'specific_rules': self._mutator_specific_rules
            }
        }

    def validate(self, config_type, data_list):
        """执行可扩展的校验逻辑"""
        if config_type not in self._registry:
            return None, ["未知配置类型"]
        
        cfg = self._registry[config_type]
        # 动态获取当前数据库中所有合法的地图/因子名称
        allowed_names = set(cfg['fetch_func'](self.conn))
        
        errors, valid_rows = [], []
        for i, row in enumerate(data_list):
            line = i + 1
            row_errs = []
            
            # 1. 名称合法性校验
            name = str(row.get(cfg['id_field'], '')).strip()
            if not name or name not in allowed_names:
                row_errs.append(f"名称 '{name}' 不在数据库中")

            # 2. 时间解析校验
            if 'time_label' in row:
                t_val = ExcelUtil.parse_time_label(row['time_label'])
                if t_val <= 0 and str(row['time_label']) not in ["00:00", "0:00"]:
                    row_errs.append(f"时间 '{row['time_label']}' 意义不明")
                else:
                    row['time_value'] = t_val

            # 3. 特有规则 (如净网行动)
            row_errs.extend(cfg['specific_rules'](row, name))

            if row_errs:
                errors.append(f"第 {line} 行: " + " | ".join(row_errs))
            else:
                valid_rows.append(row)
        
        return valid_rows, errors

    def _map_specific_rules(self, row, name):
        errs = []
        if name == '净网行动':
            cv = row.get('count_value')
            if pd.isna(cv) or not str(cv).isdigit() or int(cv) < 0:
                errs.append(f"净网行动计数值应为正整数，当前: {cv}")
        return errs

    def _mutator_specific_rules(self, row, name): return []