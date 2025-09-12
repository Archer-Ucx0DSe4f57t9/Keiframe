# map_handlers/malwarfare_map_handler.py
import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
import window_utils
from window_utils import get_sc2_window_geometry
import cv2
import numpy as np
import time
import re
import threading
from concurrent.futures import ThreadPoolExecutor
import config
import easyocr
import mss, mss.tools

# `n`值可以在括号、方括号中，或后面跟一个空格ac
n_pattern = re.compile(r"(\d)[/](\d)")

# 时间格式，只有m:ss格式
time_pattern = re.compile(r"(\d{1,2}:\d{2})")

# 扩展 PAUSED 的正则模式，使其能够匹配更多变体
# P(A|C|.)USE(D|O)
# 包括 P 和 D/O 之间的 U 和 E
pause_pattern_relaxed = re.compile(r"P[A|C|.)?USE[D|O]", re.IGNORECASE)


def parse_text(ocr_text: str):
    """
    通过更健壮的正则表达式和优先匹配顺序来解析 OCR 文本。
    - 优先匹配并返回 PAUSED 状态。
    - 如果没有 PAUSED，则匹配并返回时间状态。
    - 匹配时对每个模式独立进行预处理，而不是对整个文本一次性处理。
    """
    # 将整个 OCR 文本转换为大写，方便后续匹配
    text = ocr_text.strip().upper() 

    # 1. 优先尝试匹配 PAUSED
    # 这个模式专为 PAUSED 设计，可以处理常见的OCR错误
    # 例如：PAUSED, POUSEO, PcUSED
    # 这个模式不依赖括号，因此括号的误识别不会影响它
    paused_match = pause_pattern_relaxed.search(text.replace(' ', '')) # 移除空格以提高匹配率
    
    # 找到 PAUSED 关键字，继续尝试匹配 n/5
    if paused_match:
        n_match = n_pattern.search(text)
        if n_match:
            n_val = int(n_match.group(1))
            return {"lang": "en", "n": n_val, "time": "PAUSED"}
    
    # 2. 如果没有匹配到 PAUSED，再尝试提取时间
    # 对于时间匹配，对文本进行特定的清理，处理括号和数字的混淆
    time_text = text.replace('(', '').replace(')', '').replace('[', '').replace(']', '')
    time_text = time_text.replace('O', '0').replace('I', '1')

    time_match = time_pattern.search(time_text)
    
    # 找到时间，继续尝试匹配 n/5
    if time_match:
        n_match = n_pattern.search(text)
        if n_match:
            n_val = int(n_match.group(1))
            return {"lang": "en", "n": n_val, "time": time_match.group(1)}

    # 如果既没有 PAUSED 也没有时间，则返回 None
    return None

