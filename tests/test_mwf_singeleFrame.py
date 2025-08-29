# 文件路径: tests/run_single_frame_test.py (增强诊断版)

import cv2
import sys
import os
import argparse
import time
import numpy as np

def get_sc2_window_geometry():
    # 这是一个模拟函数，请用您自己的函数替换
    # 在实际使用中，它应该返回 (x, y, w, h)
    # 这里我们模拟一个 1920x1080 的窗口，以便观察缩放效果
    return (0, 0, 1936, 1119)

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

def mock_get_window_geometry():
    return None

# --- 增强版Debug函数 ---
def debug_dump_roi_and_scores(handler, img_bgr, roi, scale_factor, ocr_scale_factor, color_type, name, outdir, top_k=10):
    x0, y0, x1, y1 = roi
    roi_img = img_bgr[y0:y1, x0:x1]
    if roi_img.size == 0:
        print(f"\n[DIAGNOSTIC] {name}: ROI为空，跳过。")
        return

    h, w = roi_img.shape[:2]
    enlarged_roi = cv2.resize(roi_img, (int(w * ocr_scale_factor), int(h * ocr_scale_factor)), interpolation=cv2.INTER_CUBIC)

    mask = handler._preprocess_image(enlarged_roi, color_type)
    if mask is None:
        print(f"\n[DIAGNOSTIC] {name}: 预处理返回None (color_type={color_type})")
        return

    print(f"\n----------- DIAGNOSTIC: [{name}] -----------")
    
    scores = []
    if not handler.templates:
        print("[DIAGNOSTIC] 错误: handler.templates 为空，没有加载任何模板！")
        return
        
    for ch, tmpl in handler.templates.items():
        if tmpl is None: 
            continue

        th, tw = tmpl.shape[:2]
        final_template_scale = scale_factor
        
        if int(tw * final_template_scale) < 1 or int(th * final_template_scale) < 1:
            continue

        scaled_template = cv2.resize(tmpl, (int(tw * final_template_scale), int(th * final_template_scale)), interpolation=cv2.INTER_CUBIC)
        _, scaled_template_binary = cv2.threshold(scaled_template, 127, 255, cv2.THRESH_BINARY)

        if scaled_template_binary.shape[0] > mask.shape[0] or scaled_template_binary.shape[1] > mask.shape[1]:
            continue

        res = cv2.matchTemplate(mask, scaled_template_binary, cv2.TM_CCOEFF_NORMED)
        _, maxv, _, _ = cv2.minMaxLoc(res)
        scores.append((ch, float(maxv)))

    scores.sort(key=lambda x: x[1], reverse=True)
    
    print(f"为区域 '{name}' 计算出的最高匹配分数:")
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
        table_area=None,
        toast_manager=MockToastManager(),
        logger=MockLogger() # 强制开启handler内部的debug模式
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
    print(f"[INFO] 图像宽度={current_width}, 基准宽度={handler.BASE_RESOLUTION_WIDTH}, 分辨率缩放因子={scale_factor:.3f}")

    # 直接调用debug函数获取分数
    outdir = os.path.join(os.path.dirname(args.image_path) or ".", "debug_out")
    debug_dump_roi_and_scores(handler, img, handler._count_roi,  scale_factor, 2.5, 'green', "Count", outdir)
    debug_dump_roi_and_scores(handler, img, handler._time_roi,   scale_factor, 2.0, 'yellow', "Time", outdir)
    debug_dump_roi_and_scores(handler, img, handler._paused_roi, scale_factor, 2.0, 'yellow', "Paused", outdir)

    # 运行一次真实的识别流程以供对比
    print("\n[INFO] 正在运行真实的内部OCR识别流程...")
    handler._ocr_and_process_count(img, scale_factor)
    handler._ocr_and_process_time_and_paused(img, scale_factor)
    handler._update_latest_result()
    print(f"[INFO] 内部OCR识别完成。最终结果: {handler._latest_result}")


if __name__ == "__main__":
    main()