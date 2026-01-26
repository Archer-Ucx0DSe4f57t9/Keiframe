# -*- coding: utf-8 -*-
import cv2
import numpy as np

# === 填入你的橙色文字原始截图路径 ===
IMAGE_PATH = 'raw_screenshots/orange_test.png'
# ===================================

window_name = 'Orange Text Tuner V2 - Saturation Special'

def nothing(x):
    pass

def processing_pipeline(img_bgr):
    # === 获取滑块参数 ===
    scale_x10 = cv2.getTrackbarPos('Scale (x10)', window_name)
    mode = cv2.getTrackbarPos('Extraction Mode', window_name) # 核心切换
    
    tophat_k = cv2.getTrackbarPos('TopHat', window_name)
    thresh_val = cv2.getTrackbarPos('Threshold', window_name)
    erode_iter = cv2.getTrackbarPos('Erode', window_name)
    
    # 1. 放大 (Scale)
    scale = max(1.0, scale_x10 / 10.0)
    h, w = img_bgr.shape[:2]
    img_resized = cv2.resize(img_bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

    # 2. 核心特征提取 (Extraction Strategy)
    if mode == 0:
        # [Mode 0] 饱和度法 (Saturation) - 强力推荐
        # 橙色很鲜艳(S高)，背景很灰(S低)。提取 S 通道能瞬间分离。
        hsv = cv2.cvtColor(img_resized, cv2.COLOR_BGR2HSV)
        _, s, _ = cv2.split(hsv)
        gray = s
        
    elif mode == 1:
        # [Mode 1] 色差法 (Red - Blue)
        # 橙色(R高B低) vs 灰色(R中B中)。相减后橙色亮，灰色暗。
        b, g, r = cv2.split(img_resized)
        gray = cv2.subtract(r, b)
        
    else:
        # [Mode 2] 原始 R+G (备用)
        b, g, r = cv2.split(img_resized)
        gray = cv2.addWeighted(r, 0.6, g, 0.4, 0)

    # 3. 顶帽运算 (TopHat) - 辅助去纹理
    if tophat_k > 0:
        k_size = (tophat_k * 2) + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k_size, k_size))
        gray = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, kernel)
        gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)

    # 4. 双边滤波
    filtered = cv2.bilateralFilter(gray, d=9, sigmaColor=100, sigmaSpace=75)

    # 5. 全局阈值
    _, binary = cv2.threshold(filtered, thresh_val, 255, cv2.THRESH_BINARY)

    # 6. 腐蚀
    if erode_iter > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        binary = cv2.erode(binary, kernel, iterations=erode_iter)

    return binary

def main():
    img = cv2.imread(IMAGE_PATH)
    if img is None:
        print(f"错误：找不到图片 {IMAGE_PATH}")
        return

    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 1000, 800)

    # === 滑块配置 ===
    cv2.createTrackbar('Scale (x10)', window_name, 40, 60, nothing) # 默认 4.0x
    
    # 模式切换: 0=饱和度(推荐), 1=色差(R-B), 2=旧版
    cv2.createTrackbar('Extraction Mode', window_name, 0, 2, nothing) 
    
    # TopHat: 饱和度法通常不需要太大的TopHat，0-5即可
    cv2.createTrackbar('TopHat', window_name, 0, 20, nothing) 
    
    # Threshold: 饱和度提取后，背景通常很黑，阈值可以设低一点 (20-60)
    cv2.createTrackbar('Threshold', window_name, 40, 255, nothing) 
    
    cv2.createTrackbar('Erode', window_name, 0, 3, nothing)

    print("="*40)
    print("【橙色 V2 调试指南】")
    print("1. Extraction Mode: 请优先尝试 [0] (饱和度法)。")
    print("   - 这应该能瞬间把灰背景变黑。")
    print("2. Threshold: 在模式 0 下，试着调整到 30-60 左右。")
    print("3. TopHat: 如果还有一点点背景纹理，轻轻拉一点 (1-3)。")
    print("="*40)

    while True:
        res = processing_pipeline(img)
        cv2.imshow(window_name, res)
        if cv2.waitKey(50) & 0xFF == 27: break
    
    print(f"Mode: {cv2.getTrackbarPos('Extraction Mode', window_name)}")
    print(f"TopHat: {cv2.getTrackbarPos('TopHat', window_name)}")
    print(f"Threshold: {cv2.getTrackbarPos('Threshold', window_name)}")
    print(f"Erode: {cv2.getTrackbarPos('Erode', window_name)}")
    
    cv2.destroyAllWindows()

if __name__ == '__main__':
    main()