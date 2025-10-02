#malwarfare_map_handler.py
import cv2
import numpy as np
import time
import threading
from concurrent.futures import ThreadPoolExecutor
import mss
import sys
import os

# 自带模块
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
BASE_DIR = os.path.dirname(__file__)
from window_utils import get_sc2_window_geometry, is_game_active
from logging_util import get_logger
import config


class MalwarfareMapHandler:
    """
    通过屏幕捕捉、图像处理和模板匹配，实时识别净网的当前已净化的节点数，倒计时，和是否处于暂停状态。
    """
    def __init__(self, game_state = None, debug=False):
        """
        初始化处理器。
        """
        self.logger = get_logger(__name__)
        self.debug = debug
        self._consecutive_failures = 0 #连续获取数据失败一定次数后重定位
        self._shutdown_condition_counter = 0 #在n=4(最后一个锁)时，如果时间小于20秒持续一定时间，结束运行（最后一波在倒计时还剩30秒时发出，10秒已经很足够）
        self._time_recognition_failures = 0 #时间识别的连续失败计数器
        self.game_state = game_state
        
        # 获取当前文件所在目录，用于构建绝对路径
        base_dir = os.path.dirname(__file__)
        self.debug_path = os.path.join(base_dir, 'debugpath')
        if self.debug and not os.path.exists(self.debug_path):
            os.makedirs(self.debug_path)

        self._executor = ThreadPoolExecutor(max_workers=3)
        self._running = False
        self._running_thread = None

        # --- 1. 定义所有可能的HSV颜色范围 ---
        
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

        # --- 2. 动态ROI定位相关定义 ---
        # 定义三种UI状态对应的精确垂直偏移像素

        self.UI_STATE_OFFSETS = [0, config.MALWARFARE_HERO_OFFSET, config.MALWARFARE_ZWEIHAKA_OFFSET] 
        
        # 存储“基准”ROI (状态0: 0偏移时的坐标)
        self._base_count_roi = (
            config.MALWARFARE_PURIFIED_COUNT_TOP_LEFT_COORD[0], config.MALWARFARE_PURIFIED_COUNT_TOP_LEFT_COORD[1],
            config.MALWARFARE_PURIFIED_COUNT_BOTTOMRIGHT_COORD[0], config.MALWARFARE_PURIFIED_COUNT_BOTTOMRIGHT_COORD[1]
        )
        self._base_paused_roi = (
            config.MALWARFARE_PAUSED_TOP_LFET_COORD[0], config.MALWARFARE_PAUSED_TOP_LFET_COORD[1],
            config.MALWARFARE_PAUSED_BOTTOM_RIGHT_COORD[0], config.MALWARFARE_PAUSED_BOTTOM_RIGHT_COORD[1]
        )
        self._base_time_roi = (
            config.MALWARFARE_TIME_TOP_LFET_COORD[0], config.MALWARFARE_TIME_TOP_LFET_COORD[1],
            config.MALWARFARE_TIME_BOTTOM_RIGHT_COORD[0], config.MALWARFARE_TIME_BOTTOM_RIGHT_COORD[1]
        )
        
        # UI状态变量, -1 代表未知，需要探测
        self._current_ui_offset_state = -1 
        
        # 当前生效的ROI，会在探测后被设置
        self._count_roi = None
        self._paused_roi = None
        self._time_roi = None

        # --- 3. 加载模板 ---
        self.BASE_RESOLUTION_WIDTH = 1920.0
        template_dir = 'char_templates_1920w'
        self.templates = self._load_templates(template_dir)
        #人族和rep用
        self.templates_green = self._load_templates('char_templates_1920w')
        #神族和虫族count用
        self.templates_orange = self._load_templates('char_templates_1920w_orange')
        self.templates_blue = self._load_templates('char_templates_1920w_blue')
        
        self.template_sets = {
        'green': self.templates_green,
        'orange': self.templates_orange,
        'blue': self.templates_blue
        }
        self.templates = self.templates_green
        

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

        possible_offsets = self.UI_STATE_OFFSETS.copy()
        for an_offset in self.UI_STATE_OFFSETS:
            an_offset = an_offset + config.MALWARFARE_REPLAY_OFFSET
            possible_offsets.append(an_offset)

        for state_index, y_offset in enumerate(possible_offsets):
            
            # 计算当前探测的ROI坐标
            probe_roi_coords = (
                self._base_count_roi[0], self._base_count_roi[1] + y_offset,
                self._base_count_roi[2], self._base_count_roi[3] + y_offset
            )
            
            x0, y0, x1, y1 = probe_roi_coords
            # 安全检查，确保ROI在图像范围内
            if y1 > img_bgr.shape[0] or x1 > img_bgr.shape[1]: continue
            roi_img = img_bgr[y0:y1, x0:x1]

            if roi_img.size == 0:
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
                self.logger.info(f"UI状态探测成功！当前状态: {state_index} (偏移: {y_offset}px)")
                
                # 锁定状态
                self._current_ui_offset_state = state_index
                
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
    
    def _load_templates(self, template_dir):
        """
        加载并预处理所有字符模板 (已修正 grayscale/alpha channel bug)。
        """
        templates = {}
        base_dir = os.path.dirname(__file__)
        real_template_dir = os.path.join(base_dir, template_dir)
        
        if not os.path.exists(real_template_dir):
            self.logger.warning(f"模板文件夹未找到: {real_template_dir}")
            return {}
            
        for filename in os.listdir(real_template_dir):
            if filename.endswith('.png'):
                char_name = os.path.splitext(filename)[0]
                path = os.path.join(real_template_dir, filename)
                
                # 使用 IMREAD_UNCHANGED 读取图像，以保留可能的Alpha通道
                template_img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
                
                if template_img is None:
                    self.logger.warning(f"加载模板失败: {path}")
                    continue

                # --- 关键修正点 ---
                # 首先检查图像的维度，然后再访问特定维度，避免IndexError
                if len(template_img.shape) == 3 and template_img.shape[2] == 4:
                    # 情况1: 图像是 BGRA (带Alpha通道)
                    # 直接使用Alpha通道作为模板 (白字黑底)
                    template_binary = template_img[:, :, 3]
                else:
                    # 情况2: 图像是 BGR (彩色) 或 Grayscale (灰度)
                    # 如果是彩色的，先转为灰度
                    if len(template_img.shape) == 3:
                        gray_img = cv2.cvtColor(template_img, cv2.COLOR_BGR2GRAY)
                    else:
                        # 如果本身就是灰度图，直接使用
                        gray_img = template_img
                    
                    # 对灰度图执行标准流程：二值化后反色
                    _, template_binary = cv2.threshold(gray_img, 127, 255, cv2.THRESH_BINARY)
                    template_binary = cv2.bitwise_not(template_binary)

                templates[char_name] = template_binary
                
        self.logger.info(f"成功加载 {len(templates)} 个模板。")
        return templates

    def _preprocess_image(self, roi_img, color_type):
        """
        极简版预处理函数：
        1. 使用非常宽容的颜色范围。
        2. 不进行任何形态学操作，只返回最纯粹的颜色提取结果，以保证鲁棒性。
        """
        hsv_img = cv2.cvtColor(roi_img, cv2.COLOR_BGR2HSV)
        
        if color_type == 'yellow':
            mask = cv2.inRange(hsv_img, self.yellow_lower, self.yellow_upper)
        elif color_type == 'green':
            mask = cv2.inRange(hsv_img, self.green_lower, self.green_upper)
        else:
            return None
            
        return mask

    def _recognize_text_from_roi(self, img_bgr, roi, scale_factor, color_type, threshold=0.8, ocr_scale_factor=2.0, debug_name="unknown", templates_to_use=None):
        """
        核心文本识别函数。
        通过模板匹配和非极大值抑制（NMS）来识别ROI中的文本。
        """
        x0, y0, x1, y1 = roi
        roi_img = img_bgr[y0:y1, x0:x1]
        if roi_img.size == 0:
            return ""
        
        # 步骤1: 放大ROI以获得更清晰的字符轮廓
        h, w = roi_img.shape[:2]
        enlarged_roi = cv2.resize(roi_img, (int(w * ocr_scale_factor), int(h * ocr_scale_factor)), interpolation=cv2.INTER_CUBIC)
        
        # 步骤2: 预处理放大后的ROI，提取颜色
        processed_roi = self._preprocess_image(enlarged_roi, color_type)
        if processed_roi is None or processed_roi.size == 0:
            return ""
        
        if self.debug and cv2.countNonZero(processed_roi) > 20:
            img_to_save = cv2.bitwise_not(processed_roi)
            timestamp = int(time.time() * 1000)
            filepath = os.path.join(self.debug_path, f"{timestamp}_{debug_name}.png")
            cv2.imwrite(filepath, img_to_save)

        if cv2.countNonZero(processed_roi) < 20: 
            return ""

        # 步骤3: 收集所有可能的匹配项
        all_detections = []
        template_pool = templates_to_use if templates_to_use is not None else self.templates
        
        for char_name, template in template_pool.items():
            th, tw = template.shape[:2]
            # 模板只根据窗口分辨率（scale_factor）进行缩放
            final_template_scale = scale_factor
            
            if int(tw * final_template_scale) < 1 or int(th * final_template_scale) < 1:
                continue
            
            # 缩放模板（会产生灰色边缘）
            scaled_template = cv2.resize(template, (int(tw * final_template_scale), int(th * final_template_scale)), interpolation=cv2.INTER_CUBIC)
            # 将缩放后的模板重新二值化，确保是纯黑白
            _, scaled_template_binary = cv2.threshold(scaled_template, 127, 255, cv2.THRESH_BINARY)
            
            if scaled_template_binary.shape[0] > processed_roi.shape[0] or scaled_template_binary.shape[1] > processed_roi.shape[1]:
                continue
            
            res = cv2.matchTemplate(processed_roi, scaled_template_binary, cv2.TM_CCOEFF_NORMED)
            
            loc = np.where(res >= threshold)
            scores = res[loc]
            
            h_t, w_t = scaled_template_binary.shape
            for pt, score in zip(zip(*loc[::-1]), scores):
                all_detections.append([(pt[0], pt[1], pt[0] + w_t, pt[1] + h_t), score, char_name])

        if not all_detections:
            return ""

        # 步骤4: 应用非极大值抑制（NMS）去除重叠的检测框
        all_detections.sort(key=lambda x: x[1], reverse=True)
        final_results = []
        while all_detections:
            best_choice = all_detections.pop(0)
            final_results.append(best_choice)
            boxA = best_choice[0]
            
            remaining_detections = []
            for other in all_detections:
                boxB = other[0]
                xA = max(boxA[0], boxB[0])
                yA = max(boxA[1], boxB[1])
                xB = min(boxA[2], boxB[2])
                yB = min(boxA[3], boxB[3])
                interArea = max(0, xB - xA + 1) * max(0, yB - yA + 1)
                boxAArea = (boxA[2] - boxA[0] + 1) * (boxA[3] - boxA[1] + 1)
                boxBArea = (boxB[2] - boxB[0] + 1) * (boxB[3] - boxB[1] + 1)
                iou = interArea / float(boxAArea + boxBArea - interArea)
                
                if iou < 0.3:
                    remaining_detections.append(other)
            all_detections = remaining_detections

        # 步骤5: 按x坐标排序，构建字符串
        final_results.sort(key=lambda x: x[0][0])
        result_text = "".join([char.replace('colon', ':').replace('slash', '/') for _, _, char in final_results])
            
        return result_text

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
            """后台线程的主循环，负责定时截图和调度识别任务。"""
            with mss.mss() as sct:
                while self._running:
                    start_time = time.perf_counter()
                    sc2_rect = get_sc2_window_geometry()
                    
                    if not sc2_rect or not is_game_active() or self.game_state.game_screen !="in_game":
                        # 当游戏窗口关闭时，重置状态以便下次启动时重新探测
                        self._current_ui_offset_state = -1
                        self._detected_count_color = None
                        time.sleep(1)
                        continue
                    
                    x, y, w, h = sc2_rect
                    if w == 0 or h == 0:
                        time.sleep(1)
                        continue
                    
                    current_width = float(w)
                    scale_factor = current_width / self.BASE_RESOLUTION_WIDTH
                    
                    monitor = {"top": y, "left": x, "width": w, "height": h}
                    
                     # 1. 原始 mss.grab() 返回的是一个 MSS.Image 对象
                    sct_img = sct.grab(monitor)
                    
                    # 2. 将其转换为numpy数组时，明确指定数据类型为 uint8。
                    #    这会“净化”数据，使其与 cv2.imread() 读取的数组格式完全一致，解决颜色校准失败的问题。
                    img_array = np.array(sct_img, dtype=np.uint8)
                    
                    # 3. 现在再进行颜色空间转换
                    game_screen_bgr = cv2.cvtColor(img_array, cv2.COLOR_BGRA2BGR)
                    
                    # 如果UI状态未知，则先进行探测 
                    if self._current_ui_offset_state == -1:
                        if not self._detect_and_set_ui_state(game_screen_bgr):
                            # 如果探测失败，则等待下一轮，不进行OCR
                            time.sleep(0.5)
                            continue
                    
                    # 正常调度OCR任务，此时 self._count_roi 等已经是正确的值了
                    current_time = time.perf_counter()
                    
                    if current_time - self._last_count_update >= 1.0:
                        self._executor.submit(self._ocr_and_process_count, game_screen_bgr, scale_factor)
                        self._last_count_update = current_time
                    if current_time - self._last_status_update >= 0.33:
                        self._executor.submit(self._ocr_and_process_time_and_paused, game_screen_bgr, scale_factor)
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

    def _ocr_and_process_count(self, img_bgr, scale_factor):
        """
        自动校准颜色并识别count。
        1. 如果颜色未知，则遍历所有可能的颜色，选择匹配度最高的作为当前局的颜色。
        2. 之后只使用已确定的颜色进行识别。
        3. 在Debug模式下，会将预处理的mask图像保存到debugpath。
        """
        parsed_n = None
        try:
            # --- 步骤1: 颜色校准 (仅在颜色未知时运行) ---
            if self._detected_count_color is None:
                self.logger.info("正在尝试自动校准'Count'区域的颜色...")
                best_score = 0
                best_color = None
                
                x0, y0, x1, y1 = self._count_roi
                roi_img = img_bgr[y0:y1, x0:x1]

                if roi_img.size > 0:
                    h, w = roi_img.shape[:2]
                    ocr_scale_factor = 2.5
                    enlarged_roi = cv2.resize(roi_img, (int(w * ocr_scale_factor), int(h * ocr_scale_factor)), interpolation=cv2.INTER_CUBIC)
                    hsv_img = cv2.cvtColor(enlarged_roi, cv2.COLOR_BGR2HSV)
                    
                    for color_name, (lower, upper) in self.count_color_processors.items():
                        mask = cv2.inRange(hsv_img, lower, upper)
                        
                        kernel = np.ones((3, 3), np.uint8)
                        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
                        
                        if self.debug and cv2.countNonZero(mask) > 20:
                            timestamp = int(time.time() * 1000)
                            filename = f"{timestamp}_count_CALIBRATE_{color_name}.png"
                            filepath = os.path.join(self.debug_path, filename)
                            cv2.imwrite(filepath, cv2.bitwise_not(mask))

                        # ### 修正点 1: 在校准时，为当前测试的颜色选择其对应的模板集 ###
                        current_templates_for_test = self.template_sets.get(color_name, self.templates)
                        phrase_templates_for_test = {name: tmpl for name, tmpl in current_templates_for_test.items() if name.startswith('c')}
                        
                        # 使用与颜色匹配的模板进行匹配测试
                        for name, tmpl in phrase_templates_for_test.items():
                            th, tw = tmpl.shape[:2]
                            final_template_scale = scale_factor
                            if int(tw * final_template_scale) < 1 or int(th * final_template_scale) < 1: continue
                            
                            scaled_template = cv2.resize(tmpl, (int(tw * final_template_scale), int(th * final_template_scale)), interpolation=cv2.INTER_CUBIC)
                            _, scaled_template_binary = cv2.threshold(scaled_template, 127, 255, cv2.THRESH_BINARY)
                            
                            if scaled_template_binary.shape[0] > mask.shape[0] or scaled_template_binary.shape[1] > mask.shape[1]: continue
                            
                            res = cv2.matchTemplate(mask, scaled_template_binary, cv2.TM_CCOEFF_NORMED)
                            _, max_val, _, _ = cv2.minMaxLoc(res)
                            
                            if max_val > best_score:
                                best_score = max_val
                                best_color = color_name
                
                if best_score > 0.75:
                    self._detected_count_color = best_color
                    self.logger.info(f"颜色校准成功！本局游戏'Count'颜色为: {self._detected_count_color.upper()} (分数: {best_score:.2f})")
                else:
                    self.logger.info(f"颜色校准失败 (最高分: {best_score:.2f})，将在下一轮继续尝试。")
                    return

            # --- 步骤2: 使用已确定的颜色进行常规识别 ---
            if self._detected_count_color:
                active_templates = self.template_sets.get(self._detected_count_color, self.templates)
                if not active_templates:
                    self.logger.warning(f"未找到颜色 '{self._detected_count_color}' 的专属模板集，将使用默认模板。")
                    active_templates = self.templates
                    
                color_to_use = self.count_color_processors[self._detected_count_color]
                
                x0, y0, x1, y1 = self._count_roi
                roi_img = img_bgr[y0:y1, x0:x1]
                if roi_img.size > 0:
                    h, w = roi_img.shape[:2]
                    ocr_scale_factor = 2.5
                    enlarged_roi = cv2.resize(roi_img, (int(w * ocr_scale_factor), int(h * ocr_scale_factor)), interpolation=cv2.INTER_CUBIC)
                    hsv_img = cv2.cvtColor(enlarged_roi, cv2.COLOR_BGR2HSV)
                    processed_roi = cv2.inRange(hsv_img, color_to_use[0], color_to_use[1])
                    
                    kernel = np.ones((3, 3), np.uint8)
                    processed_roi = cv2.morphologyEx(processed_roi, cv2.MORPH_CLOSE, kernel, iterations=1)
                    
                    if self.debug and cv2.countNonZero(processed_roi) > 20:
                        timestamp = int(time.time() * 1000)
                        filename = f"{timestamp}_count_RECOGNIZE_{self._detected_count_color}.png"
                        filepath = os.path.join(self.debug_path, filename)
                        cv2.imwrite(filepath, cv2.bitwise_not(processed_roi))
                    
                    # ### 修正点 2: 使用 active_templates 而不是 self.templates ###
                    phrase_templates = {name: tmpl for name, tmpl in active_templates.items() if name.startswith('c')}
                    best_match_score = 0; best_match_name = None
                    for name, tmpl in phrase_templates.items():
                        th, tw = tmpl.shape[:2]
                        scaled_template = cv2.resize(tmpl, (int(tw * scale_factor), int(th * scale_factor)), cv2.INTER_CUBIC)
                        _, scaled_template_binary = cv2.threshold(scaled_template, 127, 255, cv2.THRESH_BINARY)
                        if scaled_template_binary.shape[0] > processed_roi.shape[0] or scaled_template_binary.shape[1] > processed_roi.shape[1]: continue
                        res = cv2.matchTemplate(processed_roi, scaled_template_binary, cv2.TM_CCOEFF_NORMED)
                        _, max_val, _, _ = cv2.minMaxLoc(res)
                        if max_val > best_match_score: best_match_score = max_val; best_match_name = name
                    
                    if best_match_score > 0.8:
                        parsed_n = int(best_match_name[1:])
                        self.logger.debug(f"词组匹配成功: '{best_match_name}'，分数 {best_match_score:.2f}")

            if parsed_n is None and self._detected_count_color:
                self.logger.debug("词组匹配失败或跳过，回退到单字符识别。")

                # ### 修正点 3: 这里同样要使用 active_templates ###
                active_templates = self.template_sets.get(self._detected_count_color, self.templates)
                single_char_templates = {name: tmpl for name, tmpl in active_templates.items() if not name.startswith('c')}

                text = self._recognize_text_from_roi(
                    img_bgr, self._count_roi, scale_factor, self._detected_count_color,
                    threshold=0.75, ocr_scale_factor=2.5,
                    templates_to_use=single_char_templates,
                    debug_name=f"count_fallback_{self._detected_count_color}"
                )
                self.logger.debug(f"单字符识别结果: '{text}'")
                if '/' in text:
                    parts = text.split('/')
                    if parts and parts[0].isdigit():
                        parsed_n = int(parts[0])

            parsed_n = self._post_process_n_value(parsed_n)
            with self._count_lock:
                self._latest_count = parsed_n

        except Exception as e:
            self.logger.error(f"Count区域OCR出错: {e}", exc_info=True)
            
            
    def _ocr_and_process_time_and_paused(self, img_bgr, scale_factor):
        """
        识别时间和暂停状态。
        - 如果识别到3位数时间，则设置 time 并将 paused 状态设为 False。
        - 否则，将 paused 状态设为 True。
        """
        FAILURE_THRESHOLD = 10  # 约等于 5 * 33ms ~= 165ms 的容忍窗口
        
        try:
            # 优先尝试识别时间
            time_text = self._recognize_text_from_roi(img_bgr, self._time_roi, scale_factor, 'yellow', 
                                                      threshold=0.75, ocr_scale_factor=2.0, debug_name="time")
            self.logger.debug(f"Time区域OCR(3位数): '{time_text}'")

            # Case A: 时间识别成功 (游戏运行中)
            if time_text and time_text.isdigit() and len(time_text) == 3:
                with self._time_lock:
                    self._latest_time = time_text
                with self._paused_lock:
                    self._latest_paused = False # 只要有时间，就没有暂停
                return # 成功识别，结束函数

            # Case B：未能识别到有效时间，则判定为暂停状态
            # 这包含了两种情况：a) 明确识别到"PAUSED"文本 b) 时间区域为空
            # 两种情况都意味着游戏计时器没有在走
            #2. 检查是否为“真暂停”
            paused_text = self._recognize_text_from_roi(img_bgr, self._paused_roi, scale_factor, 'yellow', 
                                                          threshold=0.75, ocr_scale_factor=2.0, debug_name="paused")
            self.logger.debug(f"Paused区域OCR: '{paused_text}' (因时间识别失败而检查)")
            
            required_chars = {'P', 'A', 'U', 'S', 'E', 'D'}
            found_chars = set(paused_text.upper())
            
            if len(required_chars.intersection(found_chars)) >= 4:
                # 成功识别到"PAUSED" -> 状态：真暂停
                with self._time_lock:
                    self._latest_time = None
                with self._paused_lock:
                    self._latest_paused = True
                return
            
            # 如果既没识别到时间，也没识别到暂停，则应用“25秒规则”
            # 安全地获取上一次的有效结果
            last_result = self._last_valid_parsed
            if not last_result:
                # 如果连上一次的结果都没有（比如刚启动），则默认为间歇期
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
                last_min, last_sec = map(int, last_time_str.split(':'))
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
                with self._time_lock: self._latest_time = None
                with self._paused_lock: self._latest_paused = False

        except Exception as e:
            self.logger.error(f"Time/Paused区域OCR出错: {e}", exc_info=True)

    
    def _update_latest_result(self):
        """
        1. 组合结果。
        2. 增加状态保持逻辑：当游戏进行中OCR短暂失效时，不更新结果。
        3. 暂停时，'time' 字段保持上一次的有效时间。
        4. 增加延迟补偿：将最终有效时间减去1秒。
        """
        parsed = None
        with self._count_lock, self._paused_lock, self._time_lock:
            latest_count=self._latest_count; 
            latest_paused=self._latest_paused; 
            latest_time=self._latest_time
        
        # 如果没有识别已净化的节点数，则无法构成有效结果，直接处理失败计数并返回
        if latest_count is None:
            if self._current_ui_offset_state != -1:
                self._consecutive_failures += 1
                if self._consecutive_failures > 30: # 阈值可调整
                    self.logger.warning("已连续识别失败超过阈值，可能UI状态已改变。将重置状态...")
                    self._current_ui_offset_state = -1
                    self._detected_count_color = None
                    self._consecutive_failures = 0
                    self._last_valid_parsed = None
            return

         # --- Section 1: 统一处理时间和暂停状态 ---
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
                    
                    # 检查时间是否倒退的逻辑
                    is_valid_update = True
                    if self._last_valid_parsed and self._last_valid_parsed.get('time') and self._last_valid_parsed['time'] not in ["PAUSED", ""]:
                        if latest_count == self._last_valid_parsed.get('n'):
                            try:
                                last_min,last_sec=map(int,self._last_valid_parsed['time'].split(':'))
                                last_total_seconds=last_min*60+last_sec

                                if current_total_seconds - 1  > last_total_seconds: #实际时间快进1秒
                                    is_valid_update = False
                                    self.logger.debug(f"时间未减小，忽略: {current_total_seconds}s > {last_total_seconds}s")
                                    
                            except (ValueError, IndexError, TypeError):
                                pass # 解析上次时间失败，则允许本次更新 
                    
                    if is_valid_update:
                        # --- 关键修改：延迟补偿 ---
                        # 将总秒数减一，并确保不会低于0
                        adjusted_total_seconds = max(0, current_total_seconds - 1)
                        
                        # 从调整后的总秒数重新计算分钟和秒
                        adjusted_min = adjusted_total_seconds // 60
                        adjusted_sec = adjusted_total_seconds % 60
                        
                        # 使用调整后的时间来格式化最终结果
                        final_time_str = f"{adjusted_min}:{str(adjusted_sec).zfill(2)}"
                    else:
                        final_time_str = self._last_valid_parsed.get('time')

            except (ValueError, IndexError) as e:
                self.logger.warning(f"时间字符串格式错误 '{latest_time}': {e}")
        
        # Case 2: 游戏暂停或时间识别失败
        elif latest_paused:
            if self._last_valid_parsed and self._last_valid_parsed.get('time'):
                final_time_str = self._last_valid_parsed.get('time')
        
        # Case 3: 间歇期，final_time_str 保持为 None
        
        #输出结果        
        parsed = {
                    "lang": "en",
                    "n": latest_count,
                    "time": final_time_str,
                    "is_paused": latest_paused
                }

        # --- 自我修复 与 状态更新 --
        if parsed:
            self._consecutive_failures = 0
            if self._last_valid_parsed is None or parsed != self._last_valid_parsed:
                self.logger.info(f"状态更新: {parsed}")
                self._last_valid_parsed = parsed

        
        # --- 处理最后节点时的自动关闭机制 ---
        '''
        if parsed and self._running: # 确保在有有效结果且线程仍在运行时检查
            is_shutdown_condition_met = False
            # 检查 n 是否为 4，以及 time 是否存在且有效
            if parsed.get('n') == 4 and not parsed.get('is_paused') and parsed.get('time'):
                try:
                    minutes, seconds = map(int, parsed['time'].split(':'))
                    total_seconds = minutes * 60 + seconds
                    if total_seconds < 20:
                        is_shutdown_condition_met = True
                except (ValueError, IndexError):
                    pass # 时间格式错误则不满足条件

            if is_shutdown_condition_met:
                # 如果条件满足，计数器加1
                self._shutdown_condition_counter += 1
                self.logger.debug(f"自动关闭条件满足，连续计数: {self._shutdown_condition_counter}/10")
            else:
                # 如果条件中断（比如n不再是4，或者时间超过20秒），则必须重置计数器
                self._shutdown_condition_counter = 0

            # 当计数器达到10次时，执行关闭操作
            if self._shutdown_condition_counter >= 10:
                self.logger.info("检测到 n=4 且 时间<20秒 的状态已连续满足10次,自动退出净网检测")
                self._running = False # 设置标志位，让 _run_loop 线程在下一次循环时优雅地退出
        '''
        with self._result_lock:
            self._latest_result = self._last_valid_parsed


    def get_latest_data(self):
        with self._result_lock:
            # 返回 self._latest_result 的一个浅拷贝，防止外部修改影响内部状态
            return self._latest_result.copy() if self._latest_result else None

    def reset(self):
        """
        将处理器的所有内部状态变量重置为初始值。
        这使得一个实例可以被安全地用于一场新游戏。
        """
        self.logger.info("正在重置 MalwarfareMapHandler 的内部状态...")
        
        # 重新创建线程池，确保它是全新的
        if self._executor._shutdown:
             self._executor = ThreadPoolExecutor(max_workers=3)

        # 重置所有在 __init__ 中设置的状态变量
        self._consecutive_failures = 0
        self._shutdown_condition_counter = 0
        self._time_recognition_failures = 0
        
        self._current_ui_offset_state = -1 # 强制重新探测UI位置
        self._detected_count_color = None  # 强制重新校准颜色
        
        self._latest_count = None
        self._latest_paused = None
        self._latest_time = None
        
        self._last_count_update = 0
        self._last_status_update = 0
        
        self._latest_result = None
        self._last_valid_parsed = None
    
    def shutdown(self):
        self.logger.info("正在请求关闭 MalwarfareMapHandler...")
        self.cleanup()