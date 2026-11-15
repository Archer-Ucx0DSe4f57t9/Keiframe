#game_state_service.py
# 封装全局游戏状态的服务，只记录状态（游戏时间，id,画面截图等），不进行任何处理逻辑
import time
import json
import aiohttp
import asyncio
import traceback
import threading
import mss
import cv2
import numpy as np
from PyQt5 import QtCore
from src.map_handlers.IdentifyMap import identify_map
from src import config
from src.utils.debug_utils import get_mock_data, reset_mock, get_mock_screen_data
from src.utils.logging_util import get_logger
from src.utils.window_utils import get_sc2_window_geometry, is_game_active
#from src import show_fence

logger = get_logger(__name__)
_capture_log_times = {}
_CAPTURE_LOG_INTERVAL_SECONDS = 10.0


def _log_capture_diagnostic(key, level, message, *args):
    now = time.monotonic()
    previous = _capture_log_times.get(key)
    if previous is not None and now - previous < _CAPTURE_LOG_INTERVAL_SECONDS:
        return
    _capture_log_times[key] = now
    getattr(logger, level)(message, *args)


class GlobalState:
    """封装所有全局状态的类，确保单例模式"""

    def __init__(self):
        
        #基础状态信息
        self.game_time = None
        self.current_selected_map = None
        self.current_game_id = None
        self.is_in_game = None
        
        # 游戏相关信息
        self.troop = None
        self.active_mutators = None
        self.enemy_race = None
        self.enemy_composition = None
        
        # 截图相关信息
        self.latest_screenshot = None  # 存储BGR格式的numpy数组
        # 仅在 3840 Runtime 显式启用且客户端区原生为 3840x2160 时保留。
        # 旧识别器继续只消费 latest_screenshot，不受此字段影响。
        self.latest_malwarfare_native_screenshot = None
        self.latest_screenshot_native_shape = None
        self.screenshot_timestamp = 0
        self.scale_factor = 1.0        # 基于1920宽度的缩放比例
        self.screenshot_lock = threading.Lock() # 用于保护截图数据的读写安全
        
        # 消息播报状态
        self.message_presenter_triggered = False
        
        #暂时没用
        self.player_names = []
        self.app_closing = False


# 创建一个唯一的全局状态实例
state = GlobalState()

port_game_status  = "http://127.0.0.1:6119/game/"
port_game_screen_for_check_in_game = "http://127.0.0.1:6119/ui/"
troop = None
BASE_RESOLUTION_WIDTH = 1920.0


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
            # 更新全局变量中的时间,只有当新的时间比当前时间更大时才更新，避免因API偶尔返回较小的时间而导致回退
            if state.game_time is None or current_time > state.game_time:
                state.game_time = current_time
                logger.debug(f'更新游戏时间: {current_time}')

        # 生成当前游戏的唯一标识（使用玩家列表的哈希值）
        new_game_id = hash(json.dumps(players, sort_keys=True))

        # 如果游戏ID发生变化，说明是新游戏
        if new_game_id != state.current_game_id:
            state.current_game_id = new_game_id
            logger.warning(
                "[MapDiag] /game/ 玩家解析成功: count=%d, players=%s",
                len(players),
                [
                    (player.get('id'), player.get('name'), player.get('type'))
                    for player in players
                ],
            )

            # 如果所有玩家都是用户类型，说明是对战模式，跳过
            if all(p['type'] == 'user' for p in players) or len(players) <= 2:
                await asyncio.sleep(0.5)
                return

            # 发送信号，通知主线程重置识别器和地图
            progress_callback.emit(['reset_game_info'])
            # 更新全局变量
            state.game_time = current_time
            logger.info(f'新游戏更新游戏时间: {state.game_time}')

            
            '''
            #暂时不知道有什么用
            player_names = list()
            player_position = 1
            for player in players:
                if player['id'] in {1, 2} and player['type'] != 'computer':
                    player_names.append(player['name'])
                    player_position = 2 if player['id'] == 1 else 1
                    break
            '''

            formatted_time = time.strftime("%M:%S", time.gmtime(game_data['displayTime']))
            logger.info(f'游戏时间更新: {formatted_time}, 原始数据: {game_data["displayTime"]}')

            # 识别地图
            try:
                logger.info('开始识别地图...')
                logger.info(f'玩家数据: {json.dumps(players, ensure_ascii=False, indent=2)}')
                map_found = identify_map(players)
                if map_found:
                    logger.warning(
                        "[MapDiag] identify_map(players)=%r，准备发出 update_map",
                        map_found,
                    )
                    # 发送信号更新下拉列表
                    progress_callback.emit(['update_map', map_found])
                    # 更新全局变量中的地图信息
                    state.current_selected_map = map_found
                else:
                    logger.warning(
                        "[MapDiag] identify_map(players)=None，不会发出 update_map"
                    )
            except Exception:
                logger.error(f'地图识别出错: {traceback.format_exc()}')

            # 检测部队
            troop = None
            '''
            def troop_detection_callback(result):
                global troop
                if result['success']:
                    logger.info(f"检测到部队: {result['match']}, 相似度: {result['similarity']}")
                    troop = result['match']
                else:
                    logger.info(f"部队检测失败: {result['reason']}")
                    troop = None

            show_fence.detect_troop(troop_detection_callback)
            '''
    # 更新地图相关
    # 获取activeScreens数组，如果数组不为空表示在匹配界面，为空表示在游戏中
    active_screens = game_screen_for_check_in_game_data.get('activeScreens', [])
    
    # 判断游戏状态变化
    previous_is_in_game = state.is_in_game
    #如果activeScreens非空，说明在菜单界面，不在游戏中；如果activeScreens为空，说明在游戏中
    new_is_in_game = not bool(active_screens)
    state.is_in_game = new_is_in_game
    if previous_is_in_game is not new_is_in_game:
        logger.warning(
            "[CaptureDiag] is_in_game 变化: %r -> %r, activeScreens=%s",
            previous_is_in_game,
            new_is_in_game,
            active_screens,
        )

    # 从游戏内切换到非游戏内时，如果本局触发过 message_presenter，则重置一次
    if previous_is_in_game is True and new_is_in_game is False:
        if state.message_presenter_triggered:
            logger.info('检测到离开游戏，且本局触发过消息播报，执行 reset_game_info')
            progress_callback.emit(['reset_game_info'])
            state.message_presenter_triggered = False
        
