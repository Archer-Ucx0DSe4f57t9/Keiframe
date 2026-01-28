# your_project/tests/test_recognizer.py

import sys
import os
import cv2
import logging
import shutil
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
from src.mutator_and_enemy_race_recognizer import Mutator_and_enemy_race_recognizer
current_dir = os.path.dirname(os.path.abspath(__file__))
# your_project/tests/test_recognizer_debug.py

# +++ 新增的调试函数 +++
def scan_with_debug(recognizer_instance, screenshot_gray, scan_type):
    """一个包装函数，用于执行扫描并打印所有模板的最高匹配分数。"""
    templates = getattr(recognizer_instance, f"{scan_type}_templates")
    if not templates:
        return

    logger.info(f"--- 正在调试扫描: {scan_type.upper()} ---")
    all_scores = {}
    for name, template in templates.items():
        if template.shape[0] > screenshot_gray.shape[0] or template.shape[1] > screenshot_gray.shape[1]:
            continue
        
        res = cv2.matchTemplate(screenshot_gray, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(res)
        all_scores[name] = max_val
    
    # 按分数从高到低排序后打印
    sorted_scores = sorted(all_scores.items(), key=lambda item: item[1], reverse=True)
    
    for name, score in sorted_scores:
        status = " (低于阈值)" if score < recognizer_instance.CONFIDENCE_THRESHOLD else " (!!! 高于阈值 !!!)"
        logger.info(f"  模板 '{name}': 最高匹配分数 = {score:.4f}{status}")


# --- 测试脚本主逻辑 ---
if __name__ == "__main__":
    # 配置一个简单的日志记录器
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger("DEBUG_TEST")

    # --- 1. 从命令行获取文件名 ---
    if len(sys.argv) < 2:
        logger.error("用法: python tests/test_recognizer_debug.py <图片文件名>")
        sys.exit(1)

    SAMPLE_IMAGE_FILENAME = sys.argv[1]
    sample_image_path = os.path.join(current_dir, 'samples', SAMPLE_IMAGE_FILENAME)

    if not os.path.exists(sample_image_path):
        logger.error(f"测试图片未找到: {sample_image_path}")
        sys.exit(1)
        
    # --- 2. 创建用于存放调试图片的文件夹 ---
    debug_output_dir = os.path.join(current_dir, "debug_output")
    if os.path.exists(debug_output_dir):
        shutil.rmtree(debug_output_dir) # 每次运行时清空旧的调试结果
    os.makedirs(debug_output_dir)
    logger.info(f"调试图片将保存在: {debug_output_dir}")

    # --- 3. 初始化识别器 ---
    recognizer = Mutator_and_enemy_race_recognizer()
    
    # (可选) 如果需要，可以在这里临时降低阈值进行测试
    # recognizer.CONFIDENCE_THRESHOLD = 0.7 

    # --- 4. 加载并保存ROI图片 ---
    full_screenshot = cv2.imread(sample_image_path, cv2.IMREAD_COLOR)
    roi_coords = recognizer.RECOGNITION_ROI
    roi_image = full_screenshot[
        roi_coords['top'] : roi_coords['top'] + roi_coords['height'],
        roi_coords['left'] : roi_coords['left'] + roi_coords['width']
    ]
    screenshot_gray = cv2.cvtColor(roi_image, cv2.COLOR_BGR2GRAY)
    
    # 保存代码实际“看到”的区域，这是最重要的检查点
    roi_save_path = os.path.join(debug_output_dir, "_roi_to_recognize.png")
    cv2.imwrite(roi_save_path, screenshot_gray)
    logger.info(f"已将被识别的灰度图区域保存到: {roi_save_path}")

    # --- 5. 执行带详细日志的扫描 ---
    scan_with_debug(recognizer, screenshot_gray, "race")
    scan_with_debug(recognizer, screenshot_gray, "mutator")
    
    # --- 6. 正常执行原逻辑以获得最终结果 ---
    logger.info("\n--- 正在执行原有的连续识别逻辑 (用于最终确认) ---")
    
    TEST_SCALE_FACTOR = 1.0
    
    for _ in range(recognizer.CONSECUTIVE_MATCH_REQUIREMENT):
        if not recognizer.race_detection_complete:
            # 传入 scale_factor 解决 TypeError
            recognizer._scan_for_races(screenshot_gray, TEST_SCALE_FACTOR)
        if not recognizer.mutator_detection_complete:
            # 传入 scale_factor 解决 TypeError
            recognizer._scan_for_mutators(screenshot_gray, TEST_SCALE_FACTOR)
    
    # --- 7. 输出最终结果 ---
    final_results = recognizer.get_results()
    print("\n" + "="*30)
    print("      最终识别结果")
    print("="*30)
    print(f"  测试图片: {SAMPLE_IMAGE_FILENAME}")
    print(f"  识别出的种族: {final_results['race']}")
    print(f"  识别出的突变因子: {final_results['mutators']}")
    print("="*30)