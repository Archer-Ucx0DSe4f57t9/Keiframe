# src/settings_window/setting_data_handler.py
# 这个文件定义了 SettingsHandler 类，负责处理设置界面中的数据加载、保存和 Excel 导入逻辑
import json, os, copy
from src import config
from src.db import map_daos, mutator_daos
from src.utils.excel_utils import ExcelUtil
from src.utils.data_validator import DataValidator

class SettingsHandler:
    def __init__(self, settings_file, maps_db=None, mutators_db=None):
        self.settings_file = settings_file
        self.maps_db = maps_db
        self.mutators_db = mutators_db

    def load_config(self):
        """整合默认 config.py 和本地 settings.json"""
        config_dict = {
            # ===== 常规 =====
            'current_language': getattr(config, 'current_language', 'zh'),
            'LOG_LEVEL': getattr(config, 'LOG_LEVEL', 'WARNING'),
            'debug_mode': getattr(config, 'debug_mode', False),
            'debug_time_factor': getattr(config, 'debug_time_factor', 5.0),

            # ===== 快捷键 =====
            'MAP_SHORTCUT': getattr(config, 'MAP_SHORTCUT', ''),
            'LOCK_SHORTCUT': getattr(config, 'LOCK_SHORTCUT', ''),
            'SCREENSHOT_SHORTCUT': getattr(config, 'SCREENSHOT_SHORTCUT', ''),
            'MEMO_TEMP_SHORTCUT': getattr(config, 'MEMO_TEMP_SHORTCUT', ''),
            'MEMO_TOGGLE_SHORTCUT': getattr(config, 'MEMO_TOGGLE_SHORTCUT', ''),
            'COUNTDOWN_SHORTCUT': getattr(config, 'COUNTDOWN_SHORTCUT', ''),

            # ===== 主窗口与界面 =====
            'MAIN_WINDOW_POS': (getattr(config, 'MAIN_WINDOW_X', 1000), getattr(config, 'MAIN_WINDOW_Y', 100)),
            'MAIN_WINDOW_WIDTH': getattr(config, 'MAIN_WINDOW_WIDTH', 200),
            'MAIN_WINDOW_BG_COLOR': getattr(config, 'MAIN_WINDOW_BG_COLOR', 'rgba(43, 43, 43, 200)'),
            'TABLE_FONT_SIZE': getattr(config, 'TABLE_FONT_SIZE', 12),
            'TABLE_HEIGHT': getattr(config, 'TABLE_HEIGHT', 150),

            # ===== 地图事件配置 =====
            'MAP_ALERT_SECONDS': getattr(config, 'MAP_ALERT_SECONDS', 30),
            'MAP_ALERT_WARNING_THRESHOLD_SECONDS': getattr(config, 'MAP_ALERT_WARNING_THRESHOLD_SECONDS', 10),
            'MAP_ALERT_NORMAL_COLOR': getattr(config, 'MAP_ALERT_NORMAL_COLOR', 'rgb(239, 255, 238)'),
            'MAP_ALERT_WARNING_COLOR': getattr(config, 'MAP_ALERT_WARNING_COLOR', 'rgb(255, 0, 0)'),
            'TOAST_OFFSET_X': getattr(config, 'TOAST_OFFSET_X', 19),
            'TOAST_OFFSET_Y': getattr(config, 'TOAST_OFFSET_Y', 540),
            'TOAST_LINE_HEIGHT': getattr(config, 'TOAST_LINE_HEIGHT', 32),
            'TOAST_FONT_SIZE': getattr(config, 'TOAST_FONT_SIZE', 20),
            'MAP_SEARCH_KEYWORDS': getattr(config, 'MAP_SEARCH_KEYWORDS', {}),

            # ===== 突变事件配置 =====
            'MUTATOR_ALERT_SECONDS': getattr(config, 'MUTATOR_ALERT_SECONDS', 49),
            'MUTATOR_WARNING_THRESHOLD_SECONDS': getattr(config, 'MUTATOR_WARNING_THRESHOLD_SECONDS', 10),
            'MUTATOR_NORMAL_COLOR': getattr(config, 'MUTATOR_NORMAL_COLOR', 'rgb(255, 255, 255)'),
            'MUTATOR_WARNING_COLOR': getattr(config, 'MUTATOR_WARNING_COLOR', 'rgb(255, 0, 0)'),

            'MUTATOR_ALERT_OFFSET_X': getattr(config, 'MUTATOR_ALERT_OFFSET_X', 19),
            'MUTATOR_ALERT_OFFSET_Y': getattr(config, 'MUTATOR_ALERT_OFFSET_Y', 324),
            'MUTATOR_ALERT_LINE_HEIGHT': getattr(config, 'MUTATOR_ALERT_LINE_HEIGHT', 32),
            'MUTATOR_ALERT_FONT_SIZE': getattr(config, 'MUTATOR_ALERT_FONT_SIZE', 19),
            
            'MUTATOR_ICON_TRANSPARENCY': getattr(config, 'MUTATOR_ICON_TRANSPARENCY', 0.7),
            
            # ===== 自定义倒计时配置 =====
            'COUNTDOWN_OPTIONS': getattr(config, 'COUNTDOWN_OPTIONS', []),
            'COUNTDOWN_MAX_CONCURRENT': getattr(config, 'COUNTDOWN_MAX_CONCURRENT', 3),
            'COUNTDOWN_WARNING_THRESHOLD_SECONDS': getattr(config, 'COUNTDOWN_WARNING_THRESHOLD_SECONDS', 10),
            'COUNTDOWN_DISPLAY_COLOR': getattr(config, 'COUNTDOWN_DISPLAY_COLOR', 'rgb(0, 255, 255)'),

            # ===== 声音配置 =====
            'ALERT_SOUND_COOLDOWN': getattr(config, 'ALERT_SOUND_COOLDOWN', 10),
            'ALERT_SOUND_VOLUME': getattr(config, 'ALERT_SOUND_VOLUME', 90),

            # ===== 笔记 =====
            'MEMO_OPACITY': getattr(config, 'MEMO_OPACITY', 1.0),
            'MEMO_DURATION': getattr(config, 'MEMO_DURATION', 5000),
            'MEMO_FADE_TIME': getattr(config, 'MEMO_FADE_TIME', 1000),

            # ===== 图像识别 =====
            '''
            'GAME_SCREEN_DPI': getattr(config, 'GAME_SCREEN_DPI', 96),
            'GAME_ICO_RECONGIZE_INTERVAL': getattr(config, 'GAME_ICO_RECONGIZE_INTERVAL', 1),
            'GAME_ICO_RECONGIZE_CONFIDENCE': getattr(config, 'GAME_ICO_RECONGIZE_CONFIDENCE', 0.9),
            'DEBUG_SHOW_ENEMY_INFO_SQUARE': getattr(config, 'DEBUG_SHOW_ENEMY_INFO_SQUARE', False),
            'GAME_ICO_RECONGIZE_TIMEOUT': getattr(config, 'GAME_ICO_RECONGIZE_TIMEOUT', 300),
            '''

            'GAME_ICON_POS_AMON_RACE': getattr(config, 'GAME_ICON_POS_AMON_RACE', [45, 300, 36, 36]),
            'GAME_ICON_POS_AMON_TROOPS': getattr(config, 'GAME_ICON_POS_AMON_TROOPS', [1710, 938, 1904, 1035]),

            'MUTATOR_AND_ENEMY_RACE_RECOGNIZER_ROI': getattr(config, 'MUTATOR_AND_ENEMY_RACE_RECOGNIZER_ROI', (1850, 50, 1920, 800)),
            'ENEMY_COMP_RECOGNIZER_ROI': getattr(config, 'ENEMY_COMP_RECOGNIZER_ROI', (1450, 373 ,1920 ,800)),

            'MALWARFARE_PURIFIED_COUNT_TOP_LEFT_COORD': getattr(config, 'MALWARFARE_PURIFIED_COUNT_TOP_LEFT_COORD', (298, 85)),
            'MALWARFARE_PURIFIED_COUNT_BOTTOMRIGHT_COORD': getattr(config, 'MALWARFARE_PURIFIED_COUNT_BOTTOMRIGHT_COORD', (334, 103)),
            'MALWARFARE_TIME_TOP_LFET_COORD': getattr(config, 'MALWARFARE_TIME_TOP_LFET_COORD', (431, 85)),
            'MALWARFARE_TIME_BOTTOM_RIGHT_COORD': getattr(config, 'MALWARFARE_TIME_BOTTOM_RIGHT_COORD', (475, 103)),
            'MALWARFARE_PAUSED_TOP_LFET_COORD': getattr(config, 'MALWARFARE_PAUSED_TOP_LFET_COORD', (343, 85)),
            'MALWARFARE_PAUSED_BOTTOM_RIGHT_COORD': getattr(config, 'MALWARFARE_PAUSED_BOTTOM_RIGHT_COORD', (420, 103)),
            'MALWARFARE_HERO_OFFSET':getattr(config, 'MALWARFARE_HERO_OFFSET', 97),
            'MALWARFARE_ZWEIHAKA_OFFSET':getattr(config, 'MALWARFARE_ZWEIHAKA_OFFSET', 181),
            'MALWARFARE_REPLAY_OFFSET':getattr(config, 'MALWARFARE_REPLAY_OFFSET', 49),

        }

        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    user_cfg = json.load(f)
                    config_dict.update(user_cfg)
            except Exception as e:
                self.logger.error(f"读取设置文件失败: {e}")
        
        return config_dict

    def save_all(self, new_config, nested_roi, keyword_dict):
        """执行保存逻辑，包括数据库同步"""
        # 1. 同步关键词到数据库
        if keyword_dict and self.maps_db:
            map_daos.update_keywords_batch(self.maps_db, keyword_dict)
        
        # 2. 处理 ROI 嵌套数据
        new_config['MALWARFARE_ROI'] = nested_roi
        
        # 3. 写入 JSON
        with open(self.settings_file, 'w', encoding='utf-8') as f:
            json.dump(new_config, f, indent=4, ensure_ascii=False)
        return True

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
    
    def get_all_map_data(self):
        """导出专用：从数据库抓取全量地图配置"""
        if not self.maps_db: return []
        all_data = []
        for name in map_daos.get_all_map_names(self.maps_db):
            rows = map_daos.load_map_by_name(self.maps_db, name)
            for r in rows:
                all_data.append({
                    'map_name': r['map_name'],
                    'time_label': r['time']['label'],
                    'count_value': r['count'],
                    'event_text': r['event'],
                    'sound_filename': r['sound']
                })
        return all_data
    
    def export_to_excel(self, config_type, path):
        """具体导出逻辑"""
        if config_type == 'map' and self.maps_db:
            all_data = [] # ... 执行原本 on_export_data 里的查询逻辑
            ExcelUtil.export_configs(all_data, path, 'map')