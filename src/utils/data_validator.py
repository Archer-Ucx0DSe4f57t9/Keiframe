# src/utils/data_validator.py
import pandas as pd
from src.db import map_daos, mutator_daos
from src.utils.excel_utils import ExcelUtil
from src.utils.temp_translate_utils import mutator_names_to_CHS

import re

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
        """执行严格的时间格式和名称校验"""
        if config_type not in self._registry:
            return None, ["未知配置类型"]
        
        cfg = self._registry[config_type]
        allowed_names = set(cfg['fetch_func'](self.conn)) #
        
        # 严格正则：必须是 分:秒，且秒数不能超过 59
        time_pattern = re.compile(r'^([0-6]?\d):([0-5]\d)$') 
        
        
        rev_mutator_map = {}
        if config_type == 'mutator':
            rev_mutator_map = {v: k for k, v in mutator_names_to_CHS.items()}
        
        
        errors, valid_rows = [], []
        for i, row in enumerate(data_list):
            line = i + 2  # Excel 行号补偿（标题行+索引）
            row_errs = []
            
            # 1. 名称合法性校验
            raw_name = str(row.get(cfg['id_field'], '')).strip()
            internal_name = raw_name
            
            if config_type == 'mutator' and raw_name in rev_mutator_map:
                internal_name = rev_mutator_map[raw_name]
            
            if not internal_name or internal_name not in allowed_names:
                row_errs.append(f"名称 '{raw_name}' 在数据库中不存在")
            else:
                #将 row 里的名称更新为数据库识别的英文名，确保后续 DAO 写入正确
                row[cfg['id_field']] = internal_name

            # 2. 严格时间解析校验（拦截脏数据）
            label = str(row.get('time_label', '')).strip()
            if not time_pattern.match(label):
                row_errs.append(f"时间格式非法: '{label}' (正确示例: 1:20)")
            else:
                # 只有正则通过，才进行换算并存入 row 供后续 DAO 直接使用
                row['time_value'] = ExcelUtil.parse_time_label(label) #

            # 3. 特有规则逻辑...
            row_errs.extend(cfg['specific_rules'](row, internal_name))

            if row_errs:
                errors.append(f"第 {line} 行: " + " | ".join(row_errs))
            else:
                valid_rows.append(row)
        
        # 返回已校验行及错误列表。如果 errors 不为空，UI 层应停止导入。
        return valid_rows, errors

    def _map_specific_rules(self, row, name):
        errs = []
        if name == '净网行动':
            cv = row.get('count_value')
            if pd.isna(cv) or not str(cv).isdigit() or int(cv) < 0:
                errs.append(f"净网行动计数值应为正整数，当前: {cv}")
        return errs

    def _mutator_specific_rules(self, row, name): return []