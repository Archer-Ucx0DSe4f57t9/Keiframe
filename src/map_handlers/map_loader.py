import os
import traceback
from PyQt5.QtWidgets import QTableWidgetItem, QPushButton
from PyQt5.QtGui import QBrush, QColor
from PyQt5.QtCore import Qt
from src.utils.fileutil import get_resources_dir
from src.map_handlers.map_event_manager import MapEventManager
from src.map_handlers.malwarfare_event_manager import MapwarfareEventManager
from src.map_handlers.malwarfare_map_handler import MalwarfareMapHandler
from src.db.daos import load_map_by_name
from src import config, game_state_service

def handle_version_selection(window):
    """处理地图版本按钮选择事件 (原 TimerWindow.on_version_selected)"""
    sender = window.sender()
    if not sender or not isinstance(sender, QPushButton):
        return

    # 取消其他按钮的选中状态
    for btn in window.version_buttons:
        if btn != sender:
            btn.setChecked(False)

    # 获取当前地图名称的前缀
    current_map = window.combo_box.currentText()
    if not current_map:
        return

    # 根据按钮文本和地图前缀构造新的地图名称
    prefix = current_map.rsplit('-', 1)[0]
    new_map = f"{prefix}-{sender.text()}"

    # 在下拉框中查找并选择新地图
    index = window.combo_box.findText(new_map)
    if index >= 0:
        window.combo_box.setCurrentIndex(index)

