# -*- coding: utf-8 -*-
import cv2
import numpy as np

# === 填入你的蓝色文字原始截图路径 ===
IMAGE_PATH = 'raw_screenshots/blue_test.png'
# =================================

window_name = 'Blue Text Tuner'

def nothing(x):
    pass

def processing_pipeline(img_bgr):
    # === 获取滑块参数 ===
    scale_x10 = cv2.getTrackbarPos('Scale (x10)', window_name)
    thresh_val = cv2.getTrackbarPos('Threshold', window_name)
    tophat_k = cv2.getTrackbarPos('TopHat', window_name) # 新增：压制纹理神器
    erode_iter = cv2.getTrackbarPos('Erode', window_name)
    
    # 1. 放大
    scale = max(1.0, scale_x10 / 10.0)
    h, w = img_bgr.shape[:2]
    img_resized = cv2.resize(img_bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

    # 2. 颜色分离 (Blue Channel)
    # 蓝色文字的核心特征是 B 通道极亮
    b, g, r = cv2.split(img_resized)
    gray = b

    # 3. 顶帽运算 (去除背景纹理)
    if tophat_k > 0:
        k_size = (tophat_k * 2) + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k_size, k_size))
        gray = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, kernel)
        gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)

    # 4. 双边滤波 (去噪)
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
    cv2.createTrackbar('Scale (x10)', window_name, 40, 60, nothing) # 默认4倍
    
    # TopHat: 如果背景有纹理，试着拉到 1-5
    cv2.createTrackbar('TopHat', window_name, 0, 20, nothing) 
    
    # Threshold: 这是关键！背景有纹理说明这个值太低了。试着拉到 80-150
    cv2.createTrackbar('Threshold', window_name, 100, 255, nothing) 
    
    cv2.createTrackbar('Erode', window_name, 1, 3, nothing)

    print("="*40)
    print("【蓝色调试指南】")
    print("1. 背景有纹理？ -> 往右拉 'Threshold'。")
    print("2. 字断了？ -> 往右拉一点 'TopHat'，或者把 Threshold 调低一点。")
    print("="*40)

    while True:
        res = processing_pipeline(img)
        cv2.imshow(window_name, res)
        if cv2.waitKey(50) & 0xFF == 27: break
    
    # 打印最终参数
    print(f"Scale: {cv2.getTrackbarPos('Scale (x10)', window_name)/10}")
    print(f"TopHat: {cv2.getTrackbarPos('TopHat', window_name)}")
    print(f"Threshold: {cv2.getTrackbarPos('Threshold', window_name)}")
    print(f"Erode: {cv2.getTrackbarPos('Erode', window_name)}")
    cv2.destroyAllWindows()

if __name__ == '__main__':
    main()