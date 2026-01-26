#game_time_handler
import time
import traceback
from src import config, game_monitor# 导入 TimerWindow 可能需要的其他模块（假设它们在项目中其他位置定义）
# 确保项目结构能够解析这些导入
from src.map_handlers.map_event_manager import MapEventManager
from src.map_handlers.malwarfare_event_manager import MapwarfareEventManager
from src.map_handlers.malwarfare_map_handler import MalwarfareMapHandler


def update_game_time(window):
    """更新游戏时间显示和处理地图/突变事件 (原 TimerWindow.update_game_time)"""
    window.logger.debug('开始更新游戏时间')
    start_time = time.time()

    try:
        # 从全局变量获取游戏时间
        if window.game_state.most_recent_playerdata and isinstance(window.game_state.most_recent_playerdata, dict):
            game_time = window.game_state.most_recent_playerdata.get('time', 0)
            window.logger.debug(f'从全局变量获取的原始时间数据: {game_time}')

            # 格式化时间显示
            hours = int(float(game_time) // 3600)
            minutes = int((float(game_time) % 3600) // 60)
            seconds = int(float(game_time) % 60)

            if hours > 0:
                formatted_time = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            else:
                formatted_time = f"{minutes:02d}:{seconds:02d}"

            window.current_time = formatted_time
            window.time_label.setText(formatted_time)


          # 更新地图信息（如果有）
            map_name = window.game_state.most_recent_playerdata.get('map')
            if map_name:
                window.logger.debug(f'地图信息更新: {map_name}')

            window.logger.debug(f'游戏时间更新: {formatted_time} (格式化后), 原始数据: {game_time}')

            # 根据当前时间调整表格滚动位置和行颜色
            try:
                # 将当前时间转换为总秒数
                current_seconds = hours * 3600 + minutes * 60 + seconds

                # === 突变信息相关 ===
                if hasattr(window, 'mutator_manager'):
                    window.logger.debug(f'正在检查突变: {formatted_time} (格式化后), 原始数据: {game_time}')
                    window.mutator_manager.check_alerts(current_seconds, window.game_state.game_screen)

                # ===地图信息相关===
                if hasattr(window, 'map_event_manager'):
                    window.logger.debug(f'正在检查地图事件: {formatted_time} (格式化后), 原始数据: {game_time}')
                    if window.is_map_Malwarfare:
                        # 净网行动 (Malwarfare) 逻辑
                        if not window.countdown_label.isVisible():
                            window.countdown_label.show()
                        if window.malwarfare_handler:
                            ocr_data = window.malwarfare_handler.get_latest_data()

                            if ocr_data:
                                time_str = ocr_data.get('time')
                                is_paused = ocr_data.get('is_paused')

                                if is_paused:
                                    window.countdown_label.setText("(暂停)")
                                elif time_str:
                                    window.countdown_label.setText(f"({time_str})")
                                else:
                                    window.countdown_label.setText("")
                            else:
                                window.countdown_label.setText("")
                            
                            # 只有在获取到有效数据，且游戏未暂停时，才更新事件
                            if ocr_data and not ocr_data.get('is_paused') and ocr_data.get('time'):
                                current_count = ocr_data.get('n', 1)
                                time_str = ocr_data.get('time')

                                try:
                                    # 将 "M:SS" 格式的时间字符串转换为总秒数
                                    parts = time_str.split(':')
                                    if len(parts) == 2:
                                        minutes = int(parts[0])
                                        seconds = int(parts[1])
                                        countdown_seconds = minutes * 60 + seconds

                                        # 将数据传递给 SpecialLevelEventManager
                                        window.map_event_manager.update_events(
                                            current_count,
                                            countdown_seconds,
                                            window.game_state.game_screen
                                        )
                                    else:
                                        window.logger.warning(f"从OCR接收到无效的时间格式: {time_str}")
                                except (ValueError, TypeError) as e:
                                        window.logger.error(f"解析OCR时间 '{time_str}' 失败: {e}")
                            else:
                                window.logger.debug(f"游戏暂停或无有效OCR数据，跳过地图事件更新。")
                    else:
                        # 标准地图环境逻辑
                        if window.countdown_label.isVisible():
                            window.countdown_label.hide()
                            window.countdown_label.setText("") 
                        window.map_event_manager.update_events(current_seconds, window.game_state.game_screen)

            
                #===突变因子识别器相关===
                if hasattr(window, 'mutator_and_enemy_race_recognizer'):
                    window.logger.debug(f'尝试推送到因子识别器时间{current_seconds}')
                    window.mutator_and_enemy_race_recognizer .update_game_time(current_seconds)
                    
                #===倒计时模块相关===
                if hasattr(window, 'countdown_manager'):
                    # window.game_state.game_screen 是当前的游戏状态 ('in_game', 'loading' 等)
                    window.countdown_manager.update_game_time(
                        current_seconds, 
                        window.game_state.game_screen
                    )

            except Exception as e:
                window.logger.error(f'调整表格滚动位置和颜色失败: {str(e)}\n{traceback.format_exc()}')

        else:
            window.logger.debug('未获取到有效的游戏时间数据')
            window.time_label.setText("00:00")

    except Exception as e:
        window.logger.error(f'获取游戏时间失败: {str(e)}\n{traceback.format_exc()}')
        # 如果获取失败，显示默认时间
        window.time_label.setText("00:00")

    window.logger.debug(f'本次更新总耗时：{time.time() - start_time:.2f}秒\n')