def _capture_game_screen(sct):
    """
    同步函数：执行截屏并更新state。
    由scheduler调用。
    """
    try:
        # 基础检查：游戏是否激活且在进行中
        if not is_game_active(): # 如果你需要只在游戏窗口激活时截图，保留此行；否则可去掉
            _log_capture_diagnostic(
                "inactive",
                "warning",
                "[CaptureDiag] SC2 截图暂停: is_game_active=False, is_in_game=%r",
                state.is_in_game,
            )
            return

        # 获取窗口几何信息
        sc2_rect = get_sc2_window_geometry()
        if not sc2_rect:
            _log_capture_diagnostic(
                "missing_geometry",
                "warning",
                "SC2 截图暂停: get_sc2_window_geometry() 未返回客户端区。",
            )
            return
            
        x, y, w, h = sc2_rect
        if w == 0 or h == 0:
            return

        monitor = {"top": y, "left": x, "width": w, "height": h}
        
        # 1. 截图 (mss.grab 返回 MSS.Image)
        sct_img = sct.grab(monitor)
        
        # 2. 转换为 numpy 数组 (dtype=uint8 确保兼容性)
        img_array = np.array(sct_img, dtype=np.uint8)
        
        # 3. 颜色空间转换 BGRA -> BGR
        game_screen_bgr = cv2.cvtColor(img_array, cv2.COLOR_BGRA2BGR)
        native_frame_shape = tuple(game_screen_bgr.shape)
        
        # 4. 在任何缩放发生前，按显式开关保留 3840 Runtime 所需原生帧。
        # 其他原生尺寸不保留，由旧 1920 标准帧路径继续处理。
        malwarfare_native_bgr = None
        if (
            getattr(config, "enable_malwarfare_3840_runtime", False)
            and game_screen_bgr.shape == (2160, 3840, 3)
        ):
            malwarfare_native_bgr = game_screen_bgr

        # 5. 重缩放图片大小（既有行为）
        target_w = 1920
        target_h = int(h * (1920.0 / w)) # 保持纵横比

        if w != target_w:
            game_screen_bgr = cv2.resize(game_screen_bgr, (target_w, target_h), interpolation=cv2.INTER_AREA)

        current_scale = 1.0
        
        # 6. 计算缩放比例（基于宽度）
        # current_scale = float(w) / BASE_RESOLUTION_WIDTH
        
        # 7. 更新全局状态 (加锁)
        with state.screenshot_lock:
            state.latest_screenshot = game_screen_bgr
            state.latest_malwarfare_native_screenshot = malwarfare_native_bgr
            state.latest_screenshot_native_shape = native_frame_shape
            state.scale_factor = current_scale
            state.screenshot_timestamp = time.perf_counter()
            updated_timestamp = state.screenshot_timestamp
        _log_capture_diagnostic(
            "capture_active",
            "warning",
            "[CaptureDiag] SC2 截图已更新: rect=%s, native=%s %s, canonical=%s %s, "
            "native_3840_preserved=%s, timestamp=%.6f",
            sc2_rect,
            native_frame_shape,
            game_screen_bgr.dtype,
            tuple(game_screen_bgr.shape),
            game_screen_bgr.dtype,
            malwarfare_native_bgr is not None,
            updated_timestamp,
        )
    except Exception as e:
        logger.error(f"截图失败: {e}")


async def screenshot_scheduler() -> None:
    """
    后台截图循环：
    - 每 0.1 秒截一次
    - 结果写入 GlobalState
    """
    logger.info("screenshot_scheduler 启动")

    with mss.mss() as sct:
        while not state.app_closing:
            start = time.perf_counter()

            # 只在“确实在游戏中”时截图
            if state.is_in_game:
                _capture_game_screen(sct)

            elapsed = time.perf_counter() - start
            sleep_time = max(0.0, 0.1 - elapsed)
            await asyncio.sleep(sleep_time)

    logger.info("screenshot_scheduler 退出")


async def check_for_new_game_scheduler(progress_callback: QtCore.pyqtSignal) -> None:
    logger.info('check_for_new_game_scheduler函数启动')

    # 如果是调试模式，重置模拟时间
    if config.debug_mode:
        reset_mock()

    # 在调度器中创建会话，并确保其关闭
    async with aiohttp.ClientSession() as session:
        await asyncio.sleep(4)  # 游戏初始化等待
        logger.info('游戏初始化等待完成')

        asyncio.create_task(screenshot_scheduler())
        
        while not state.app_closing:
            try:
                await asyncio.wait_for(
                    process_game_data(session, progress_callback),
                    timeout=1.0
                )
            except asyncio.TimeoutError:
                logger.debug("process_game_data 单轮更新超时，已跳过")
            await asyncio.sleep(0.125)
