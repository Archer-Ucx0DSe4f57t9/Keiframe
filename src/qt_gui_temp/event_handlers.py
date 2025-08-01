# qt_gui/event_handlers.py
import os
import traceback
from PyQt5.QtWidgets import QPushButton, QLabel, QGraphicsDropShadowEffect, QTableWidgetItem
from PyQt5.QtGui import QColor, QBrush
from PyQt5.QtCore import Qt, QRect, QPoint
import config
from fileutil import get_resources_dir
from image_util import capture_screen_rect


def on_map_selected(self, map_name):
        """处理地图选择变化事件"""
        # 检查是否是由用户手动选择触发的
        if not self.manual_map_selection and self.sender() == self.combo_box:
            self.manual_map_selection = True
            self.logger.info('用户手动选择了地图')
        
        # 处理地图版本按钮组的显示
        if '-' in map_name:
            prefix = map_name.rsplit('-', 1)[0]
            suffix = map_name.rsplit('-', 1)[1]
            
            # 检查是否存在同前缀的其他地图
            has_variant = False
            variant_type = None
            for i in range(self.combo_box.count()):
                other_map = self.combo_box.itemText(i)
                if other_map != map_name and other_map.startswith(prefix + '-'):
                    has_variant = True
                    other_suffix = other_map.rsplit('-', 1)[1]
                    if other_suffix in ['左', '右'] and suffix in ['左', '右']:
                        variant_type = 'LR'
                    elif other_suffix in ['A', 'B'] and suffix in ['A', 'B']:
                        variant_type = 'AB'
                    break
            
            if has_variant and variant_type:
                # 更新按钮文本
                if variant_type == 'LR':
                    self.version_buttons[0].setText('左')
                    self.version_buttons[1].setText('右')
                else:  # AB
                    self.version_buttons[0].setText('A')
                    self.version_buttons[1].setText('B')
                
                # 设置当前选中的按钮
                current_suffix = suffix
                for btn in self.version_buttons:
                    btn.setChecked(btn.text() == current_suffix)
                
                # 显示按钮组
                self.map_version_group.show()
            else:
                # 隐藏按钮组
                self.map_version_group.hide()
        else:
            # 没有版本区分，隐藏按钮组
            self.map_version_group.hide()
        
        try:
            map_file_path = get_resources_dir('resources', 'maps', config.current_language, map_name)
            self.logger.info(f'尝试加载地图文件: {map_file_path}')
            
            # 读取地图文件内容
            if os.path.exists(map_file_path):
                with open(map_file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.logger.info(f'成功读取地图文件内容: {map_name}\n文件内容:\n{content}')
                
                # 清空表格现有内容
                self.table_area.setRowCount(0)
                self.logger.info('已清空表格现有内容')
                
                # 按行分割内容，过滤掉空行和只包含空白字符的行
                lines = [line.strip() for line in content.split('\n') if line and not line.isspace()]
                self.logger.info('解析到的有效行数: {}'.format(len(lines)))
                self.logger.info('解析后的行内容:\n{}'.format('\n'.join(lines)))
                
                # 设置表格行数
                self.table_area.setRowCount(len(lines))
                self.logger.info(f'设置表格行数为: {len(lines)}')
                
                # 填充表格内容
                for row, line in enumerate(lines):
                    # 按tab分隔符拆分时间和事件
                    parts = line.split('\t')
                    self.logger.info(f'处理第{row+1}行: {line}, 拆分结果: {parts}')
                    
                    if len(parts) >= 2:
                        # 创建时间单元格
                        time_item = QTableWidgetItem(parts[0])
                        time_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                        time_item.setForeground(QBrush(QColor(255, 255, 255)))  # 修改时间列文字颜色为白色
                        self.table_area.setItem(row, 0, time_item)
                        
                        # 创建事件单元格
                        event_item = QTableWidgetItem(parts[1])
                        event_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                        event_item.setForeground(QBrush(QColor(255, 255, 255)))  # 设置事件列文字颜色为白色
                        self.table_area.setItem(row, 1, event_item)
                        
                        if len(parts) == 3:
                            army_item = QTableWidgetItem(parts[2])
                            army_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                            army_item.setForeground(QBrush(QColor(255, 255, 255)))  # 设置事件
                            self.table_area.setItem(row, 2, army_item)
                            self.logger.info(f'已添加表格内容 - 行{row+1}: 时间={parts[0]}, 事件={parts[1]}, {parts[2]}')
                        else:
                            self.logger.info(f'已添加表格内容 - 行{row+1}: 时间={parts[0]}, 事件={parts[1]}')
                    else:
                        # 对于不符合格式的行，将整行内容显示在事件列
                        event_item = QTableWidgetItem(line)
                        event_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                        event_item.setForeground(QBrush(QColor(255, 255, 255)))  # 设置事件列文字颜色为白色
                        
                        self.table_area.setItem(row, 0, event_item)
                        self.table_area.setSpan(row, 0, 1, 3)  # 将当前行的两列合并为一列

                        self.logger.info(f'已添加不规范行内容到合并单元格 - 行{row+1}: {line}')
                
                # 验证表格内容
                row_count = self.table_area.rowCount()
                self.logger.info(f'最终表格行数: {row_count}')
                for row in range(row_count):
                    time_item = self.table_area.item(row, 0)
                    event_item = self.table_area.item(row, 1)
                    time_text = time_item.text() if time_item else 'None'
                    event_text = event_item.text() if event_item else 'None'
                    self.logger.info(f'验证第{row+1}行内容: 时间={time_text}, 事件={event_text}')
                
            else:
                self.logger.error(f'地图文件不存在: {map_name}')
                return
            
        except Exception as e:
            self.logger.error(f'加载地图文件时出错: {str(e)}\n{traceback.format_exc()}')
