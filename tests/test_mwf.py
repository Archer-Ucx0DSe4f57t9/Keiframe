# test_malwarfare_map_handler.py
import cv2
import sys
import os
import argparse
import time
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
from map_handlers.malwarfare_map_handler import MalwarfareMapHandler

def main():
    parser = argparse.ArgumentParser(description="Test MalwarfareMapHandler OCR")
    parser.add_argument("images", nargs='+', help="输入的截图文件路径 (支持多个文件)")
    parser.add_argument("--show", action="store_true", help="是否显示ROI区域")
    args = parser.parse_args()

    # 创建 handler 实例，只创建一次以节省初始化时间
    handler = MalwarfareMapHandler(None, None, None)

    for image_path in args.images:
        print(f"\n--- 处理文件: {image_path} ---")

        if not os.path.exists(image_path):
            print(f"文件不存在: {image_path}")
            continue

        # 读取图片
        img = cv2.imread(image_path)
        if img is None:
            print("无法读取图片:", image_path)
            continue

        H, W = img.shape[:2]
        print(f"图片尺寸: {W}x{H}")

        # 计算 ROI
        roi = handler._roi
        print("计算出的 ROI:", roi)

        # 计时开始
        start_time = time.perf_counter()

        # 调用 OCR
        n = handler._ocr_and_process_count
        time = handler._ocr_and_process_paused
        paused = handler._ocr_and_process_paused
        
        # 计时结束
        end_time = time.perf_counter()
        duration = (end_time - start_time) * 1000  # 转换为毫秒

        print(f"OCR 原始输出: {repr()}")
        print(f"识别耗时: {duration:.2f} ms")

        # 正则解析
        parsed = parse_text(text)
        print(f"解析结果: {parsed}")

        # 显示 ROI 区域
        if args.show:
            preview = img.copy()
            x0, y0, x1, y1 = roi
            cv2.rectangle(preview, (x0, y0), (x1, y1), (0, 255, 0), 2)
            
            # 在图片上显示结果
            display_text = f"Time: {duration:.2f}ms | Result: {parsed}"
            cv2.putText(preview, display_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            
            cv2.imshow("ROI", preview)
            cv2.waitKey(0)
            cv2.destroyAllWindows()

if __name__ == "__main__":
    main()