# src/settings_window/setting_data_handler.py
# 这个文件定义了 SettingsHandler 类，负责处理设置界面中的数据加载、保存和 Excel 导入逻辑
import json, os, copy
from src import config
from src.db import map_daos, mutator_daos
from src.utils.excel_utils import ExcelUtil
from src.utils.data_validator import DataValidator
from src.utils.logging_util import get_logger
import inspect
from src.utils.temp_translate_utils import mutator_names_to_CHS
class SettingsHandler:
    # 1. 定义注册表：未来增加新类型只需在这里添加一项
    BACKPLANE_REGISTRY = {
        'map': {
            'name': "地图 (Map)",
            'db_conn_attr': 'maps_db',
            'table_name': 'map_configs',
            'id_col': 'map_name',
            'dao_load': map_daos.load_map_by_name,
            'dao_import': map_daos.bulk_import_map_configs,
            'dao_get_names': map_daos.get_all_map_names,
            'headers': ["时间点 (Label)", "节点 (净网限定)", "提醒事件", "科技等级", "声音文件", "风暴英雄"],
            # 这里的映射必须与 DAO 中的 bulk_import 键名严格一致
            'mapping': ['time_label', 'count_value', 'event_text', 'army_text', 'sound_filename', 'hero_text']
        },
        'mutator': {
            'name': "突变因子 (Mutator)",
            'db_conn_attr': 'mutators_db',
            'table_name': 'mutator_configs',
            'id_col': 'mutator_name',
            'dao_load': mutator_daos.load_mutator_by_name,
            'dao_import': mutator_daos.bulk_import_mutator_configs,
            'dao_get_names': mutator_daos.get_all_mutator_names,
            'headers': ["时间点 (Label)", "提醒内容", "声音文件"],
            'mapping': ['time_label', 'content_text', 'sound_filename']
        }
    }
    def __init__(self, settings_file, maps_db=None, mutators_db=None):
        self.settings_file = settings_file
        self.maps_db = maps_db
        self.mutators_db = mutators_db
        self.logger = get_logger(__name__)
    def _get_base_from_config_module(self):
        """从 config 模块中提取基础配置项，排除函数、类和模块等非数据项"""
        base_config = {}
        for k in dir(config):
            if k.startswith("__"): continue
            val = getattr(config, k)
            if not inspect.ismodule(val) and not inspect.isfunction(val) and not inspect.isclass(val):
                try:
                    base_config[k] = copy.deepcopy(val)
                except: continue
        return base_config
    
    def load_config(self):
        """深度加载配置并合成 UI 需使用的复合项"""
        base_config = self._get_base_from_config_module()
        
        # --- 修复 1: 合并合成项 (MAIN_WINDOW_POS) ---
        # 确保 UI 能够找到这个键，否则 add_row 会报警告
        base_config['MAIN_WINDOW_POS'] = [
            base_config.get('MAIN_WINDOW_X', 1000),
            base_config.get('MAIN_WINDOW_Y', 100)
        ]

        if self.maps_db:
            try:
                # 调用你提供的 map_daos.get_all_keywords
                db_keywords = map_daos.get_all_keywords(self.maps_db)
                # 即使 JSON 里没有，也要保证 UI 能看到数据库里的东西
                base_config['MAP_SEARCH_KEYWORDS'] = db_keywords
            except Exception as e:
                logger.error(f"从数据库加载关键词失败: {e}")

        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                    self._deep_update(base_config, user_config)
            except: pass
                
        return base_config
    
    def _deep_update(self, base_dict, update_dict):
        """递归合并字典，防止子字典（如 ROI）被整体覆盖"""
        for k, v in update_dict.items():
            if k in base_dict and isinstance(base_dict[k], dict) and isinstance(v, dict):
                self._deep_update(base_dict[k], v)
            else:
                base_dict[k] = v

    def validate_and_import(self, file_path, config_type='map'):
        """验证并导入数据：改为先删除 Excel 中涉及的地图/因子的旧数据，再重新插入"""
        # 1. 解析 Excel
        raw_data, parse_err = ExcelUtil.import_configs(file_path, config_type)
        if parse_err: return False, [parse_err]

        # 根据类型选择数据库连接
        reg = self.BACKPLANE_REGISTRY[config_type]
        db_conn = getattr(self, reg['db_conn_attr'])
        validator = DataValidator(db_conn)
        
        valid_data, validation_errors = validator.validate(config_type, raw_data)
        
        if validation_errors:
            return False, validation_errors

        # 2. 执行“覆盖式”写入逻辑
        try:
            # 提取 Excel 中涉及的所有唯一名称 (例如：['亡者之夜', '净网行动'])
            target_names = list(set(item[reg['id_col']] for item in valid_data))
            
            if target_names:
                # 物理删除这些目标的旧数据，确保 Excel 中删除的行也能反馈到数据库
                placeholders = ', '.join(['?'] * len(target_names))
                sql_delete = f"DELETE FROM {reg['table_name']} WHERE {reg['id_col']} IN ({placeholders})"
                db_conn.execute(sql_delete, target_names)
            
            # 批量插入新数据
            reg['dao_import'](db_conn, valid_data)
            db_conn.commit()
            
            return True, f"成功同步 {len(valid_data)} 条记录，已覆盖原有的 {len(target_names)} 个项目。"
        except Exception as e:
            return False, [f"写入失败: {str(e)}"]
    
    def save_backplane_to_db(self, config_type, target_name, data_list):
        """通用保存逻辑：不再使用 if-else 判断类型"""
        reg = self.BACKPLANE_REGISTRY.get(config_type)
        if not reg:
            return False, f"未知的配置类型: {config_type}"

        db_conn = getattr(self, reg['db_conn_attr'])
        if not db_conn:
            return False, "数据库连接未就绪"

        try:
            # 第一步：物理删除该目标下的所有旧数据（确保 UI 删掉的行在数据库也同步消失）
            # 注意：bulk_import 里的 INSERT OR REPLACE 只能处理更新，不能处理删除
            sql_delete = f"DELETE FROM {reg['table_name']} WHERE {reg['id_col']} = ?"
            db_conn.execute(sql_delete, (target_name,))
            
            # 第二步：调用对应的 DAO 函数执行插入
            # 此时传入的 data_list 中的键名必须符合 reg['mapping'] 的定义
            reg['dao_import'](db_conn, data_list)
            
            # 第三步：强制提交事务 (DAO 内部通常有 commit，但这里双重保险)
            db_conn.commit()
            
            return True, f"【{target_name}】的背板数据已同步"
        except Exception as e:
            return False, f"同步失败: {str(e)}"
    def save_all(self, config_data, keyword_dict=None):
        """保存配置并同步数据库关键词"""
        try:
            # 1. 保存到 JSON
            # 存入前可以清理掉 UI 专用的合成项，保持 JSON 简洁
            final_save_data = copy.deepcopy(config_data)
            
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(final_save_data, f, indent=4, ensure_ascii=False)
            
            # 2. 批量更新数据库关键词
            if keyword_dict is not None and self.maps_db:
                # 直接调用你提供的 map_daos 函数
                map_daos.update_keywords_batch(self.maps_db, keyword_dict)
                
            return True, "设置及关键词已成功保存"
        except Exception as e:
            return False, f"保存失败: {str(e)}"

    def process_excel_import(self, path, config_type):
        """导入 Excel 数据并校验"""
        raw_data, err = ExcelUtil.import_configs(path, config_type)
        if err: return False, err
        
        validator = DataValidator(self.maps_db)
        valid_data, errors = validator.validate(config_type, raw_data)
        
        if not errors:
            # 执行数据库写入
            if config_type == 'map':
                map_daos.bulk_import_map_configs(self.maps_db, valid_data)
            return True, len(valid_data)
        return False, errors
    
    def get_all_configs_for_export(self, config_type):
        """根据类型获取全量背板数据，用于 Excel 导出"""
        reg = self.BACKPLANE_REGISTRY.get(config_type)
        if not reg: return []
        
        db_conn = getattr(self, reg['db_conn_attr'])
        all_data = []
        
        # 简化版：直接遍历 names
        names = reg['dao_get_names'](db_conn)
        # 2. 遍历加载每项的配置
        for name in names:
            display_name = name
            if config_type == 'mutator':
                display_name = mutator_names_to_CHS.get(name, name)
            
            rows = reg['dao_load'](db_conn, name)
            for r in rows:
                # 扁平化数据以适配 Excel 结构
                item = {reg['id_col']: display_name}
                item['time_label'] = r['time']['label']if isinstance(r.get('time'), dict) else ""
                
                # 动态填充其他映射字段
                for col_key in reg['mapping']:
                    if col_key == 'time_label':continue # time_label 已特殊处理
                    source_key = col_key.replace('_text', '').replace('_filename', '').replace('_value', '')
                    if source_key == 'count': source_key = 'count' # 适配 map_daos
                    item[col_key] = r.get(source_key, '')
                
                all_data.append(item)
        return all_data
    
    def export_to_excel(self, config_type, path):
        """具体导出逻辑"""
        if config_type == 'map' and self.maps_db:
            all_data = [] # ... 执行原本 on_export_data 里的查询逻辑
            ExcelUtil.export_configs(all_data, path, 'map')

    def get_names_by_type(self, config_type):
        """统一返回格式为 [(原始名, 显示名), ...]"""
        results = []
        if config_type == 'map':
            # 获取所有地图名称
            names = map_daos.get_all_map_names(self.maps_db)
            # 地图不需要翻译，原始名和显示名一致
            results = [(n, n) for n in names]
        elif config_type == 'mutator':
            # 获取所有突变因子英文名
            raw_names = mutator_daos.get_all_mutator_names(self.mutators_db)
            # 即使翻译表中没有，也至少保证有两个元素
            results = [(n, mutator_names_to_CHS.get(n, n)) for n in raw_names]
        
        # 增加防御性检查：过滤掉不符合 (a, b) 格式的脏数据
        return [item for item in results if isinstance(item, (list, tuple)) and len(item) == 2]

    def get_data_by_name(self, config_type, name):
        """获取特定项的详细背板配置数据"""
        if config_type == 'map':
            return map_daos.load_map_by_name(self.maps_db, name)
        elif config_type == 'mutator':
            return mutator_daos.load_mutator_by_name(self.mutators_db, name)
        else:
            return []