# map_event_manager.py
import traceback
from PyQt5.QtGui import QBrush, QColor
from PyQt5.QtCore import Qt
import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config
import time  # 添加 time 模块用于调试
import game_monitor


class MapEventManager:
    def __init__(self, table_area, toast_manager, logger):
        """
        初始化地图事件管理器
        :param table_area: QTableWidget 实例
        :param toast_manager: ToastManager 实例
        :param logger: 日志对象
        """
        self.table_area = table_area
        self.toast_manager = toast_manager
        self.logger = logger
        self.last_seconds = -1  # 用于避免重复高亮和提示

    def update_events(self, current_seconds, game_screen) -> object:
        """
        根据当前游戏时间更新表格颜色和Toast提示
        :param current_seconds: 当前游戏时间（秒）
        """
        # 避免在同一秒内重复执行，除非秒数改变
        if int(current_seconds) == self.last_seconds:
            self.logger.debug(f'时间未变化，跳过更新,当前时间{current_seconds}')
            return

        self.last_seconds = int(current_seconds)
        self.logger.debug(f'正在执行地图事件检查,当前时间{current_seconds}')
        start_time = time.time()
        try:
            closest_row = 0
            min_diff = float('inf')
            next_event_row = -1
            next_event_seconds = float('inf')

            # 第一次遍历：找出下一个即将触发的事件
            for row in range(self.table_area.rowCount()):
                time_item = self.table_area.item(row, 0)
                if time_item and time_item.text():
                    try:
                        time_parts = time_item.text().split(':')
                        row_seconds = 0
                        if len(time_parts) == 2:  # MM:SS
                            row_seconds = int(time_parts[0]) * 60 + int(time_parts[1])
                        elif len(time_parts) == 3:  # HH:MM:SS
                            row_seconds = int(time_parts[0]) * 3600 + int(time_parts[1]) * 60 + int(time_parts[2])

                        if row_seconds > current_seconds and row_seconds < next_event_seconds:
                            next_event_seconds = row_seconds
                            next_event_row = row

                        diff = abs(current_seconds - row_seconds)
                        if diff < min_diff:
                            min_diff = diff
                            closest_row = row
                    except ValueError:
                        continue
            
            is_heroes_from_the_storm_active = False
            if game_monitor.state.active_mutators and 'HeroesFromtheStorm' in game_monitor.state.active_mutators:
                is_heroes_from_the_storm_active = True
            
            # 第二次遍历：设置颜色和触发提示
            for row in range(self.table_area.rowCount()):
                time_item = self.table_area.item(row, 0)
                event_item = self.table_area.item(row, 1)
                army_item = self.table_area.item(row, 2)
                if time_item and time_item.text():
                    try:
                        time_parts = time_item.text().split(':')
                        row_seconds = 0
                        if len(time_parts) == 2:
                            row_seconds = int(time_parts[0]) * 60 + int(time_parts[1])
                        elif len(time_parts) == 3:
                            row_seconds = int(time_parts[0]) * 3600 + int(time_parts[1]) * 60 + int(time_parts[2])

                        if row_seconds < current_seconds:
                            time_item.setForeground(QBrush(QColor(128, 128, 128, 255)))
                            time_item.setBackground(QBrush(QColor(0, 0, 0, 0)))
                            if event_item:
                                event_item.setForeground(QBrush(QColor(128, 128, 128, 255)))
                                event_item.setBackground(QBrush(QColor(0, 0, 0, 0)))
                        elif row == next_event_row:
                            time_item.setForeground(QBrush(
                                QColor(config.TABLE_NEXT_FONT_COLOR[0], config.TABLE_NEXT_FONT_COLOR[1],
                                       config.TABLE_NEXT_FONT_COLOR[2])))
                            time_item.setBackground(QBrush(
                                QColor(config.TABLE_NEXT_FONT_BG_COLOR[0], config.TABLE_NEXT_FONT_BG_COLOR[1],
                                       config.TABLE_NEXT_FONT_BG_COLOR[2], config.TABLE_NEXT_FONT_BG_COLOR[3])))
                            if event_item:
                                event_item.setForeground(QBrush(
                                    QColor(config.TABLE_NEXT_FONT_COLOR[0], config.TABLE_NEXT_FONT_COLOR[1],
                                           config.TABLE_NEXT_FONT_COLOR[2])))
                                event_item.setBackground(QBrush(
                                    QColor(config.TABLE_NEXT_FONT_BG_COLOR[0], config.TABLE_NEXT_FONT_BG_COLOR[1],
                                           config.TABLE_NEXT_FONT_BG_COLOR[2], config.TABLE_NEXT_FONT_BG_COLOR[3])))
                    except ValueError:
                        continue

            # 第三次遍历：更新提醒和销毁过时提醒    
            for row in range(self.table_area.rowCount()):
                time_item = self.table_area.item(row, 0)
                event_item = self.table_area.item(row, 1)
                army_item = self.table_area.item(row, 2)
                sound_item = self.table_area.item(row, 3)
                hero_item = self.table_area.item(row, 4)
                
                if time_item and time_item.text():
                    try:
                        time_parts = time_item.text().split(':')
                        row_seconds = 0
                        if len(time_parts) == 2:  # MM:SS
                            row_seconds = int(time_parts[0]) * 60 + int(time_parts[1])
                        elif len(time_parts) == 3:  # HH:MM:SS
                            row_seconds = int(time_parts[0]) * 3600 + int(time_parts[1]) * 60 + int(time_parts[2])
                        time_diff = row_seconds - current_seconds
                        event_id = f"map_event_{row}"  # 使用行号作为唯一ID

                        if time_diff > 0 and time_diff <= config.MAP_ALERT_SECONDS:
                            toast_message = (
                                f'{time_diff:0>2}秒后'
                                + f"{time_item.text()}\t{event_item.text()}"
                                + (f"\t{army_item.text()}" if army_item else "")
                                + (f"风暴: \t{hero_item.text()}" if is_heroes_from_the_storm_active and len(hero_item.text())>0 else "")
                            )
                            sound_filename = sound_item.text().strip() if sound_item else ""
                            # 调用 ToastManager 的新方法
                            self.logger.debug(f'正在调用toast_manager播报地图事件')
                            self.toast_manager.show_map_countdown_alert(event_id, time_diff, toast_message, game_screen,sound_filename)
                        else:
                            if self.toast_manager.has_alert(event_id):
                                self.toast_manager.remove_alert(event_id)

                    except ValueError:
                        continue



                        # ... 其他颜色逻辑保持不变



            # 滚动位置逻辑
            if self.table_area.rowHeight(0) == 0:
                return
            else:
                visible_rows = self.table_area.height() // self.table_area.rowHeight(0)
            scroll_position = max(0, closest_row - (visible_rows // 2))
            self.table_area.verticalScrollBar().setValue(scroll_position)

        except Exception as e:
            self.logger.error(f'调整表格滚动位置和颜色失败: {str(e)}\n{traceback.format_exc()}')

        self.logger.debug(f'本次地图事件更新耗时：{time.time() - start_time:.2f}秒')

    def hide_all_alerts(self):
        """隐藏所有与此管理器相关的提示"""
        # 在这里调用 ToastManager 的隐藏方法
        self.toast_manager.hide_toast()