class MalwarfareMapHandler:
    """
    只处理一个特殊地图，通过 OCR + 正则解析文本:
      - 净化5个安全终端({n}/5) (在{m:ss}后净化)
      - 5 Security Terminals({n}/5) (暂停)
      - Purify 5 Security Terminals({n}/5) (Purified in {m:ss})
      - Purify 5 Security Terminals({n}/5) Purified (PAUSED)
    """

    def __init__(self, table_area, toast_manager, logger):
        self.table_area = table_area
        self.toast_manager = toast_manager
        self.logger = logger
        
        self._reader = easyocr.Reader(['en', 'ch_sim'])
        self._executor = ThreadPoolExecutor(max_workers=3)
        self._running = False
        self._running_thread = None

        # 定义三个独立的 OCR 区域 (ROIs)
        self._count_roi = (
            config.MALWARFARE_PURIFIED_COUNT_TOP_LEFT_COORD[0],
            config.MALWARFARE_PURIFIED_COUNT_TOP_LEFT_COORD[1],
            config.MALWARFARE_PURIFIED_COUNT_BOTTOMRIGHT_COORD[0],
            config.MALWARFARE_PURIFIED_COUNT_BOTTOMRIGHT_COORD[1]
        )
        self._paused_roi = (
            config.MALWARFARE_PAUSED_TOP_LFET_COORD[0],
            config.MALWARFARE_PAUSED_TOP_LFET_COORD[1],
            config.MALWARFARE_PAUSED_BOTTOM_RIGHT_COORD[0],
            config.MALWARFARE_PAUSED_BOTTOM_RIGHT_COORD[1]
        )
        self._time_roi = (
            config.MALWARFARE_TIME_TOP_LFET_COORD[0],
            config.MALWARFARE_TIME_TOP_LFET_COORD[1],
            config.MALWARFARE_TIME_BOTTOM_RIGHT_COORD[0],
            config.MALWARFARE_TIME_BOTTOM_RIGHT_COORD[1]
        )
        
        self._latest_result = None
        self._result_lock = threading.Lock()
        
        self._last_valid_parsed = None
        self._last_valid_timestamp = None
        
        self._latest_count = None
        self._latest_paused = None
        self._latest_time = None
        
        self._count_lock = threading.Lock()
        self._paused_lock = threading.Lock()
        self._time_lock = threading.Lock()
        
        self._last_count_update = 0
        self._last_status_update = 0

    def load_map(self, file_path, lines):
        if self.logger:
            self.logger.info(f"MalwarfareMapHandler load_map: {file_path}")

    def start(self):
        if self._running_thread is None or not self._running_thread.is_alive():
            self._running = True
            self._running_thread = threading.Thread(target=self._run_loop, daemon=True)
            self._running_thread.start()
            if self.logger:
                self.logger.info("MalwarwareMapHandler started its internal OCR thread.")
    
    def cleanup(self):
        if self._running:
            self._running = False
            if self._running_thread and self._running_thread.is_alive():
                self._running_thread.join(timeout=1)
                
    def get_latest_parsed_result(self):
        with self._result_lock:
            return self._latest_result

    def _ocr_once(self, img_bgr, roi):
        x0, y0, x1, y1 = roi
        roi_img = img_bgr[y0:y1, x0:x1]
        # 如果分辨率较低，放大 ROI 图像以提高识别率
        if roi_img.shape[0] < 300:
            roi_img = cv2.resize(roi_img, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        results = self._reader.readtext(roi_img, detail=0, paragraph=True)
        return results[0].strip() if results else ""
        
    def _run_loop(self):
        with mss.mss() as sct:
            while self._running:
                start_time = time.perf_counter()
                
                sc2_rect = get_sc2_window_geometry()
                if not sc2_rect:
                    time.sleep(1)
                    continue
                
                x, y, w, h = sc2_rect
                monitor = {"top": y, "left": x, "width": w, "height": h}
                game_screen = np.array(sct.grab(monitor))

                current_time = time.perf_counter()
                
                if current_time - self._last_count_update >= 1.0:
                    self._executor.submit(self._ocr_and_process_count, game_screen)
                    self._last_count_update = current_time
                    
                if current_time - self._last_status_update >= 0.2:
                    self._executor.submit(self._ocr_and_process_paused, game_screen)
                    self._executor.submit(self._ocr_and_process_time, game_screen)
                    self._last_status_update = current_time

                self._update_latest_result()

                elapsed_time = time.perf_counter() - start_time
                sleep_time = 0.1 - elapsed_time
                if sleep_time > 0:
                    time.sleep(sleep_time)

    def _ocr_and_process_count(self, img):
        try:
            ocr_text = self._ocr_once(img, self._count_roi)
            if self.logger: self.logger.debug(f"Count OCR: {repr(ocr_text)}")
            parsed_n = None
            n_match = n_pattern.search(ocr_text)
            if n_match:
                parsed_n = int(n_match.group(1))
                
            parsed_n = self._post_process_n_value(parsed_n)
            
            with self._count_lock:
                self._latest_count = parsed_n
        except Exception as e:
            if self.logger: self.logger.error(f"Count OCR error: {e}")
    
    def _post_process_n_value(self, n_value):
        """
        对 OCR 识别的 n 值进行后处理，修正常见的错误。
        例如，将从 n=2 过渡到 n= 8或者 9 的错误修正为 n=3。
        """
        # 只有当 n 值为 8或者9 且上一个有效值为 2 时才进行修正
        if (n_value == 8 or n_value == 9) and self._last_valid_parsed and self._last_valid_parsed.get('n') == 2:
            if self.logger: self.logger.warning("OCR 识别到 n=9，但根据前一个状态 n=2，修正为 n=3。")
            return 3
        # 否则，返回原始值
        return n_value

    def _ocr_and_process_paused(self, img):
        try:
            ocr_text = self._ocr_once(img, self._paused_roi).upper()
            if self.logger: self.logger.debug(f"PAUSED OCR: {repr(ocr_text)}")
            parsed_paused = None
            if pause_pattern_relaxed.search(ocr_text):
                parsed_paused = "PAUSED"
            with self._paused_lock:
                self._latest_paused = parsed_paused
        except Exception as e:
            if self.logger: self.logger.error(f"PAUSED OCR error: {e}")

    def _ocr_and_process_time(self, img):
        try:

            ocr_text = self._ocr_once(img, self._time_roi).upper()
            if self.logger: self.logger.debug(f"Time OCR: {repr(ocr_text)}")
            parsed_time = None
            time_match = time_pattern.search(ocr_text.replace(' ', '').replace('O', '0').replace('I', '1'))
            if time_match:
                parsed_time = time_match.group(1)
            with self._time_lock:
                self._latest_time = parsed_time
        except Exception as e:
            if self.logger: self.logger.error(f"Time OCR error: {e}")

    def _update_latest_result(self):
        parsed = None
        with self._count_lock, self._paused_lock, self._time_lock:
            latest_count = self._latest_count
            latest_paused = self._latest_paused
            latest_time = self._latest_time
        
         # 1. 优先检查时间。如果能识别到有效时间，就忽略 PAUSED。
        if latest_time and latest_count is not None:
            try:
                min, sec = map(int, latest_time.split(':'))
                if min > 3 or sec >= 60:
                    if self.logger: self.logger.warning(f"时间值超出预期范围，忽略: {latest_time}")
                    parsed = None
                else:
                    parsed = {"lang": "en", "n": latest_count, "time": latest_time}
            except ValueError:
                if self.logger: self.logger.warning(f"时间格式不正确，忽略: {latest_time}")
                parsed = None


        # 2. 如果时间无效（parsed 为 None），再检查 PAUSED。
        if parsed is None and latest_paused == "PAUSED":
            parsed = {"lang": "en", "n": latest_count, "time": "PAUSED"}

        if parsed:
                current_seconds = time.perf_counter()
                if self._last_valid_parsed is None:
                    self._last_valid_parsed = parsed
                    self._last_valid_timestamp = current_seconds
                    if self.toast_manager: self.toast_manager.show_simple_toast(str(parsed))
                elif parsed.get('n') and self._last_valid_parsed.get('n') and \
                    parsed['n'] != self._last_valid_parsed['n']:
                    if self.logger: self.logger.info(f"N value updated to {parsed['n']}.")
                    self._last_valid_parsed = parsed
                    self._last_valid_timestamp = current_seconds
                    if self.toast_manager: self.toast_manager.show_simple_toast(str(parsed))
                elif parsed.get('time') and parsed['time'] != 'PAUSED' and \
                    self._last_valid_parsed.get('time') and self._last_valid_parsed['time'] != 'PAUSED':
                    
                    try:
                        min, sec = map(int, parsed['time'].split(':'))
                        last_min, last_sec = map(int, self._last_valid_parsed['time'].split(':'))
                        parsed_seconds = min * 60 + sec
                        last_parsed_seconds = last_min * 60 + last_sec
                    
                    # 在n值不变的前提下，时间只能减小或不变
                        if parsed['n'] == self._last_valid_parsed['n'] and parsed_seconds > last_parsed_seconds:
                            if self.logger: self.logger.debug(f"时间值没有减小，忽略: {parsed_seconds} > {last_parsed_seconds}")
                            return
                        
                        self._last_valid_parsed = parsed
                        self._last_valid_timestamp = current_seconds
                        if self.toast_manager: self.toast_manager.show_simple_toast(str(parsed))
                        
                    except Exception as e:
                        if self.logger: self.logger.warning(f"时间解析或校验失败: {e}")

        with self._result_lock:
            self._latest_result = self._last_valid_parsed

    def hide_all_alerts(self):
        try:
            if self.toast_manager:
                self.toast_manager.hide_toast()
        except Exception:
            pass