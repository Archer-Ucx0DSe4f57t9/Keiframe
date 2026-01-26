import traceback
from PyQt5.QtGui import QBrush, QColor
from PyQt5.QtCore import Qt
import time, sys, os
from src import config

class MapwarfareEventManager:
    def __init__(self, table_area, toast_manager, logger):
        """
        初始化净网地图事件管理器
        :param table_area: QTableWidget 实例
        :param toast_manager: ToastManager 实例
        :param logger: 日志对象
        """
        self.table_area = table_area
        self.toast_manager = toast_manager
        self.logger = logger
        self.last_count = -1
        self.last_seconds = -1

    def _parse_time_to_seconds(self, time_str):
        """将 MM:SS 或 HH:MM:SS 格式的时间字符串转换为秒"""
        parts = time_str.split(':')
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        raise ValueError("Invalid time format")

    def update_events(self, current_count, current_countdown_seconds, game_screen):
        """
        根据当前阶段(count)和倒计时更新表格颜色和Toast提示
        :param current_count: 当前的计数值
        :param current_countdown_seconds: 当前的倒计时（秒）
        :param game_screen: 游戏屏幕对象，用于定位Toast
        """
        # 避免在同一秒内或相同count下重复执行
        if self.last_count == current_count and int(current_countdown_seconds) == self.last_seconds:
            return

        self.last_count = current_count
        self.last_seconds = int(current_countdown_seconds)
        self.logger.debug(f'正在执行净网事件检查, count={current_count}, 倒计时={current_countdown_seconds:.2f}s')
        start_time = time.time()

        try:
            next_event_row = -1
            min_future_diff = float('inf')
            last_passed_row_in_count = -1

            # --- 第一次遍历：分析事件，找出当前count下下一个要发生的事件 ---
            for row in range(self.table_area.rowCount()):
                count_item = self.table_area.item(row, 0)
                time_item = self.table_area.item(row, 1) # 时间现在是第2列

                if not (count_item and count_item.text() and time_item and time_item.text()):
                    continue

                try:
                    row_count = int(count_item.text())
                    
                    # 只处理与当前count匹配的行
                    if row_count == current_count:
                        row_seconds = self._parse_time_to_seconds(time_item.text())
                        time_diff = row_seconds - current_countdown_seconds

                        if time_diff >= 0: # 事件在未来或刚刚发生
                            if time_diff < min_future_diff:
                                min_future_diff = time_diff
                                next_event_row = row
                        else: # 事件已在当前count中过去
                           last_passed_row_in_count = row

                except (ValueError, IndexError):
                    continue
            
            # --- 第二次遍历：更新UI（颜色、提示、滚动） ---
            for row in range(self.table_area.rowCount()):
                count_item = self.table_area.item(row, 0)
                time_item = self.table_area.item(row, 1)
                event_item = self.table_area.item(row, 2)
                army_item = self.table_area.item(row, 3)

                if not (count_item and count_item.text() and time_item and time_item.text()):
                    continue
                
                # 为所有单元格设置默认颜色（避免状态残留）
                for col in range(self.table_area.columnCount()):
                    item = self.table_area.item(row, col)
                    if item:
                        item.setForeground(QBrush(QColor(255, 255, 255))) # 假设默认是白色
                        item.setBackground(QBrush(QColor(0, 0, 0, 0)))   # 透明背景

                try:
                    row_count = int(count_item.text())
                    row_seconds = self._parse_time_to_seconds(time_item.text())
                    
                    # 确定行状态并上色
                    if row_count < current_count: # 已完成的阶段
                        for col in range(self.table_area.columnCount()):
                            item = self.table_area.item(row, col)
                            if item:
                                item.setForeground(QBrush(QColor(128, 128, 128, 255))) # 灰色
                    elif row_count == current_count: # 当前阶段
                        if row_seconds < current_countdown_seconds: # 已完成的事件
                            for col in range(self.table_area.columnCount()):
                                item = self.table_area.item(row, col)
                                if item:
                                    item.setForeground(QBrush(QColor(128, 128, 128, 255))) # 灰色
                        elif row == next_event_row: # 即将发生的事件
                             for col in range(self.table_area.columnCount()):
                                item = self.table_area.item(row, col)
                                if item:
                                    item.setForeground(QBrush(QColor(*config.TABLE_NEXT_FONT_COLOR)))
                                    item.setBackground(QBrush(QColor(*config.TABLE_NEXT_FONT_BG_COLOR)))
                    # 对于 row_count > current_count 的行，保持默认颜色即可

                    # 处理Toast提示
                    event_id = f"special_event_{row}"
                    if row_count == current_count:
                        time_diff = current_countdown_seconds - row_seconds
                        # 在指定时间窗口内显示或更新提示
                        if 0 < time_diff <= config.MAP_ALERT_SECONDS:
                            toast_message = f'余{int(time_diff):0>2}秒  ' + f"  {time_item.text()}\t{event_item.text()}" + (
                                f"\t{army_item.text()}" if army_item and army_item.text() else "")
                            self.toast_manager.show_map_countdown_alert(event_id, time_diff, toast_message, game_screen)
                        else:
                            # 确保过时或远未到来的提示被移除
                            if self.toast_manager.has_alert(event_id):
                                self.toast_manager.remove_alert(event_id)
                    else:
                        # 确保其他阶段的提示被移除
                        if self.toast_manager.has_alert(event_id):
                            self.toast_manager.remove_alert(event_id)

                except (ValueError, IndexError):
                    continue

            # --- 滚动位置逻辑 ---
            scroll_target_row = next_event_row if next_event_row != -1 else last_passed_row_in_count
            if scroll_target_row != -1 and self.table_area.rowHeight(0) > 0:
                visible_rows = self.table_area.height() // self.table_area.rowHeight(0)
                scroll_position = max(0, scroll_target_row - (visible_rows // 2))
                self.table_area.verticalScrollBar().setValue(scroll_position)

        except Exception as e:
            self.logger.error(f'更新净网事件失败: {str(e)}\n{traceback.format_exc()}')
        
        self.logger.debug(f'本次净网事件更新耗时：{time.time() - start_time:.4f}秒')

    def hide_all_alerts(self):
        """隐藏所有与此管理器相关的提示"""
        # 这个方法可以保持不变，或者根据需要让 toast_manager 支持按前缀隐藏
        self.toast_manager.hide_toast()