def handle_map_selection(window, map_name):
    """处理地图选择变化事件 (原 TimerWindow.on_map_selected)"""
    # 检查是否是由用户手动选择触发的
    if hasattr(window, 'toast_manager') and window.toast_manager:
        window.toast_manager.clear_all_alerts()
    if not window.manual_map_selection and window.sender() == window.combo_box:
        window.manual_map_selection = True
        window.logger.info('用户手动选择了地图')
        
    game_state_service.state.current_selected_map = map_name
    
    # 在地嗪图识别到神族时，自动切换到神族模式
    if map_name == '机会渺茫-人虫' and window.game_state.enemy_race == 'Protoss':
        new_map = '机会渺茫-神'
        window.logger.info(f"检测到 '机会渺茫-人虫' 且种族为 Protoss，尝试切换到: {new_map}")
        
        index = window.combo_box.findText(new_map)
        if index >= 0:
            # 如果目标地图已经是新地图，则跳过 set，避免无限循环
            if window.combo_box.currentText() != new_map:
                window.combo_box.setCurrentIndex(index)
                # 重要：在 setCurrentIndex 后，信号会再次触发 handle_map_selection
                return 
            else:
                window.logger.info("目标地图已是 '机会渺茫-神'，继续加载。")
        else:
            window.logger.warning(f"未在下拉框中找到地图: {new_map}，继续加载原地图。")   
         
        
    # 根据地图名称实例化正确的事件管理器
    if map_name == '净网行动':
        window.logger.warning("检测到特殊地图 '净网行动'，正在启用 MalwarfareEventManager。")
        window.map_event_manager = MapwarfareEventManager(window.table_area, window.toast_manager, window.logger)
        window.is_map_Malwarfare = True
        
        if window.malwarfare_handler is None:
            window.logger.info("创建并启动 MalwarfareMapHandler 实例。")
            window.malwarfare_handler = MalwarfareMapHandler(game_state = window.game_state)
            window.malwarfare_handler.reset()
            window.malwarfare_handler.start()
        
        window.countdown_label.show()
        window.table_area.setColumnCount(5)
        window.table_area.setColumnWidth(0, 40) # Count
        window.table_area.setColumnWidth(1, 50) # Time
        window.table_area.setColumnWidth(2, config.MAIN_WINDOW_WIDTH - config.MUTATOR_WIDTH - 95) # Event (宽列)
        window.table_area.setColumnWidth(3, 5) # 新增 Sound 列（隐藏）
        window.table_area.setColumnWidth(4, 5) # Hero 列（隐藏/留空）

    else:
        window.logger.info(f"使用标准地图 '{map_name}'，正在启用 MapEventManager。")
        window.map_event_manager = MapEventManager(window.table_area, window.toast_manager, window.logger)
        window.is_map_Malwarfare = False
        
        if window.malwarfare_handler is not None:
            window.logger.info("切换到其他地图，正在关闭 MalwarfareMapHandler。")
            window.malwarfare_handler.shutdown()
            window.malwarfare_handler = None
        
        window.countdown_label.hide()
        window.countdown_label.setText("")
        window.table_area.setColumnCount(5) 
        window.table_area.setColumnWidth(0, 50)          # Time
        window.table_area.setColumnWidth(1, config.MAIN_WINDOW_WIDTH -config.MUTATOR_WIDTH - 90) # Event
        window.table_area.setColumnWidth(2, 30)          # Army/Note
        window.table_area.setColumnWidth(3, 5)           # Sound File (隐藏)
        window.table_area.setColumnWidth(4, 5)           # Hero Event (隐藏)

    # 处理地图版本按钮组的显示 (原有的版本检测逻辑)
    if '-' in map_name:
        prefix = map_name.rsplit('-', 1)[0]
        suffix = map_name.rsplit('-', 1)[1]

        has_variant = False
        variant_type = None
        for i in range(window.combo_box.count()):
            other_map = window.combo_box.itemText(i)
            if other_map != map_name and other_map.startswith(prefix + '-'):
                has_variant = True
                other_suffix = other_map.rsplit('-', 1)[1]
                if other_suffix in ['左', '右'] and suffix in ['左', '右']:
                    variant_type = 'LR'
                elif other_suffix in ['A', 'B'] and suffix in ['A', 'B']:
                    variant_type = 'AB'
                elif other_suffix in ['神', '人虫'] and suffix in ['神', '人虫']:
                    variant_type = 'PZT'
                break

        if has_variant and variant_type:
            # 更新按钮文本
            if variant_type == 'LR':
                window.version_buttons[0].setText('左')
                window.version_buttons[1].setText('右')
            elif variant_type == 'AB':
                window.version_buttons[0].setText('A')
                window.version_buttons[1].setText('B')
            else:
                window.version_buttons[0].setText('神')
                window.version_buttons[1].setText('人虫')

            # 设置当前选中的按钮
            current_suffix = suffix
            for btn in window.version_buttons:
                btn.setChecked(btn.text() == current_suffix)

            window.map_version_group.show()
        else:
            window.map_version_group.hide()
    else:
        window.map_version_group.hide()
        
    # 加载地图文件内容并填充表格 (原有的文件加载和表格填充逻辑)
    try:
        
        map_data = load_map_by_name(window.maps_db, map_name)
        if map_data:
            window.logger.info(f'成功从数据库读取地图数据: {map_name}，记录数: {len(map_data)}')
            # 清空表格现有内容
            window.table_area.setRowCount(0)
            window.logger.info('已清空表格现有内容')
            
            # 设置表格行数
            window.table_area.setRowCount(len(map_data))
            window.logger.info(f'设置表格行数为: {len(map_data)}')
            
            # 填充表格内容
            for row, map_row in enumerate(map_data):
                if window.is_map_Malwarfare:
                    # 净网行动处理逻辑 (4列)
                    
                    count_text = str(map_row['count_value'])
                    time_text = str(map_row['time_label'])
                    event_text = map_row['event_text']
                    army_text = map_row['army_text']
                    sound_text = map_row['sound_filename']  # Sound 现在是第 5 列
                    hero_text = map_row['hero_text'] # 净网行动英雄列留空

                    # 0. Count
                    count_item = QTableWidgetItem(count_text)
                    count_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                    count_item.setForeground(QBrush(QColor(255, 255, 255)))
                    window.table_area.setItem(row, 0, count_item)
                    
                    # 1. Time
                    time_item = QTableWidgetItem(time_text)
                    time_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                    time_item.setForeground(QBrush(QColor(255, 255, 255)))
                    window.table_area.setItem(row, 1, time_item)
                    
                    # 2. Event
                    event_item = QTableWidgetItem(event_text)
                    event_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                    event_item.setForeground(QBrush(QColor(255, 255, 255)))
                    window.table_area.setItem(row, 2, event_item) 
                    
                    # 3. Sound (隐藏列)
                    sound_item = QTableWidgetItem(sound_text)
                    sound_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                    sound_item.setForeground(QBrush(QColor(255, 255, 255)))
                    window.table_area.setItem(row, 3, sound_item)
                    
                    # 4. Hero (隐藏列，风暴英雄)
                    hero_item = QTableWidgetItem(hero_text)
                    hero_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                    hero_item.setForeground(QBrush(QColor(255, 255, 255)))
                    window.table_area.setItem(row, 4, hero_item)
                else:
                        # 标准地图处理逻辑 (2或3列)
                        
                        time_text = str(map_row['time_label'])
                        event_text = map_row['event_text']
                        army_text = map_row['army_text']
                        sound_text = map_row['sound_filename']
                        hero_text = map_row['hero_text']
                        
                        # 1. 时间单元格 (列 0)
                        time_item = QTableWidgetItem(time_text)
                        time_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                        time_item.setForeground(QBrush(QColor(255, 255, 255)))
                        window.table_area.setItem(row, 0, time_item)
                        
                        # 2. 事件单元格 (列 1)
                        event_item = QTableWidgetItem(event_text)
                        event_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                        event_item.setForeground(QBrush(QColor(255, 255, 255)))
                        window.table_area.setItem(row, 1, event_item)
    
                        # 3. 兵种/备注单元格 (列 2)
                        army_item = QTableWidgetItem(army_text)
                        army_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                        army_item.setForeground(QBrush(QColor(255, 255, 255)))
                        window.table_area.setItem(row, 2, army_item)
                        
                        # 4. 音频文件单元格 (列 3)
                        sound_item = QTableWidgetItem(sound_text)
                        sound_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                        sound_item.setForeground(QBrush(QColor(255, 255, 255)))
                        window.table_area.setItem(row, 3, sound_item)
                        
                        # 5. 英雄事件单元格 (列 4)
                        hero_item = QTableWidgetItem(hero_text)
                        hero_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                        hero_item.setForeground(QBrush(QColor(255, 255, 255)))
                        window.table_area.setItem(row, 4, hero_item)
    except Exception as e:
        window.logger.error(f'加载地图数据时出错: {str(e)}\n{traceback.format_exc()}')