# -*- coding: utf-8 -*-
import cv2
import numpy as np
import os

INPUT_DIR = 'raw_screenshots'
OUTPUT_DIR = 'templates_green_processed_v2' # 改个输出文件夹名，避免混淆

# === 修正后的绿字参数 ===
SCALE_FACTOR = 4
# 【修正1】提高阈值。
# 绿字很亮，设为 60-80 可以有效过滤掉导致粘连的光晕。
GLOBAL_THRESH_VAL = 60  
# 【修正2】增加腐蚀力度。
# 针对数字5的粘连，我们需要更强的断开能力。
ERODE_ITER = 1 

def preprocess_green_text(img_bgr):
    if img_bgr is None: return None

    # 1. 放大 (保持 4倍)
    h, w = img_bgr.shape[:2]
    img_resized = cv2.resize(img_bgr, (int(w * SCALE_FACTOR), int(h * SCALE_FACTOR)), interpolation=cv2.INTER_CUBIC)

    # 2. 颜色分离 (Green - Red)
    b, g, r = cv2.split(img_resized)
    gray = cv2.subtract(g, r)

    # 3. 双边滤波
    filtered = cv2.bilateralFilter(gray, d=9, sigmaColor=100, sigmaSpace=75)

    # 4. 全局阈值 (Thresh)
    # 提高到 60，让字变瘦
    _, binary = cv2.threshold(filtered, GLOBAL_THRESH_VAL, 255, cv2.THRESH_BINARY)

    # 5. 【修正3】改用形态学“开运算” (Morphology OPEN)
    # 开运算 = 先腐蚀后膨胀。
    # 它的特技是：能把细微的连接处（比如5那里的粘连）切断，但保持字的主体大小不变。
    # 配合 3x3 的核，效果比单纯腐蚀更好。
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=ERODE_ITER)

    return binary

def main():
    if not os.path.exists(INPUT_DIR):
        print(f"错误：找不到文件夹 '{INPUT_DIR}'")
        return
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    files = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith(('.png', '.jpg'))]
    print(f"开始处理 {len(files)} 张图片 (绿字 V2 修正版)...")

    for filename in files:
        img = cv2.imread(os.path.join(INPUT_DIR, filename))
        if img is None: continue
        
        result = preprocess_green_text(img)
        
        if result is not None:
            out_path = os.path.join(OUTPUT_DIR, 'green_v2_' + filename)
            cv2.imwrite(out_path, result)
            print(f"已保存: {out_path}")

    print("完成！请检查新生成的图片中 '5' 是否清晰。")

if __name__ == '__main__':
    main()