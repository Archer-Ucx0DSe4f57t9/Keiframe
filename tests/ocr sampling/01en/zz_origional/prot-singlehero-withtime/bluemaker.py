# -*- coding: utf-8 -*-
import cv2
import numpy as np
import os

# === 蓝色文字 (Blue/Protoss) 专用配置 ===
INPUT_DIR = 'raw_screenshots'
OUTPUT_DIR = 'templates_blue_processed'

# === 你调试出的参数 ===
SCALE_FACTOR = 4.0      # 默认放大倍数
TOPHAT_K = 4            # 去纹理核心参数
GLOBAL_THRESH_VAL = 45  # 低阈值配合TopHat
ERODE_ITER = 2          # 稍微削细

def preprocess_blue_text(img_bgr):
    if img_bgr is None: return None

    # 1. 放大 (Scale 4.0)
    h, w = img_bgr.shape[:2]
    img_resized = cv2.resize(img_bgr, (int(w * SCALE_FACTOR), int(h * SCALE_FACTOR)), interpolation=cv2.INTER_CUBIC)

    # 2. 颜色分离 (Blue Channel)
    # 蓝色文字特征：蓝色通道极亮
    b, g, r = cv2.split(img_resized)
    gray = b

    # 3. 顶帽运算 (TopHat = 4)
    # 这一步能有效把背景纹理抹平，只留下突出的文字
    if TOPHAT_K > 0:
        k_size = (TOPHAT_K * 2) + 1 
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k_size, k_size))
        gray = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, kernel)
        # 拉伸对比度，确保文字亮度足够
        gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)

    # 4. 双边滤波 (标准降噪)
    filtered = cv2.bilateralFilter(gray, d=9, sigmaColor=100, sigmaSpace=75)

    # 5. 全局阈值 (Thresh = 31)
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
    print(f"开始处理 {len(files)} 张图片 (蓝色文字模式)...")
    print(f"参数: TopHat={TOPHAT_K}, Thresh={GLOBAL_THRESH_VAL}, Erode={ERODE_ITER}")

    for filename in files:
        img = cv2.imread(os.path.join(INPUT_DIR, filename))
        if img is None: continue
        
        result = preprocess_blue_text(img)
        
        if result is not None:
            # 加前缀 blue_ 防止混淆
            out_path = os.path.join(OUTPUT_DIR, 'blue_' + filename)
            cv2.imwrite(out_path, result)
            print(f"已保存: {out_path}")

    print("="*30)
    print("完成！请去 templates_blue_processed 文件夹裁剪蓝色数字。")

if __name__ == '__main__':
    main()