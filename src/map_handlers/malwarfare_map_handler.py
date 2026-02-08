#malwarfare_map_handler.py
import cv2
import numpy as np
import time
import threading
from concurrent.futures import ThreadPoolExecutor
import os

# 自带模块
from src.utils.logging_util import get_logger
from src.map_handlers.malwarfate_ocr_processor import MalwarfareOcrProcessor
from src import config
from src.game_state_service import state



class MalwarfareMapHandler:
    """
    通过屏幕捕捉、图像处理和模板匹配，实时识别净网的当前已净化的节点数，倒计时，和是否处于暂停状态。
    """
    def __init__(self, game_state = None, debug=False):
        """
        初始化处理器。
        """
        self.logger = get_logger(__name__)
        self.logger.warning("初始化 MalwarfareMapHandler...")
        self.debug = debug
        
        self.game_state = game_state
        # 使用 config 中的当前游戏语言
        self.lang = config.current_game_language
        
        # === 1. 初始化 OCR 处理器 ===
        self.ocr = MalwarfareOcrProcessor(lang=self.lang)
        
        self._consecutive_failures = 0 #连续获取数据失败一定次数后重定位
        self._time_recognition_failures = 0 #时间识别的连续失败计数器
        
        # 获取当前文件所在目录，用于构建绝对路径 (仅用于Debug输出)
        base_dir = os.path.dirname(__file__)
        self.debug_path = os.path.join(base_dir, 'debugpath')
        if self.debug and not os.path.exists(self.debug_path):
            os.makedirs(self.debug_path)

        self._executor = ThreadPoolExecutor(max_workers=3)
        self._running = False
        self._running_thread = None

        # --- 2. 只有 UI 探测 (检测是否存在) 还需要保留简单的 HSV 定义 ---
        # 注意：实际 OCR 识别不再使用这些，而是使用 OCR_CONFIG 中的参数
        
        # 黄色 (对应倒计时和暂停的颜色)
        self.yellow_lower = np.array([20, 80, 80])
        self.yellow_upper = np.array([40, 255, 255])
        
        #用于统计三种已净化的节点的颜色
        # 绿色 (对应人族)
        self.green_lower = np.array([60, 70, 70])
        self.green_upper = np.array([90, 255, 255])
        # 蓝色 (对应神族)
        self.blue_lower = np.array([100, 100, 100])
        self.blue_upper = np.array([125, 255, 255])
        # 橙色 (对应虫族)
        self.orange_lower = np.array([10, 150, 150])
        self.orange_upper = np.array([25, 255, 255])

        # 将所有颜色处理器打包管理，用于颜色校准
        self.count_color_processors = {
            'green': (self.green_lower, self.green_upper),
            'blue': (self.blue_lower, self.blue_upper),
            'orange': (self.orange_lower, self.orange_upper)
        }
        # 用于颜色校准的状态变量
        self._detected_count_color = None 
        self._possible_colors = ['green', 'blue', 'orange']

        # --- 2. 动态ROI定位相关定义 ---
        # 定义三种UI状态对应的精确垂直偏移像素

        self.UI_STATE_OFFSETS = [0, config.MALWARFARE_HERO_OFFSET, config.MALWARFARE_ZWEIHAKA_OFFSET] 
        
        # 存储“基准”ROI (状态0: 0偏移时的坐标)
        self._base_count_roi = config.get_malwarfare_roi(self.lang, 'purified_count')
        self._base_paused_roi = config.get_malwarfare_roi(self.lang, 'paused')
        self._base_time_roi = config.get_malwarfare_roi(self.lang, 'time')
        
        # UI状态变量, -1 代表未知，需要探测
        self._current_ui_offset_state = -1 
        
        # 当前生效的ROI，会在探测后被设置
        self._count_roi = None
        self._paused_roi = None
        self._time_roi = None

        # --- 4. 状态变量初始化 ---
        self._latest_count = None
        self._latest_paused = None
        self._latest_time = None
        
        self._count_lock = threading.Lock()
        self._paused_lock = threading.Lock()
        self._time_lock = threading.Lock()
        
        self._last_count_update = 0
        self._last_status_update = 0
        
        self._latest_result = None
        self._result_lock = threading.Lock()
        self._last_valid_parsed = None
    
    def _detect_and_set_ui_state(self, img_bgr):
        """
        探测UI的当前垂直偏移状态。
        它会检查 `count` 区域的所有可能位置，找到有效信息后，设置全局的ROI。
        """
        self.logger.info("正在探测UI偏移状态...")
        
        # 遍历所有定义好的偏移状态
        for base_index, base_offset in enumerate(self.UI_STATE_OFFSETS):
            for replay_offset in (0, config.MALWARFARE_REPLAY_OFFSET):
                
                y_offset = base_offset + replay_offset

                probe_roi_coords = (
                    self._base_count_roi[0],
                    self._base_count_roi[1] + y_offset,
                    self._base_count_roi[2],
                    self._base_count_roi[3] + y_offset
                )

                self.logger.info(f"尝试探测UI状态: base={base_index}, replay={replay_offset != 0}, ROI={probe_roi_coords}")
                
                x0, y0, x1, y1 = probe_roi_coords
                # 安全检查，确保ROI在图像范围内
                if y1 > img_bgr.shape[0] or x1 > img_bgr.shape[1]: 
                    self.logger.warning(f"跳过越界的ROI检测: base={base_index}, replay={replay_offset != 0}, ROI={probe_roi_coords}")
                    continue
                roi_img = img_bgr[y0:y1, x0:x1]
                
                #cv2.imwrite(f"debug_roi_state_{y0}_{y1}.png", roi_img) # Debug: 输出当前探测的ROI图像，检查是否正确截取
                
                if roi_img.size == 0:
                    self.logger.warning(f"跳过空的ROI检测: base={base_index}, replay={replay_offset != 0}, ROI={probe_roi_coords}")
                    continue

                # 使用所有可能的颜色进行快速、低成本的探测
                hsv_img = cv2.cvtColor(roi_img, cv2.COLOR_BGR2HSV)
                
                # 将所有颜色mask合并，只要有任何一个颜色存在即可
                mask_green = cv2.inRange(hsv_img, self.green_lower, self.green_upper)
                mask_blue = cv2.inRange(hsv_img, self.blue_lower, self.blue_upper)
                mask_orange = cv2.inRange(hsv_img, self.orange_lower, self.orange_upper)
                combined_mask = cv2.bitwise_or(mask_green, mask_blue)
                combined_mask = cv2.bitwise_or(combined_mask, mask_orange)

                # 如果在这个ROI里找到了超过一定数量的有效颜色像素，就认为找到了
                if cv2.countNonZero(combined_mask) > 50: # 阈值可以根据实际情况调整
                    # 锁定状态
                    self._current_ui_offset_state = base_index

                    self.logger.debug(f"UI状态探测成功: base={base_index}, replay={replay_offset != 0}, 总偏移：y_offset = {y_offset}")

                    # 根据探测到的状态，设置所有实际使用的ROI
                    self._count_roi = probe_roi_coords
                    self._paused_roi = (
                        self._base_paused_roi[0], self._base_paused_roi[1] + y_offset,
                        self._base_paused_roi[2], self._base_paused_roi[3] + y_offset
                    )
                    self._time_roi = (
                        self._base_time_roi[0], self._base_time_roi[1] + y_offset,
                        self._base_time_roi[2], self._base_time_roi[3] + y_offset
                    )
                    return True # 探测成功，结束函数
            

            
        self.logger.warning("UI状态探测失败，所有预设位置均未找到有效信息。")

        return False

    def start(self):
        """启动后台识别线程。"""
        if self._running_thread is None or not self._running_thread.is_alive():
            self._running = True
            self._running_thread = threading.Thread(target=self._run_loop, daemon=True)
            self._running_thread.start()
            self.logger.info("MalwarfareMapHandler 已启动后台OCR线程。")
    
    def cleanup(self):
        """停止后台线程并清理资源。"""
        if self._running:
            self._running = False
            if self._running_thread and self._running_thread.is_alive():
                self._running_thread.join(timeout=1)
            #清理线程池
            try:
                self._executor.shutdown(wait=False, cancel_futures=True)
            except TypeError:
                self._executor.shutdown(wait=False)
            self.logger.info("MalwarfareMapHandler 已停止。")

    def _run_loop(self):
        """后台线程的主循环"""
        last_game_screen_time_stamp = 0.0
        while self._running:
            start_time = time.perf_counter()
            
            with state.screenshot_lock:
                game_screen = state.latest_screenshot
                self.logger.warning(f"当前处理图片尺寸: {game_screen.shape if game_screen is not None else 'None'}")
                game_screen_time_stamp = state.screenshot_timestamp
            
            if game_screen is None or game_screen_time_stamp == last_game_screen_time_stamp:
                time.sleep(0.05)
                continue
            
            if self._current_ui_offset_state == -1:
                self.logger.info("正在探测ui状态...")
                if not self._detect_and_set_ui_state(game_screen):
                    time.sleep(0.5)
                    continue
            
            last_game_screen_time_stamp = game_screen_time_stamp
            current_time = time.perf_counter()
            
            # 依据时间间隔决定执行哪些OCR任务
            if current_time - self._last_count_update >= 1.0:
                self._executor.submit(self._ocr_and_process_count, game_screen)
                self._last_count_update = current_time
            if current_time - self._last_status_update >= 0.13:
                self._executor.submit(self._ocr_and_process_time_and_paused, game_screen)
                self._last_status_update = current_time

            self._update_latest_result()

            elapsed_time = time.perf_counter() - start_time
            sleep_time = max(0, 0.1 - elapsed_time)
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _post_process_n_value(self, n_value):
        """对识别出的n值进行后处理，修正已知的特定识别错误。"""
        if n_value is None:
            return None
        if (n_value == 8 or n_value == 9) and self._last_valid_parsed and self._last_valid_parsed.get('n') == 2:
            self.logger.warning("OCR识别到n=8/9，但前一个状态为n=2，修正为n=3。")
            return 3
        return n_value

    def _ocr_and_process_count(self, img_bgr):
        """
        利用 Processor 识别净化节点数。
        如果颜色未知，尝试轮询颜色。
        """
        parsed_n = None
        if not self._count_roi:
            return
        x0, y0, x1, y1 = self._count_roi
        roi_img = img_bgr[y0:y1, x0:x1]

        if roi_img.size == 0: return

        try:
            # --- 步骤1: 颜色校准 (仅在颜色未知时运行) ---
            if self._detected_count_color is None:
                self.logger.info("正在尝试自动校准'Count'区域的颜色...")
                
                for color_name in self._possible_colors:
                    # 尝试用每种颜色的配置去识别
                    result_text = self.ocr.recognize(roi_img, color_name, confidence_thresh=0.75)
                    
                    if result_text:
                        # 检查识别结果是否合法 (例如 "3", "c0")
                        valid = False
                        if result_text.isdigit(): valid = True
                        if result_text.startswith('c') and result_text[1:].isdigit(): valid = True
                        
                        if valid:
                            self._detected_count_color = color_name
                            self.logger.debug(f"颜色校准成功！本局颜色: {color_name.upper()}, 识别结果: {result_text}")
                            break
                
                if self._detected_count_color is None:
                    self.logger.debug("本轮颜色校准未找到匹配，稍后重试。")
                    return

            # --- 步骤2: 使用已确定的颜色进行识别 ---
            if self._detected_count_color:
                result_text = self.ocr.recognize(
                    roi_img, 
                    self._detected_count_color, 
                    confidence_thresh=0.7,
                    debug_show=False
                )
                
                if result_text:
                    # 处理 "c3" 这种格式 (Template 文件夹里的文件名可能是 c0, c1...)
                    if result_text.startswith('c'):
                        result_text = result_text[1:]
                    
                    # 处理可能存在的干扰 (Processor 已经合并了，这里再次清理)
                    clean_text = ''.join(filter(str.isdigit, result_text))
                    
                    self.logger.debug(f"Count区域识别结果原始: '{result_text}'，清理后: '{clean_text}'")
                    
                    if clean_text:
                        parsed_n = int(clean_text)

            parsed_n = self._post_process_n_value(parsed_n)
            
            with self._count_lock:
                self._latest_count = parsed_n

        except Exception as e:
            self.logger.error(f"Count区域OCR出错: {e}", exc_info=True)
            
    def _ocr_and_process_time_and_paused(self, img_bgr):
        """
        识别时间和暂停状态。
        - 如果识别到3位数时间，则设置 time 并将 paused 状态设为 False。
        - 否则，将 paused 状态设为 True。
        """
        if not self._time_roi or not self._paused_roi:
            return
        x_t0, y_t0, x_t1, y_t1 = self._time_roi
        time_roi_img = img_bgr[y_t0:y_t1, x_t0:x_t1]
        
        x_p0, y_p0, x_p1, y_p1 = self._paused_roi
        paused_roi_img = img_bgr[y_p0:y_p1, x_p0:x_p1]

        try:
            # 1. 尝试识别时间
            # Processor 会返回类似 "2:48" 的字符串
            time_text = self.ocr.recognize(time_roi_img, 'yellow', confidence_thresh=0.7)
            self.logger.debug(f"time_text raw: '{time_text}'")
            # Case A: 时间识别成功
            if time_text and len(time_text)==3:
                with self._time_lock:
                    self._latest_time = time_text
                with self._paused_lock:
                    self._latest_paused = False # 只要有时间，就没有暂停
                return

            # Case B: 检查 PAUSED
            paused_text = self.ocr.recognize(paused_roi_img, 'yellow', confidence_thresh=0.7)
            
            is_paused_detected = False
            if paused_text and 'paused' in paused_text.lower():
                is_paused_detected = True
            
            if is_paused_detected:
                with self._time_lock: self._latest_time = None
                with self._paused_lock: self._latest_paused = True
                return
            
            # Case C: 既没时间也没暂停 -> 间歇期或闪烁
            # 25秒规则逻辑保持不变
            last_result = self._last_valid_parsed
            
            if not last_result or not last_result.get('time'):
                # 没有历史数据，默认为间歇期
                with self._time_lock: self._latest_time = None
                with self._paused_lock: self._latest_paused = False
                return

            last_time_str = last_result.get('time')

            # 如果上次没有时间记录，或者n>=5，也视为间歇期
            if not last_time_str:
                with self._time_lock: self._latest_time = None
                with self._paused_lock: self._latest_paused = False
                return

            try:
                # 解析 "Min:Sec"
                if ':' in str(last_time_str):
                    parts = last_time_str.split(':')
                    last_min, last_sec = int(parts[0]), int(parts[1])
                    last_total_seconds = last_min * 60 + last_sec

                # 如果上次时间 > 25秒，则判定为OCR“闪烁”，保持状态不变
                if last_total_seconds > 25:
                    self.logger.debug(f"时间识别失败，但上次时间为 {last_time_str} (>25s)，判定为闪烁，保持状态不变。")
                    # 直接返回，不修改 _latest_time 和 _latest_paused
                    return

                # 如果上次时间 <= 25秒 (且n<5)，则判定为正常的“间歇期”
                else:
                    self.logger.debug(f"时间识别失败，上次时间为 {last_time_str} (<=25s)，判定为间歇期。")
                    with self._time_lock:
                        self._latest_time = None
                    with self._paused_lock:
                        self._latest_paused = False
                    return

            except (ValueError, IndexError, TypeError):
                # 如果解析上次时间出错，安全起见，判定为间歇期
                self.logger.warning(f"解析上次时间'{last_time_str}'失败，默认进入间歇期。")
                
            # 默认 fallback
            with self._time_lock: self._latest_time = None
            with self._paused_lock: self._latest_paused = False

        except Exception as e:
            self.logger.error(f"Time/Paused区域OCR出错: {e}", exc_info=True)

    def _update_latest_result(self):
        """
        组合结果。
        修正：适配新的时间字符串格式 (M:SS)。
        """
        parsed = None
        with self._count_lock, self._paused_lock, self._time_lock:
            latest_count = self._latest_count
            latest_paused = bool(self._latest_paused)
            latest_time = self._latest_time
        
        # 必须有节点数才算有效，则无法构成有效结果，直接处理失败计数并返回
        if latest_count is None:
            if self._current_ui_offset_state != -1:
                self._consecutive_failures += 1
                if self._consecutive_failures > 30:
                    self.logger.warning("已连续识别失败超过阈值，重置UI状态...")
                    self.reset()
            return

        final_time_str = None
        
        # Case 1: 游戏正在运行 (检测到时间且未暂停)
        if latest_paused is False and latest_time is not None:
            try:
                min_val = int(latest_time[0]); 
                sec_val = int(latest_time[1:])
                
                if min_val > 3 or sec_val > 59:
                    self.logger.warning(f"时间值超出范围: M={min_val}, S={sec_val}")
                else:
                    current_total_seconds = min_val * 60 + sec_val
                    
                    # 检查时间倒退 (保持原逻辑)
                    is_valid_update = True
                    if self._last_valid_parsed and self._last_valid_parsed.get('time'):
                        last_t = self._last_valid_parsed['time']
                        if ':' in str(last_t):
                            try:
                                l_min, l_sec = map(int, last_t.split(':'))
                                last_total = l_min * 60 + l_sec
                                # 只有当节点数未变时才检查时间流逝
                                if latest_count == self._last_valid_parsed.get('n'):
                                    if current_total_seconds - 1 > last_total:
                                        is_valid_update = False
                            except: pass # 解析上次时间失败，则允许本次更新 

                    if is_valid_update:
                        final_time_str = f"{min_val}:{str(sec_val).zfill(2)}"
                    else:
                        final_time_str = self._last_valid_parsed.get('time')
                    


            except Exception as e:
                self.logger.warning(f"时间处理错误 '{latest_time}': {e}")
        
        # Case 2: 暂停或无时间
        elif latest_paused:
            if self._last_valid_parsed and self._last_valid_parsed.get('time'):
                final_time_str = self._last_valid_parsed.get('time')
        
        # Case 3: 间歇期，final_time_str 保持为 None
        
        # 输出结果
        parsed = {
            "lang": self.lang,
            "n": latest_count,
            "time": final_time_str,
            "is_paused": latest_paused
        }
        self.logger.debug(f"OCR 解析结果: {parsed}")

        # 更新状态
        if parsed:
            self._consecutive_failures = 0
            if self._last_valid_parsed is None or parsed != self._last_valid_parsed:
                self.logger.info(f"状态更新: {parsed}")
                self._last_valid_parsed = parsed

        with self._result_lock:
            self._latest_result = self._last_valid_parsed

    def get_latest_data(self):
        with self._result_lock:
            # 返回 self._latest_result 的一个浅拷贝，防止外部修改影响内部状态
            return self._latest_result.copy() if self._latest_result else None

    def reset(self):
        """重置状态"""
    
        self.logger.info("重置 MalwarfareMapHandler...")
        try:
            self._executor.shutdown(wait=False)
        except Exception:
            pass
        self._executor = ThreadPoolExecutor(max_workers=3)

        # 重置所有在 __init__ 中设置的状态变量
        self._consecutive_failures = 0
        self._time_recognition_failures = 0
        
        self._current_ui_offset_state = -1 # 强制重新探测UI位置
        self._detected_count_color = None  # 强制重新校准颜色
        
        self._latest_count = None
        self._latest_paused = None
        self._latest_time = None
        self._last_valid_parsed = None
    
    def shutdown(self):
        self.logger.info("请求关闭 MalwarfareMapHandler...")
        self.cleanup()