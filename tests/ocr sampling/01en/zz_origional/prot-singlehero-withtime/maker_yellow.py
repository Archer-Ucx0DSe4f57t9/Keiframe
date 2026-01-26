# -*- coding: utf-8 -*-
import cv2
import numpy as np
import os

# === 黄色文字 (Yellow) 专用配置 ===
INPUT_DIR = 'raw_screenshots'
OUTPUT_DIR = 'templates_yellow_processed'

# 固化你调试出来的黄金参数
SCALE_FACTOR = 4.0        # 之前确定的4倍放大
COLOR_MODE = 3            # 3 = R+G 混合模式
TOPHAT_K = 3              # 你发现的最佳值
ERODE_ITER = 2            # 刚好削细一点点
GLOBAL_THRESH_VAL = 31    # 你的阈值

def preprocess_yellow_text(img_bgr):
    if img_bgr is None: return None

    # 1. 放大
    h, w = img_bgr.shape[:2]
    img_resized = cv2.resize(img_bgr, (int(w * SCALE_FACTOR), int(h * SCALE_FACTOR)), interpolation=cv2.INTER_CUBIC)

    # 2. 颜色策略 (Mode 3: R+G 混合)
    b, g, r = cv2.split(img_resized)
    # 黄色 = 红+绿，混合这两个通道能最大程度保留黄色亮度
    gray = cv2.addWeighted(r, 0.5, g, 0.5, 0)

    # 3. 顶帽运算 (TopHat 2)
    if TOPHAT_K > 0:
        k_size = (TOPHAT_K * 2) + 1 
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k_size, k_size))
        gray = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, kernel)
        # 拉伸对比度 (可选，但在低阈值下不拉伸也行，这里保持原样以匹配你的调试结果)
        gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)

    # 4. 双边滤波 (保持默认清理一下杂色)
    filtered = cv2.bilateralFilter(gray, d=9, sigmaColor=100, sigmaSpace=75)

    # 5. 全局阈值 (Thresh 17)
    _, binary = cv2.threshold(filtered, GLOBAL_THRESH_VAL, 255, cv2.THRESH_BINARY)

    # 6. 腐蚀 (Erode 1)
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
    print(f"开始处理 {len(files)} 张图片 (黄色文字模式)...")

    for filename in files:
        img = cv2.imread(os.path.join(INPUT_DIR, filename))
        if img is None: continue
        
        result = preprocess_yellow_text(img)
        
        if result is not None:
            # 加上前缀 yellow_ 方便区分
            out_path = os.path.join(OUTPUT_DIR, 'yellow_' + filename)
            cv2.imwrite(out_path, result)
            print(f"已保存: {out_path}")

    print("完成！请去 output 文件夹裁剪数字。")

if __name__ == '__main__':
    main()