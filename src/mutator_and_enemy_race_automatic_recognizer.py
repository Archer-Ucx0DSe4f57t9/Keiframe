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

class Mutator_and_enemy_race_automatic_recognizer:
    """
    通过屏幕捕捉和模板匹配，识别游戏中的种族和突变因子图标。

    它会监控一个固定的屏幕区域，并将其与 'icons/races' 和 'icons/mutators'
    文件夹中的模板图片进行比对。当一个图标连续匹配10次后，会被确认为最终结果。
    """
    
    # --- 配置常量 ---
    # 目标识别区域 (基于 1920x1080 分辨率)
    RECOGNITION_ROI = {'left': 1850, 'top': 190, 'width': 70, 'height': 574}
    
    # 模板匹配的置信度阈值
    CONFIDENCE_THRESHOLD = 0.8
    
    # 确认结果所需的连续匹配次数
    CONSECUTIVE_MATCH_REQUIREMENT = 10

    def __init__(self):
        self.logger = get_logger(__name__)
        # --- 状态变量初始化 ---
        self._running = False
        self._thread = None
        self.base_dir = os.path.dirname(__file__)

        # 加载模板
        self.race_templates = self._load_templates(os.path.join(self.base_dir, '..', 'resources', 'icons', 'races'))
        self.mutator_templates = self._load_templates(os.path.join(self.base_dir, '..', 'resources', 'icons', 'mutators'))

        # 初始化状态和结果存储
        self._reset_state()

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

        # 用于跟踪连续匹配次数的计数器
        self.race_candidates = {name: 0 for name in self.race_templates.keys()}
        self.mutator_candidates = {name: 0 for name in self.mutator_templates.keys()}
        
        # 记录上一轮的最佳匹配项，用于判断是否“连续”
        self._last_best_race_match = None

        # 控制是否继续扫描特定内容
        self.race_detection_complete = False
        self.mutator_detection_complete = False

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

    def _scan_for_races(self, screenshot_gray):
        """在截图中扫描并更新种族识别状态。"""
        if not self.race_templates: return False

        best_match_name = None
        max_score = self.CONFIDENCE_THRESHOLD - 0.01 # 确保初始值低于阈值

        # 1. 遍历所有模板，找到最佳匹配
        for name, template in self.race_templates.items():
            if template.shape[0] > screenshot_gray.shape[0] or template.shape[1] > screenshot_gray.shape[1]:
                continue
            
            res = cv2.matchTemplate(screenshot_gray, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(res)
            
            if max_val > max_score:
                max_score = max_val
                best_match_name = name

        # 2. 根据最佳匹配更新连续计数器
        a_potential_match_found = False
        if best_match_name: # 如果找到了一个高于阈值的最佳匹配
            a_potential_match_found = True
            if self._last_best_race_match == best_match_name:
                self.race_candidates[best_match_name] += 1
            else:
                # 最佳匹配项已改变，重置所有计数器
                self.race_candidates = {n: 0 for n in self.race_templates.keys()}
                self.race_candidates[best_match_name] = 1
            
            self._last_best_race_match = best_match_name
            self.logger.debug(f"种族潜在匹配: {best_match_name} (分数: {max_score:.2f}, 连续次数: {self.race_candidates[best_match_name]})")

            # 3. 检查是否满足最终确认条件
            if self.race_candidates[best_match_name] >= self.CONSECUTIVE_MATCH_REQUIREMENT:
                self.recognized_race = best_match_name
                self.race_detection_complete = True
                self.logger.info(f"** 种族已确认: {self.recognized_race} **")
        else: # 如果没有任何匹配项超过阈值
            self._last_best_race_match = None
            self.race_candidates = {n: 0 for n in self.race_templates.keys()}

        return a_potential_match_found

    def _scan_for_mutators(self, screenshot_gray):
        """在截图中扫描并更新突变因子识别状态。"""
        if not self.mutator_templates: return False
        
        a_potential_match_found = False
        
        # 1. 遍历所有突变因子模板
        for name, template in self.mutator_templates.items():
            # 如果已经识别，则跳过
            if name in self.recognized_mutators:
                continue

            if template.shape[0] > screenshot_gray.shape[0] or template.shape[1] > screenshot_gray.shape[1]:
                continue

            res = cv2.matchTemplate(screenshot_gray, template, cv2.TM_CCOEFF_NORMED)
            loc = np.where(res >= self.CONFIDENCE_THRESHOLD)

            # 2. 更新计数器
            if len(loc[0]) > 0: # 找到了匹配
                a_potential_match_found = True
                self.mutator_candidates[name] += 1
                self.logger.debug(f"突变因子潜在匹配: {name} (连续次数: {self.mutator_candidates[name]})")
            else: # 未找到匹配，重置计数
                self.mutator_candidates[name] = 0

            # 3. 检查是否满足最终确认条件
            if self.mutator_candidates[name] >= self.CONSECUTIVE_MATCH_REQUIREMENT:
                if name not in self.recognized_mutators:
                    self.recognized_mutators.append(name)
                    self.logger.info(f"** 突变因子已确认: {name} **")
        
        # 4. 如果有任何一个突变因子被确认，就停止整个突变因子的扫描
        if len(self.recognized_mutators) > 0:
            self.mutator_detection_complete = True
            
        return a_potential_match_found

    def _run_loop(self):
        """后台线程的主循环，负责截图和调度识别任务。"""
        with mss.mss() as sct:
            while self._running:
                # 如果所有任务都已完成，则线程可以退出循环
                if self.race_detection_complete and self.mutator_detection_complete:
                    self.logger.info("所有识别任务已完成，线程将休眠。")
                    self.shutdown() # 自动停止
                    break

                # 截图并转换为灰度图
                sct_img = sct.grab(self.RECOGNITION_ROI)
                img_bgr = np.array(sct_img)
                screenshot_gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
                
                found_something = False

                # --- 执行识别任务 ---
                if not self.race_detection_complete:
                    if self._scan_for_races(screenshot_gray):
                        found_something = True
                
                if not self.mutator_detection_complete:
                    if self._scan_for_mutators(screenshot_gray):
                        found_something = True

                # --- 根据结果决定休眠时间 ---
                if found_something:
                    time.sleep(1) # 发现潜在目标，1秒后快速跟进
                else:
                    time.sleep(5) # 未发现任何目标，5秒后重试

# --- 使用示例 ---
if __name__ == '__main__':
    # 假设您有一个名为 logging_util.py 的文件来设置日志记录器
    # from logging_util import setup_logger
    # setup_logger() 
    
    # 创建一个假的日志记录器以便于测试
    import logging
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # 确保图标目录和文件存在
    print("请确保在 'game_info_recognizer.py' 的同级目录下有 'icons/races' 和 'icons/mutators' 文件夹，并包含PNG模板图片。")

    # 初始化并启动识别器
    recognizer = Mutator_and_enemy_race_automatic_recognizer()
    recognizer.start()

    try:
        # 模拟主程序运行，每5秒检查一次结果
        for i in range(12): # 模拟运行60秒
            time.sleep(5)
            results = recognizer.get_results()
            print(f"--- 当前识别结果 ({i*5+5}秒) ---")
            print(f"  种族: {results['race']}")
            print(f"  突变因子: {results['mutators']}")
            
            # 如果中途需要重置（例如，开始新的一局游戏）
            # if i == 5:
            #     print("\n!!! 模拟开始新游戏，正在重置识别器 !!!\n")
            #     recognizer.reset_and_start()

    except KeyboardInterrupt:
        print("\n程序被用户中断。")
    finally:
        # 确保在程序退出时停止后台线程
        recognizer.shutdown()
        print("识别器已关闭。")