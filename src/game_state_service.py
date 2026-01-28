import time
import json
import aiohttp
import asyncio
import traceback
from PyQt5 import QtCore
from src.map_handlers.IdentifyMap import identify_map
from src import config
from src.debug_utils import get_mock_data, reset_mock, get_mock_screen_data
from src.logging_util import get_logger
from src import show_fence

logger = get_logger(__name__)


class GlobalState:
    """封装所有全局状态的类，确保单例模式"""

    def __init__(self):
        self.app_closing = False
        self.most_recent_playerdata = None
        self.player_winrate_data = []
        self.player_names = []
        self.current_selected_map = None
        self.current_game_id = None
        self.troop = None
        self.is_in_game = None
        self.active_mutators = None
        self.enemy_race = None


# 创建一个唯一的全局状态实例
state = GlobalState()

port_game_status  = "http://localhost:6119/game/"
port_game_screen_for_check_in_game = "http://localhost:6119/ui/"
troop = None


def get_troop_from_game():
    return state.troop


async def process_game_data(session: aiohttp.ClientSession, progress_callback: QtCore.pyqtSignal) -> None:
    logger.info('check_for_new_game函数启动')
    if state.app_closing:
        return

    try:
        if config.debug_mode:
            # 根据调试模式选择数据来源
            game_data = get_mock_data()
            game_screen_for_check_in_game_data = get_mock_screen_data()
        else:
            async with session.get(f'{port_game_status}', timeout=2) as resp:
                resp.raise_for_status()  # 处理非200状态码
                game_data = await resp.json()
            async with session.get(f'{port_game_screen_for_check_in_game}', timeout=2) as resp:
                resp.raise_for_status()  # 处理非200状态码
                game_screen_for_check_in_game_data = await resp.json()

    except aiohttp.ClientError:
        logger.debug('SC2请求失败。游戏未运行。')
        return
    except asyncio.TimeoutError:
        logger.info('请求超时')
        return
    except json.JSONDecodeError:
        logger.info('SC2请求json解码失败')
        return
    except Exception:
        logger.info(traceback.format_exc())
        return

    # 更新游戏数据相关
    if game_data:

        players = game_data.get('players', list())
        # 更新当前游戏时间
        if 'displayTime' in game_data:
            current_time = game_data['displayTime']
            # 更新全局变量中的时间
            if state.most_recent_playerdata is None:
                state.most_recent_playerdata = {'time': current_time}
            else:
                state.most_recent_playerdata['time'] = current_time
            logger.debug(f'更新游戏时间: {current_time}')

        # 生成当前游戏的唯一标识（使用玩家列表的哈希值）
        new_game_id = hash(json.dumps(players, sort_keys=True))

        # 如果游戏ID发生变化，说明是新游戏
        if new_game_id != state.current_game_id:
            state.current_game_id = new_game_id
            logger.info('检测到新游戏，准备更新地图信息')

            # 如果所有玩家都是用户类型，说明是对战模式，跳过
            if all(p['type'] == 'user' for p in players) or len(players) <= 2:
                await asyncio.sleep(0.5)
                return

            # 发送信号，通知主线程重置识别器和地图
            progress_callback.emit(['reset_game_info'])
            # 更新全局变量
            state.most_recent_playerdata = {
                'time': game_data['displayTime'],
                'map': game_data.get('map')
            }
            logger.info(f'更新全局变量: {state.most_recent_playerdata}')

            player_names = list()
            player_position = 1
            for player in players:
                if player['id'] in {1, 2} and player['type'] != 'computer':
                    player_names.append(player['name'])
                    player_position = 2 if player['id'] == 1 else 1
                    break

            formatted_time = time.strftime("%M:%S", time.gmtime(game_data['displayTime']))
            logger.info(f'游戏时间更新: {formatted_time}, 原始数据: {game_data["displayTime"]}')

            # 识别地图
            try:
                logger.info('开始识别地图...')
                logger.info(f'玩家数据: {json.dumps(players, ensure_ascii=False, indent=2)}')
                map_found = identify_map(players)
                if map_found:
                    logger.info(f'地图识别成功: {map_found}')
                    # 发送信号更新下拉列表
                    progress_callback.emit(['update_map', map_found])
                    # 更新全局变量中的地图信息
                    state.most_recent_playerdata['map'] = map_found
                else:
                    logger.error('地图识别失败,- 原因: 无法从API响应中获取地图名称')
            except Exception:
                logger.error(f'地图识别出错: {traceback.format_exc()}')

            # 检测部队
            troop = None

            def troop_detection_callback(result):
                global troop
                if result['success']:
                    logger.info(f"检测到部队: {result['match']}, 相似度: {result['similarity']}")
                    troop = result['match']
                else:
                    logger.info(f"部队检测失败: {result['reason']}")
                    troop = None

            show_fence.detect_troop(troop_detection_callback)

    # 更新地图相关
    active_screens = game_screen_for_check_in_game_data.get('activeScreens', [])
    # 获取activeScreens数组
    # 判断界面状态：数组不为空表示在匹配界面，为空表示在游戏中
    if active_screens:
        state.is_in_game = False
    else:
        state.is_in_game = True


async def check_for_new_game_scheduler(progress_callback: QtCore.pyqtSignal) -> None:
    logger.info('check_for_new_game_scheduler函数启动')

    # 如果是调试模式，重置模拟时间
    if config.debug_mode:
        reset_mock()

    # 在调度器中创建会话，并确保其关闭
    async with aiohttp.ClientSession() as session:
        await asyncio.sleep(4)  # 游戏初始化等待
        logger.info('游戏初始化等待完成')

        while not state.app_closing:
            # 每 0.33秒创建一个非阻塞任务更新游戏状态
            asyncio.create_task(process_game_data(session, progress_callback))
            await asyncio.sleep(0.33)