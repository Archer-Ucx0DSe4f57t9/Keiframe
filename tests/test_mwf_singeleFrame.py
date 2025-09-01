# 文件路径: tests/run_single_frame_test.py (增强诊断版)

import cv2
import sys
import os
import argparse
import time
import numpy as np

# 调整路径以从'src'目录导入处理器
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.map_handlers.malwarfare_map_handler import MalwarfareMapHandler

# --- 用于测试的模拟对象 ---
class MockLogger:
    def info(self, m): print(f"[INFO] {m}")
    def debug(self, m): print(f"[DEBUG] {m}")
    def warning(self, m): print(f"[WARNING] {m}")
    def error(self, m, exc_info=False): print(f"[ERROR] {m}")

class MockToastManager:
    def show_simple_toast(self, message): print(f"[TOAST] {message}")
    def hide_toast(self): print("[TOAST] Hiding toast...")

# --- 增强版Debug函数 ---
def debug_dump_roi_and_scores(handler, img_bgr, roi_name, scale_factor, top_k=10):
    """
    增强的诊断函数，能自动获取ROI并测试多种颜色。
    :param roi_name: 字符串, 如 "_count_roi", "_time_roi"
    """
    roi = getattr(handler, roi_name, None)
    if roi is None:
        print(f"\n[DIAGNOSTIC] {roi_name}: ROI未设置(值为None)，跳过。")
        return

    # 根据ROI名称确定要测试的颜色和参数
    if roi_name == '_count_roi':
        colors_to_test = handler.count_color_processors.keys()
        ocr_scale_factor = 2.5
        area_name = "Count"
    else:
        # 假设 Time 和 Paused 区域固定为 yellow
        # 注意: handler._preprocess_image 需要支持 'yellow'
        colors_to_test = ['yellow'] 
        ocr_scale_factor = 2.0
        area_name = "Time" if roi_name == '_time_roi' else "Paused"

    print(f"\n----------- DIAGNOSTIC: [{area_name}] -----------")
    
    x0, y0, x1, y1 = roi
    roi_img = img_bgr[y0:y1, x0:x1]
    if roi_img.size == 0:
        print(f"ROI为空图像，跳过。")
        return

    h, w = roi_img.shape[:2]
    enlarged_roi = cv2.resize(roi_img, (int(w * ocr_scale_factor), int(h * ocr_scale_factor)), interpolation=cv2.INTER_CUBIC)
    hsv_img = cv2.cvtColor(enlarged_roi, cv2.COLOR_BGR2HSV)
    
    if not handler.templates:
        print("[DIAGNOSTIC] 错误: handler.templates 为空！")
        return

    # 对每种可能的颜色进行测试
    for color_type in colors_to_test:
        print(f"--- 测试颜色: {color_type.upper()} ---")
        
        lower, upper = None, None
        if color_type in handler.count_color_processors:
            lower, upper = handler.count_color_processors[color_type]
        elif color_type == 'yellow': # 为Time/Paused区域添加支持
             lower, upper = handler.yellow_lower, handler.yellow_upper

        if lower is None:
            print(f"未在handler中找到'{color_type}'的颜色定义。")
            continue

        mask = cv2.inRange(hsv_img, lower, upper)
        
        scores = []
        for ch, tmpl in handler.templates.items():
            if tmpl is None: continue

            th, tw = tmpl.shape[:2]
            scaled_template = cv2.resize(tmpl, (int(tw * scale_factor), int(th * scale_factor)), cv2.INTER_CUBIC)
            _, scaled_template_binary = cv2.threshold(scaled_template, 127, 255, cv2.THRESH_BINARY)

            if scaled_template_binary.shape[0] > mask.shape[0] or scaled_template_binary.shape[1] > mask.shape[1]:
                continue

            res = cv2.matchTemplate(mask, scaled_template_binary, cv2.TM_CCOEFF_NORMED)
            _, maxv, _, _ = cv2.minMaxLoc(res)
            scores.append((ch, float(maxv)))

        scores.sort(key=lambda x: x[1], reverse=True)
        
        print(f"为区域 '{area_name}' (颜色: {color_type}) 计算出的最高匹配分数:")
        for i, (char, score) in enumerate(scores[:top_k]):
            print(f"  Top {i+1}: 模板 '{char}.png' -> 分数 = {score:.4f}")

    print("------------------------------------------")


def main():
    parser = argparse.ArgumentParser(description="MalwarfareMapHandler的单帧OCR诊断工具。")
    parser.add_argument('image_path', type=str, help="要测试的图像文件路径。")
    args = parser.parse_args()

    if not os.path.exists(args.image_path):
        print(f"错误: 图像文件未在 {args.image_path} 找到")
        return

    handler = MalwarfareMapHandler(
        toast_manager=MockToastManager(),
        logger=MockLogger()
    )

    if not handler.templates:
        print("\n[CRITICAL ERROR] 模板未能成功加载，请检查 'char_templates_1920w' 文件夹路径和内容。")
        return

    img = cv2.imread(args.image_path)
    if img is None:
        print(f"错误: 无法从 {args.image_path} 读取图像")
        return

    current_width = img.shape[1]
    scale_factor = current_width / handler.BASE_RESOLUTION_WIDTH
    print(f"\n[INFO] 图像宽度={current_width}, 基准宽度={handler.BASE_RESOLUTION_WIDTH}, 分辨率缩放因子={scale_factor:.3f}")

    # --- 核心修正 ---
    # 新增: 首先运行UI状态探测，以设置正确的ROI
    print("\n[INFO] 步骤1: 运行UI状态探测以确定ROI位置...")
    if not handler._detect_and_set_ui_state(img):
        print("[CRITICAL ERROR] UI状态探测失败！无法确定ROI位置。请检查图像是否为游戏截图，以及偏移/颜色定义是否正确。")
        return
    print(f"[INFO] UI状态探测成功，当前状态为: {handler._current_ui_offset_state}")

    # 步骤2: 运行增强的诊断函数
    print("\n[INFO] 步骤2: 运行详细的模板匹配诊断...")
    debug_dump_roi_and_scores(handler, img, '_count_roi',  scale_factor)
    debug_dump_roi_and_scores(handler, img, '_time_roi',   scale_factor)
    debug_dump_roi_and_scores(handler, img, '_paused_roi', scale_factor)

    # 步骤3: 运行一次真实的识别流程以供对比
    print("\n[INFO] 步骤3: 运行真实的内部OCR识别流程...")
    handler._ocr_and_process_count(img, scale_factor)
    handler._ocr_and_process_time_and_paused(img, scale_factor)
    handler._update_latest_result()
    
    # 最终结果现在存储在 _latest_result 中
    final_result = None
    with handler._result_lock:
        final_result = handler._latest_result
    print(f"\n[INFO] 内部OCR识别完成。最终结果: {final_result}")


if __name__ == "__main__":
    main()