# mutator_and_enemy_race_automatic_recognizer.py

import cv2
import numpy as np
import time
import threading
import mss
import os

import sys
import os
from logging_util import get_logger
from window_utils import get_sc2_window_geometry, is_game_active

class Mutator_and_enemy_race_automatic_recognizer:
    """
    通过屏幕捕捉和模板匹配，识别游戏中的种族和突变因子图标。

    它会监控一个固定的屏幕区域，并将其与 'icons/races' 和 'icons/mutators'
    文件夹中的模板图片进行比对。当一个图标连续匹配10次后，会被确认为最终结果。
    """

    #基础分辨率
    BASE_RESOLUTION_WIDTH = 1920.0
    # 模板匹配的置信度阈值
    CONFIDENCE_THRESHOLD = 0.8
    # 确认结果所需的连续匹配次数
    CONSECUTIVE_MATCH_REQUIREMENT = 10
    #如果种族已确认，但在此秒数后仍未发现突变因子，则确认突变因子为空
    MUTATOR_TIMEOUT_AFTER_RACE = 10.0

    def __init__(self,recognition_signal = None):
        self.logger = get_logger(__name__)
        self.recognition_signal = recognition_signal
        
        self._base_roi = (1850, 190, 1920, 800)
        self._running = False
        self._thread = None
        self._current_game_time = 0.0
        self.base_dir = os.path.dirname(__file__)

        # 加载模板

        self.race_templates = self._load_templates(os.path.join(self.base_dir, '..', 'resources', 'icons', 'races'))
        self.mutator_templates = self._load_templates(os.path.join(self.base_dir, '..', 'resources', 'icons', 'mutators'))

        # 初始化状态和结果存储
        self._reset_state()

        #测试用代码
        x1, y1, x2, y2 = self._base_roi
        self.RECOGNITION_ROI = {
            'left': x1,
            'top': y1,
            'width': x2 - x1,
            'height': y2 - y1
        }

    def _load_templates(self, directory_path):
        """从指定目录加载所有 .png 模板图片。"""
        templates = {}
        if not os.path.isdir(directory_path):
            self.logger.error(f"模板目录不存在: {directory_path}")
            return templates

        self.logger.info(f"正在从 {directory_path} 加载模板...")
        for filename in os.listdir(directory_path):
            if filename.lower().endswith('.png'):
                try:
                    # 去掉 .png 后缀作为 key
                    template_name = os.path.splitext(filename)[0]
                    path = os.path.join(directory_path, filename)
                    # 以灰度模式读取模板
                    template_img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
                    if template_img is not None:
                        templates[template_name] = template_img
                        self.logger.info(f" -> 已加载模板: {filename}")
                    else:
                        self.logger.warning(f"无法加载图片: {path}")
                except Exception as e:
                    self.logger.error(f"加载模板 {filename} 时出错: {e}")
        return templates

    def _reset_state(self):
        """重置所有识别状态和结果，用于开始新一轮的识别。"""
        self.logger.info("正在重置 GameInfoRecognizer 状态...")

        # 最终识别结果
        self.recognized_race = None
        self.recognized_mutators = []
        self._current_game_time = 0.0

        # 用于跟踪连续匹配次数的计数器
        self.race_candidates = {name: 0 for name in self.race_templates.keys()}
        self.mutator_candidates = {name: 0 for name in self.mutator_templates.keys()}

        # 记录上一轮的最佳匹配项，用于判断是否“连续”
        self._last_best_race_match = None

        # 控制是否继续扫描特定内容
        self.race_detection_complete = False
        self.mutator_detection_complete = False

        # 初始化独立的计时器和扫描间隔
        self._last_race_scan_time = 0
        self._last_mutator_scan_time = 0
        self._race_scan_interval = 5.0      # 初始为5秒“搜索模式”
        self._mutator_scan_interval = 5.0   # 初始为5秒“搜索模式”
        
        self._race_confirmed_time = None

    def start(self):
        """启动后台识别线程。"""
        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
            self.logger.info("GameInfoRecognizer 后台识别线程已启动。")
        else:
            self.logger.warning("GameInfoRecognizer 已经在运行中。")

    def shutdown(self):
        """停止后台识别线程。"""
        self.logger.info("正在停止 GameInfoRecognizer...")
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self.logger.info("GameInfoRecognizer 已停止。")

    def reset_and_start(self):
        """重置状态并重启识别流程。这是开始新游戏时应调用的方法。"""
        self.shutdown()
        # 等待线程完全停止
        time.sleep(0.1) 
        self._reset_state()
        self.start()

    def get_results(self):
        """获取当前已确认的识别结果。"""
        return {
            "race": self.recognized_race,
            "mutators": self.recognized_mutators
        }
    
    def update_game_time(self,game_time_seconds):
        self.logger.info(f"已经接收到游戏时间{game_time_seconds}")
        self._current_game_time = game_time_seconds

    def _scan_for_races(self, screenshot_gray, scale_factor):
        """在截图中扫描并更新种族识别状态。"""
        if not self.race_templates: return

        best_match_name = None
        max_score = self.CONFIDENCE_THRESHOLD - 0.01

        for name, template in self.race_templates.items():
            th, tw = template.shape[:2]
            scaled_w, scaled_h = int(tw * scale_factor), int(th * scale_factor)
            if scaled_w < 1 or scaled_h < 1: continue
            scaled_template = cv2.resize(template, (scaled_w, scaled_h), interpolation=cv2.INTER_AREA)
            if scaled_h > screenshot_gray.shape[0] or scaled_w > screenshot_gray.shape[1]: continue
            res = cv2.matchTemplate(screenshot_gray, scaled_template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(res)
            if max_val > max_score:
                max_score = max_val
                best_match_name = name

        # 如果找到了任何潜在匹配
        if best_match_name:
            # [状态切换] 立即进入0.5秒/次的“确认模式”
            self._race_scan_interval = 0.5

            # 如果最佳匹配发生变化（异常情况），清空所有计数，但保持1秒模式
            if self._last_best_race_match != best_match_name:
                self.logger.info(f"种族识别目标改变: {self._last_best_race_match} -> {best_match_name}。重置计数。")
                self.race_candidates = {n: 0 for n in self.race_templates.keys()}

            self.race_candidates[best_match_name] += 1
            self._last_best_race_match = best_match_name
            self.logger.debug(f"种族潜在匹配: {best_match_name} (分数: {max_score:.2f}, 连续次数: {self.race_candidates[best_match_name]})")

            if self.race_candidates[best_match_name] >= self.CONSECUTIVE_MATCH_REQUIREMENT:
                self.recognized_race = best_match_name
                self.race_detection_complete = True
                self.logger.info(f"** 种族已确认: {self.recognized_race} **")

                if self.recognition_signal:
                    self.recognition_signal.emit({'race': self.recognized_race, 'mutators': None})


        else:
            # 如果完全没找到匹配，且之前有潜在目标，则清空计数
            if self._last_best_race_match is not None:
                 self.logger.info(f"种族识别目标 '{self._last_best_race_match}' 丢失。重置计数。")
                 self.race_candidates = {n: 0 for n in self.race_templates.keys()}
                 self._last_best_race_match = None
            # 注意：此处不改回5秒，一旦进入确认模式，除非重置，否则不退出

    def _scan_for_mutators(self, screenshot_gray, scale_factor):
        """在截图中扫描并更新突变因子识别状态。"""
        if not self.mutator_templates: return

        a_potential_match_found = False
        for name, template in self.mutator_templates.items():
            if name in self.recognized_mutators: continue

            th, tw = template.shape[:2]
            scaled_w, scaled_h = int(tw * scale_factor), int(th * scale_factor)
            if scaled_w < 1 or scaled_h < 1: continue
            scaled_template = cv2.resize(template, (scaled_w, scaled_h), interpolation=cv2.INTER_AREA)
            if scaled_h > screenshot_gray.shape[0] or scaled_w > screenshot_gray.shape[1]: continue

            res = cv2.matchTemplate(screenshot_gray, scaled_template, cv2.TM_CCOEFF_NORMED)
            loc = np.where(res >= self.CONFIDENCE_THRESHOLD)

            if len(loc[0]) > 0:
                a_potential_match_found = True
                self.mutator_candidates[name] += 1
                self.logger.debug(f"突变因子潜在匹配: {name} (连续次数: {self.mutator_candidates[name]})")
            else:
                # 如果之前正在计数（异常情况），则清零
                if self.mutator_candidates[name] > 0:
                    self.logger.info(f"突变因子识别目标 '{name}' 丢失。重置其计数。")
                    self.mutator_candidates[name] = 0

            if self.mutator_candidates[name] >= self.CONSECUTIVE_MATCH_REQUIREMENT:
                if name not in self.recognized_mutators:
                    self.recognized_mutators.append(name)
                    self.logger.info(f"** 突变因子已确认: {name} **")

                if self.recognition_signal:
                        # 每次确认新的突变因子时，都发送完整的列表
                        self.recognition_signal.emit({'race': None, 'mutators': self.recognized_mutators})

        # [状态切换] 只要发现任何一个潜在突变因子，就进入1秒/次的“确认模式”
        if a_potential_match_found:
            self._mutator_scan_interval = 0.5

        if len(self.recognized_mutators) > 0:
            self.mutator_detection_complete = True


    def _run_loop(self):
        """后台线程的主循环，使用独立计时器分别调度种族和突变因子的识别任务。"""
        with mss.mss() as sct:
            while self._running:
                # 检查所有任务是否都已完成
                if self.race_detection_complete and self.mutator_detection_complete:
                    self.logger.info("所有识别任务已完成，进入等待状态。")
                    self._running = False # 设置标志位以表明我们想停止
                    continue

                # 条件：已超过 30 秒 AND 突变因子检测未完成
                if self._current_game_time >= 30 and not self.mutator_detection_complete:
                    self.logger.warning("游戏时间已超过 30 秒，且突变因子未确认，将结果确认为空。")
                    self.recognized_mutators = [] # 确认结果为空列表
                    self.mutator_detection_complete = True
                    self.recognition_signal.emit({'race': None, 'mutators': self.recognized_mutators})
                    continue
                '''
                //弃用原来逻辑
                if self.race_detection_complete and not self.mutator_detection_complete and self._race_confirmed_time:
                  elapsed = time.perf_counter() - self._race_confirmed_time
                  if elapsed > self.MUTATOR_TIMEOUT_AFTER_RACE:
                      self.logger.warning(f"种族已确认超过 {self.MUTATOR_TIMEOUT_AFTER_RACE} 秒，未发现突变因子。将突变因子确认为空。")
                      self.recognized_mutators = [] # 确认结果为空列表
                      self.mutator_detection_complete = True
                      continue # 进入下一个循环，将会触发上面的“所有任务完成”逻辑
               
                '''
                current_time = time.perf_counter()
                
                # 检查哪个任务需要扫描
                is_race_scan_due = not self.race_detection_complete and \
                                   current_time - self._last_race_scan_time >= self._race_scan_interval
                is_mutator_scan_due = not self.mutator_detection_complete and \
                                      current_time - self._last_mutator_scan_time >= self._mutator_scan_interval

                # 如果有任何一个任务需要扫描，才执行截图和预处理
                if is_race_scan_due or is_mutator_scan_due:
                    sc2_rect = get_sc2_window_geometry()
                    if not sc2_rect or not is_game_active():
                        time.sleep(1)
                        continue

                    x, y, w, h = sc2_rect
                    if w == 0 or h == 0:
                        time.sleep(1)
                        continue

                    scale_factor = float(w) / self.BASE_RESOLUTION_WIDTH
                    monitor = {"top": y, "left": x, "width": w, "height": h}
                    sct_img = sct.grab(monitor)
                    game_screen_bgr = cv2.cvtColor(np.array(sct_img), cv2.COLOR_BGRA2BGR)

                    x1, y1, x2, y2 = self._base_roi
                    if y2 > game_screen_bgr.shape[0] or x2 > game_screen_bgr.shape[1]:
                        time.sleep(1)
                        continue

                    roi_image = game_screen_bgr[y1:y2, x1:x2]
                    screenshot_gray = cv2.cvtColor(roi_image, cv2.COLOR_BGR2GRAY)

                    # 执行到期的任务
                    if is_race_scan_due:
                        self.logger.debug(f"执行种族扫描 (间隔: {self._race_scan_interval}s)")
                        self._scan_for_races(screenshot_gray, scale_factor)
                        self._last_race_scan_time = current_time

                    if is_mutator_scan_due:
                        self.logger.debug(f"执行突变因子扫描 (间隔: {self._mutator_scan_interval}s)")
                        self._scan_for_mutators(screenshot_gray, scale_factor)
                        self._last_mutator_scan_time = current_time

                # 主循环的短暂休眠，以防止CPU占用过高
                time.sleep(0.1)

# --- 使用示例 ---
if __name__ == '__main__':
    import logging
    # 设置日志级别为INFO，以获得更清晰的输出
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    print("正在启动实时识别器...")
    print("请确保星际争霸II游戏窗口是打开的。")
    print("按 Ctrl+C 停止程序。")

    recognizer = Mutator_and_enemy_race_automatic_recognizer()
    recognizer.start()

    try:
        while True:
            # 从识别器获取最新的已确认结果
            results = recognizer.get_results()

            # 在同一行上动态更新显示结果
            # \r (回车) 让光标回到行首，end='' 防止换行
            race_str = results['race'] if results['race'] else "Searching..."
            mutators_str = ', '.join(results['mutators']) if results['mutators'] else \
                           ("Searching..." if not recognizer.mutator_detection_complete else "None")

            print(f"\rRace: {race_str:<15} | Mutators: {mutators_str:<30}", end='')

            # 如果识别器线程已停止（任务完成），则退出主循环
            if not recognizer._thread.is_alive():
                print("\n所有识别任务完成，程序退出。")
                break

            time.sleep(1)
    except KeyboardInterrupt:
        print("\n程序被用户中断。")
    finally:
        # 确保在程序退出时停止后台线程
        recognizer.shutdown()
        print("识别器已关闭。")