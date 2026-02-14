# src/settings_window/setting_data_handler.py
# 这个文件定义了 SettingsHandler 类，负责处理设置界面中的数据加载、保存和 Excel 导入逻辑
import json, os, copy
from src import config
from src.db import map_daos, mutator_daos
from src.utils.excel_utils import ExcelUtil
from src.utils.data_validator import DataValidator
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
            'headers': ["时间点 (Label)", "提醒内容", "声音文件"],
            'mapping': ['time_label', 'content_text', 'sound_filename']
        }
    }
    def __init__(self, settings_file, maps_db=None, mutators_db=None):
        self.settings_file = settings_file
        self.maps_db = maps_db
        self.mutators_db = mutators_db
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
                print(f"从数据库加载关键词失败: {e}")

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
        """
        验证并导入数据
        返回: (bool 成功标志, list 错误信息列表/成功消息)
        """
        # 1. 解析 Excel
        raw_data, parse_err = ExcelUtil.import_configs(file_path, config_type)
        if parse_err:
            return False, [f"文件解析失败: {parse_err}"]

        # 2. 执行业务校验
        # 使用传入的数据库连接实例化校验器
        validator = None
        if config_type == 'map': 
            validator = DataValidator(self.maps_db)
        elif config_type == 'mutator':
            validator = DataValidator(self.mutators_db)
        else:
            return False, [f"未知的配置类型: {config_type}"]

        valid_data, validation_errors = validator.validate(config_type, raw_data)
        if validation_errors:
            # 如果有错，返回错误列表给 UI 显示
            return False, validation_errors

        # 3. 校验通过，执行写入
        try:
            if config_type == 'map':
                map_daos.bulk_import_map_configs(self.maps_db, valid_data)
            # 可以扩展 mutator 的导入
            return True, f"成功导入 {len(valid_data)} 条配置"
        except Exception as e:
            return False, [f"数据库写入异常: {str(e)}"]
    
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
    
    def get_all_map_configs_for_export(self):
        """获取全量地图配置用于 Excel 导出"""
        if not self.maps_db: return []
        all_data = []
        # 使用你提供的 get_all_map_names
        map_names = map_daos.get_all_map_names(self.maps_db)
        for name in map_names:
            # 使用你提供的 load_map_by_name
            rows = map_daos.load_map_by_name(self.maps_db, name)
            for r in rows:
                all_data.append({
                    'map_name': r['map_name'],
                    'time_label': r['time']['label'],
                    'count_value': r['count'],
                    'event_text': r['event'],
                    'army_text': r['army'],
                    'sound_filename': r['sound'],
                    'hero_text': r['hero']
                })
        return all_data
    
    def export_to_excel(self, config_type, path):
        """具体导出逻辑"""
        if config_type == 'map' and self.maps_db:
            all_data = [] # ... 执行原本 on_export_data 里的查询逻辑
            ExcelUtil.export_configs(all_data, path, 'map')

    def get_names_by_type(self, config_type):
        """获取地图或突变因子的名称列表（支持翻译）"""
        if config_type == 'map':
            return map_daos.get_all_map_names(self.maps_db)
        elif config_type == 'mutator':
            raw_names = mutator_daos.get_all_mutator_names(self.mutators_db)
            # 返回 (原始名, 显示名) 的元组列表
            return [(n, mutator_names_to_CHS.get(n, n)) for n in raw_names]
        else:
            return []

    def get_data_by_name(self, config_type, name):
        """获取特定项的详细背板配置数据"""
        if config_type == 'map':
            return map_daos.load_map_by_name(self.maps_db, name)
        elif config_type == 'mutator':
            return mutator_daos.load_mutator_by_name(self.mutators_db, name)
        else:
            return []