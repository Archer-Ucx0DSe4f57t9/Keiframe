# -*- coding: utf-8 -*-
import cv2
import numpy as np
import os

# === 绿字 (中文/Terran) 专用配置 ===
INPUT_DIR = 'raw_screenshots'
OUTPUT_DIR = 'templates_green_zh_v2' # 建议输出到新文件夹方便对比

# === Tuner 验证过的参数 ===
SCALE_FACTOR = 4.0
TOPHAT_K = 3            # 【关键】必须启用，与Tuner一致
GLOBAL_THRESH_VAL = 31  # Tuner 验证的值
ERODE_ITER = 2          # Tuner 验证的值

def preprocess_green_text(img_bgr):
    if img_bgr is None: return None

    # 1. 放大
    h, w = img_bgr.shape[:2]
    img_resized = cv2.resize(img_bgr, (int(w * SCALE_FACTOR), int(h * SCALE_FACTOR)), interpolation=cv2.INTER_CUBIC)

    # 2. 颜色分离 (Mode 1: Green - Red)
    b, g, r = cv2.split(img_resized)
    gray = cv2.subtract(g, r)

    # 3. 【新增关键步骤】顶帽运算 + 归一化
    # 这是 Maker 生成结果变细、断裂的根本原因：缺少了这步亮度拉伸！
    if TOPHAT_K > 0:
        k_size = (TOPHAT_K * 2) + 1 
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k_size, k_size))
        gray = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, kernel)
        
        # === 核心修正 ===
        # 必须把亮度拉伸到 0-255，否则 Threshold 36 会把字切断
        gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)

    # 4. 双边滤波
    filtered = cv2.bilateralFilter(gray, d=9, sigmaColor=100, sigmaSpace=75)

    # 5. 全局阈值
    _, binary = cv2.threshold(filtered, GLOBAL_THRESH_VAL, 255, cv2.THRESH_BINARY)

    # 6. 腐蚀
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
    print(f"开始处理 {len(files)} 张图片 (绿色中文 V2)...")
    print(f"参数: TopHat={TOPHAT_K}, Thresh={GLOBAL_THRESH_VAL}, Erode={ERODE_ITER}")

    for filename in files:
        img = cv2.imread(os.path.join(INPUT_DIR, filename))
        if img is None: continue
        
        result = preprocess_green_text(img)
        
        if result is not None:
            out_path = os.path.join(OUTPUT_DIR, 'green_zh_' + filename)
            cv2.imwrite(out_path, result)
            print(f"已保存: {out_path}")

    print("完成！现在生成的字体粗细应该和 Tuner 预览完全一致了。")

if __name__ == '__main__':
    main()