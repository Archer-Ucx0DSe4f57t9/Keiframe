# -*- coding: utf-8 -*-
import cv2
import numpy as np

# === 填入你的橙色文字原始截图路径 ===
IMAGE_PATH = 'raw_screenshots/orange_test.png'
# ===================================

window_name = 'Orange Text Tuner'

def nothing(x):
    pass

def processing_pipeline(img_bgr):
    scale_x10 = cv2.getTrackbarPos('Scale (x10)', window_name)
    
    # 混合权重
    red_weight = cv2.getTrackbarPos('Red Weight %', window_name) / 100.0
    
    tophat_k = cv2.getTrackbarPos('TopHat', window_name)
    thresh_val = cv2.getTrackbarPos('Threshold', window_name)
    erode_iter = cv2.getTrackbarPos('Erode', window_name)
    
    # 1. 放大
    scale = max(1.0, scale_x10 / 10.0)
    h, w = img_bgr.shape[:2]
    img_resized = cv2.resize(img_bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

    # 2. 颜色混合 (模拟橙色亮度)
    # 橙色 = 红 + 绿。动态调整两者的比例。
    b, g, r = cv2.split(img_resized)
    green_weight = 1.0 - red_weight
    gray = cv2.addWeighted(r, red_weight, g, green_weight, 0)

    # 3. 顶帽运算 (关键去背景步骤)
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
    cv2.createTrackbar('Scale (x10)', window_name, 40, 60, nothing)
    
    # 红色权重: 橙色通常红多绿少。试试 60-80%
    cv2.createTrackbar('Red Weight %', window_name, 60, 100, nothing)
    
    # TopHat: 如果看到背景纹理，拉大这个值！(5-15)
    cv2.createTrackbar('TopHat', window_name, 2, 30, nothing) 
    
    # Threshold: 配合 TopHat 使用。背景黑了以后，找个合适的值把字显出来
    cv2.createTrackbar('Threshold', window_name, 40, 255, nothing)
    
    cv2.createTrackbar('Erode', window_name, 1, 3, nothing)

    print("="*40)
    print("【橙色调试指南】")
    print("1. Red Weight: 保持在 60-70 左右通常比较好。")
    print("2. TopHat: 这是去纹理的主力。往右拉，直到背景变黑。")
    print("3. Threshold: TopHat 拉大后，字可能会变暗，需要把 Threshold 调低一点(比如20-50)。")
    print("="*40)

    while True:
        res = processing_pipeline(img)
        cv2.imshow(window_name, res)
        if cv2.waitKey(50) & 0xFF == 27: break
    
    # 打印最终参数
    print(f"Scale: {cv2.getTrackbarPos('Scale (x10)', window_name)/10}")
    print(f"Red Weight: {cv2.getTrackbarPos('Red Weight %', window_name)/100.0}")
    print(f"TopHat: {cv2.getTrackbarPos('TopHat', window_name)}")
    print(f"Threshold: {cv2.getTrackbarPos('Threshold', window_name)}")
    print(f"Erode: {cv2.getTrackbarPos('Erode', window_name)}")

    cv2.destroyAllWindows()

if __name__ == '__main__':
    main()