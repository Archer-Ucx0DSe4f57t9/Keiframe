import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Protection
from src.utils.temp_translate_utils import MAP_HEADER_MAP, MUTATOR_HEADER_MAP
import datetime
import os

class ExcelUtil:
    @staticmethod
    def export_configs(data_list, file_path, config_type='map'):
        """
        将数据库列表导出为 Excel，并锁定名称列
        """
        # 1. 准备数据与映射
        header_map = MAP_HEADER_MAP if config_type == 'map' else MUTATOR_HEADER_MAP
        df = pd.DataFrame(data_list)
        
        # 只保留需要的列并重命名
        cols_to_keep = [c for c in header_map.keys() if c in df.columns]
        df = df[cols_to_keep].rename(columns=header_map)

        # 2. 写入 Excel
        with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Sheet1')
            
        # 3. 锁定特定列防止用户修改关联关系
        ExcelUtil._apply_protection(file_path)

    @staticmethod
    def _apply_protection(file_path):
        """锁定名称列，并强制时间列为文本格式"""
        wb = load_workbook(file_path)
        ws = wb.active
        
        # 假设 '提醒时间点' 在第二列 (B列)
        for cell in ws['B']:
            cell.number_format = '@'  # 强制设为文本格式
            
        for row in ws.iter_rows():
            for cell in row:
                cell.protection = Protection(locked=False)
                # 第一列（名称）锁定，防止破坏关联
                if cell.column == 1:
                    cell.protection = Protection(locked=True)
        
        ws.protection.sheet = True
        wb.save(file_path)

    @staticmethod
    def import_configs(file_path, config_type='map'):
        """
        读取 Excel 并转换回数据库格式，自动计算秒数
        """
        header_map = MAP_HEADER_MAP if config_type == 'map' else MUTATOR_HEADER_MAP
        # 反转映射表用于读取：{'中文表头': 'db_field'}
        rev_map = {v: k for k, v in header_map.items()}
        
        try:
            df = pd.read_excel(file_path)
            # 校验表头合法性
            if not all(col in df.columns for col in rev_map.keys()):
                return None, "Excel 格式错误：缺少必要的表头列。"

            df = df.rename(columns=rev_map)
            
            # 转换为 dict 列表
            raw_data = df.to_dict(orient='records')
            
            # 数据合法性初步检查：时间格式必须包含冒号或为数字
            valid_data = []
            for row in raw_data:
                time_str = str(row.get('time_label', ''))
                if ':' in time_str or time_str.isdigit():
                    valid_data.append(row)
                else:
                    print(f"警告：忽略非法时间格式行 - {row}")

            return valid_data, None
        except Exception as e:
            return None, str(e)


    @staticmethod
    def parse_time_label(label):
        """
        全兼容的时间解析逻辑
        解决 Excel 自动将 8:25 转为 0.350694444 的问题
        """
        # 1. 处理已经是时间对象的情况 (Pandas 自动转换)
        if isinstance(label, (datetime.time, datetime.datetime)):
            # 如果是 8:25，Excel 默认认为是 8h 25m 0s
            # 在 SC2 计时器场景下，我们通常将其视为 8分25秒
            # 如果总秒数过大（例如超过1小时），可以根据业务逻辑判断是否缩减
            total_seconds = label.hour * 3600 + label.minute * 60 + label.second
            
            # 逻辑兜底：如果在游戏计时中出现 8小时，极大概率是用户输入 8:25 被 Excel 误认
            if label.hour > 0 and label.hour < 12: # 假设游戏不会超过12小时
                # 尝试将 hour 视为 minute，minute 视为 second
                return label.hour * 60 + label.minute
            return total_seconds

        # 2. 处理浮点数 (Excel 原始 Serial Number)
        if isinstance(label, float):
            # 浮点数转为总秒数
            total_seconds = int(round(label * 86400))
            # 同样的逻辑判断：如果超过 3600 秒且小时位有值
            if total_seconds >= 3600:
                # 还原出小时和分钟，重新计算为 分:秒
                h = total_seconds // 3600
                m = (total_seconds % 3600) // 60
                return h * 60 + m
            return total_seconds

        # 3. 处理标准字符串 "8:25" 或 "0:8:25"
        try:
            s_label = str(label).strip()
            parts = list(map(int, s_label.split(':')))
            if len(parts) == 3: # h:m:s
                return parts[0] * 3600 + parts[1] * 60 + parts[2]
            elif len(parts) == 2: # m:s
                return parts[0] * 60 + parts[1]
            return int(s_label)
        except:
            return 0