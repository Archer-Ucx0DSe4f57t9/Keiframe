# -*- coding: utf-8 -*-
import cv2
import numpy as np
import os

# === 绿字专用配置 ===
INPUT_DIR = 'raw_screenshots'          # 你的原始截图文件夹
OUTPUT_DIR = 'templates_green_processed' # 输出文件夹
SCALE_FACTOR = 4
GLOBAL_THRESH_VAL = 10  # 【重要】请填入你在 Tuner 中调试出的 'C / Global Thresh' 数值
ERODE_ITER = 3          # 你确认的腐蚀次数

def preprocess_green_text(img_bgr):
    if img_bgr is None: return None

    # 1. 放大
    h, w = img_bgr.shape[:2]
    img_resized = cv2.resize(img_bgr, (int(w * SCALE_FACTOR), int(h * SCALE_FACTOR)), interpolation=cv2.INTER_CUBIC)

    # 2. 颜色分离 (Mode 1: Green - Red)
    # 利用绿字无红光、沙子有红光的特性，分离背景
    b, g, r = cv2.split(img_resized)
    gray = cv2.subtract(g, r)

    # 3. 双边滤波 (轻微去噪)
    filtered = cv2.bilateralFilter(gray, d=9, sigmaColor=100, sigmaSpace=75)

    # 4. 全局阈值 (Thresh Mode 1)
    # 因为背景已经很黑了，直接切一刀最干净
    _, binary = cv2.threshold(filtered, GLOBAL_THRESH_VAL, 255, cv2.THRESH_BINARY)

    # 5. 腐蚀 (Erode 3)
    # 削细文字，解决粘连
    if ERODE_ITER > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        binary = cv2.erode(binary, kernel, iterations=ERODE_ITER)

    return binary

def main():
    if not os.path.exists(INPUT_DIR):
        print(f"错误：找不到文件夹 '{INPUT_DIR}'")
        return
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    files = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith(('.png', '.jpg'))]
    print(f"开始处理 {len(files)} 张图片 (绿字专用模式)...")

    for filename in files:
        img = cv2.imread(os.path.join(INPUT_DIR, filename))
        result = preprocess_green_text(img)
        
        if result is not None:
            out_path = os.path.join(OUTPUT_DIR, 'green_' + filename)
            cv2.imwrite(out_path, result)
            print(f"已保存: {out_path}")

    print("完成！请去 output 文件夹查看结果。")

if __name__ == '__main__':
    main()