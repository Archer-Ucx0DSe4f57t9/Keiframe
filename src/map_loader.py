import os
import traceback
from PyQt5.QtWidgets import QTableWidgetItem, QPushButton
from PyQt5.QtGui import QBrush, QColor
from PyQt5.QtCore import Qt
from fileutil import get_resources_dir, list_files
from map_handlers.map_event_manager import MapEventManager
from map_handlers.malwarfare_event_manager import MapwarfareEventManager
from map_handlers.malwarfare_map_handler import MalwarfareMapHandler # 确保导入正确
import config

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
        window.table_area.setColumnCount(4)
        window.table_area.setColumnWidth(0, 40)
        window.table_area.setColumnWidth(1, 50)
        window.table_area.setColumnWidth(2, config.MAIN_WINDOW_WIDTH - 95)
        window.table_area.setColumnWidth(3, 5)

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
        window.table_area.setColumnCount(3)
        window.table_area.setColumnWidth(0, 50)
        window.table_area.setColumnWidth(1, config.MAIN_WINDOW_WIDTH - 55)
        window.table_area.setColumnWidth(2, 5)

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
        map_file_path = get_resources_dir('resources', 'maps', config.current_language, map_name)
        window.logger.info(f'尝试加载地图文件: {map_file_path}')

        if os.path.exists(map_file_path):
            with open(map_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            window.logger.info(f'成功读取地图文件内容: {map_name}')

            # 清空表格现有内容
            window.table_area.setRowCount(0)
            window.logger.info('已清空表格现有内容')
            
            # 按行分割内容，过滤掉空行和只包含空白字符的行
            lines = [line.strip() for line in content.split('\n') if line and not line.isspace()]
            window.logger.info('解析到的有效行数: {}'.format(len(lines)))
            window.logger.info('解析后的行内容:\n{}'.format('\n'.join(lines)))
            
            # 设置表格行数
            window.table_area.setRowCount(len(lines))
            window.logger.info(f'设置表格行数为: {len(lines)}')
            
            # 填充表格内容
            for row, line in enumerate(lines):
                
                # 按tab分隔符拆分时间和事件
                parts = line.split('\t')
                
                if window.is_map_Malwarfare:
                    # 净网行动处理逻辑 (4列)
                    if len(parts) >= 4:
                        count_item = QTableWidgetItem(parts[0])
                        time_item = QTableWidgetItem(parts[1])
                        event_item = QTableWidgetItem(parts[2])
                        army_item = QTableWidgetItem(parts[3])

                        # 设置颜色和对齐
                        for item in [count_item, time_item, event_item, army_item]:
                            item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                            item.setForeground(QBrush(QColor(255, 255, 255)))

                        window.table_area.setItem(row, 0, count_item)
                        window.table_area.setItem(row, 1, time_item)
                        window.table_area.setItem(row, 2, event_item)
                        window.table_area.setItem(row, 3, army_item)
                        window.logger.info(f'已添加净网表格内容 - 行{row+1}: Count={parts[0]}, Time={parts[1]}, Event={parts[2]}, Army={parts[3]}')
                    else:
                        window.logger.warning(f"行 {row+1} 格式不符合净网地图要求 (需要4列): {line}")
                else:
                     # 标准地图处理逻辑 (2或3列)
                    if len(parts) >= 2:
                      # 创建时间单元格
                        time_item = QTableWidgetItem(parts[0])
                        time_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                        time_item.setForeground(QBrush(QColor(255, 255, 255)))
                        window.table_area.setItem(row, 0, time_item)
                      # 创建事件单元格
                        event_item = QTableWidgetItem(parts[1])
                        event_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                        event_item.setForeground(QBrush(QColor(255, 255, 255)))
                        window.table_area.setItem(row, 1, event_item)

                        if len(parts) >= 3: # 检查是否有第三列数据（兵种/备注）
                            army_item = QTableWidgetItem(parts[2])
                            army_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                            army_item.setForeground(QBrush(QColor(255, 255, 255))) # 设置事件
                            window.table_area.setItem(row, 2, army_item)
                            window.logger.info(
                                    f'已添加表格内容 - 行{row + 1}: 时间={parts[0]}, 事件={parts[1]}, {parts[2]}')
                        elif len(parts) == 2 and window.table_area.columnCount() == 3:
                            # 确保第三列是空的，如果表格是3列的
                            window.table_area.setItem(row, 2, QTableWidgetItem(""))

                    else:
                      # 对于不符合格式的行，将整行内容显示在事件列
                        event_item = QTableWidgetItem(line)
                        event_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                        event_item.setForeground(QBrush(QColor(255, 255, 255)))

                        window.table_area.setItem(row, 0, event_item)
                        # 合并单元格
                        window.table_area.setSpan(row, 0, 1, window.table_area.columnCount())

                        window.logger.info(f'已添加不规范行内容到合并单元格 - 行{row + 1}: {line}')
            #验证表格内容
            row_count = window.table_area.rowCount()
            window.logger.info(f'最终表格行数: {row_count}')
            for row in range(row_count):
                time_item = window.table_area.item(row, 0)
                event_item = window.table_area.item(row, 1)
                time_text = time_item.text() if time_item else 'None'
                event_text = event_item.text() if event_item else 'None'
                window.logger.info(f'验证第{row + 1}行内容: 时间={time_text}, 事件={event_text}')
        else:
            window.logger.error(f'地图文件不存在: {map_name}')
            return

    except Exception as e:
        window.logger.error(f'加载地图文件时出错: {str(e)}\n{traceback.format_exc()}')