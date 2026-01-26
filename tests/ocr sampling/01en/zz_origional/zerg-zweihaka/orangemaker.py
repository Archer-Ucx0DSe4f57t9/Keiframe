# -*- coding: utf-8 -*-
import cv2
import numpy as np
import os

# === 橙色文字 (Orange/Zerg) 专用配置 ===
INPUT_DIR = 'raw_screenshots'
OUTPUT_DIR = 'templates_orange_processed'

# === 你调试出的黄金参数 ===
SCALE_FACTOR = 4.0
TOPHAT_K = 3            # TopHat = 3
GLOBAL_THRESH_VAL = 41  # Threshold = 41
ERODE_ITER = 1          # Erode = 1
EXTRACTION_MODE = 1     # 1 = (Red - Blue) 色差法

def preprocess_orange_text(img_bgr):
    if img_bgr is None: return None

    # 1. 放大 (Scale 4.0)
    h, w = img_bgr.shape[:2]
    img_resized = cv2.resize(img_bgr, (int(w * SCALE_FACTOR), int(h * SCALE_FACTOR)), interpolation=cv2.INTER_CUBIC)

    # 2. 颜色提取策略 (Mode 1: Red - Blue)
    # 橙色特征：红色分量极高，蓝色分量极低。
    # 背景特征：水泥地/沙地通常 R,G,B 值比较接近。
    # 算法：R - B，能最大程度突出橙色，压暗灰色背景。
    b, g, r = cv2.split(img_resized)
    
    # 注意：opencv的subtract会自动处理负数（截断为0），这正是我们要的
    gray = cv2.subtract(r, b)

    # 3. 顶帽运算 (TopHat = 3)
    # 去除残留的背景纹理
    if TOPHAT_K > 0:
        k_size = (TOPHAT_K * 2) + 1 
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k_size, k_size))
        gray = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, kernel)
        # 拉伸对比度
        gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)

    # 4. 双边滤波 (降噪)
    filtered = cv2.bilateralFilter(gray, d=9, sigmaColor=100, sigmaSpace=75)

    # 5. 全局阈值 (Thresh = 41)
    _, binary = cv2.threshold(filtered, GLOBAL_THRESH_VAL, 255, cv2.THRESH_BINARY)

    # 6. 腐蚀 (Erode = 1)
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
    print(f"开始处理 {len(files)} 张图片 (橙色文字 Mode 1)...")
    print(f"参数: Mode=R-B, TopHat={TOPHAT_K}, Thresh={GLOBAL_THRESH_VAL}, Erode={ERODE_ITER}")

    for filename in files:
        img = cv2.imread(os.path.join(INPUT_DIR, filename))
        if img is None: continue
        
        result = preprocess_orange_text(img)
        
        if result is not None:
            # 加前缀 orange_v2_
            out_path = os.path.join(OUTPUT_DIR, 'orange_v2_' + filename)
            cv2.imwrite(out_path, result)
            print(f"已保存: {out_path}")

    print("="*30)
    print("完成！请去 output 文件夹查看效果并裁剪。")

if __name__ == '__main__':
    main()