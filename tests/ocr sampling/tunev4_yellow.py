# -*- coding: utf-8 -*-
import cv2
import numpy as np

# === 填入你的截图路径 ===
IMAGE_PATH = 'raw_screenshots/test.png'
# =====================

window_name = 'OCR Tuner V4 - Yellow/Orange Special'

def nothing(x):
    pass

def processing_pipeline(img_bgr):
    # === 1. 获取滑块参数 ===
    scale_x10 = cv2.getTrackbarPos('Scale (x10)', window_name)
    color_mode = cv2.getTrackbarPos('Color Mode', window_name) 
    tophat_k = cv2.getTrackbarPos('TopHat (Extract)', window_name) # 核心功能
    erode_iter = cv2.getTrackbarPos('Erode (Thin)', window_name)
    
    bilateral_d = cv2.getTrackbarPos('Bilateral d', window_name)
    sigma_color = cv2.getTrackbarPos('SigmaColor', window_name)
    
    thresh_mode = cv2.getTrackbarPos('Thresh Mode', window_name) # 0=Adapt, 1=Global
    block_size = cv2.getTrackbarPos('BlockSize', window_name)
    c_val = cv2.getTrackbarPos('C / Threshold', window_name)

    # === 2. 放大 (Scale) ===
    scale = max(1.0, scale_x10 / 10.0)
    h, w = img_bgr.shape[:2]
    img_resized = cv2.resize(img_bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

    # === 3. 颜色策略 (针对黄色优化) ===
    b, g, r = cv2.split(img_resized)
    
    if color_mode == 0:
        # [Mode 0] 标准灰度
        gray = cv2.cvtColor(img_resized, cv2.COLOR_BGR2GRAY)
    
    elif color_mode == 1:
        # [Mode 1] 绿字专用 (Green - Red)
        # 对黄色无效，因为黄色里R很大，减完就黑了
        gray = cv2.subtract(g, r)
        
    elif color_mode == 2:
        # [Mode 2] 蓝字专用 (Blue Channel)
        gray = b
        
    elif color_mode == 3:
        # [Mode 3] 黄色/橙色专用 (R + G 混合)
        # 黄色是红绿混合色，我们将 R 和 G 通道各取50%混合，
        # 这样能最大程度保留黄色的亮度。
        gray = cv2.addWeighted(r, 0.5, g, 0.5, 0)

    elif color_mode == 4:
        # [Mode 4] 最大值 (Max Channel)
        # 简单粗暴，取最亮的那个通道
        gray = cv2.max(cv2.max(b, g), r)

    # === 4. 顶帽运算 (Top-Hat) - 黄色的救星 ===
    # 这一步能把"亮字"从"亮背景"里剥离出来
    if tophat_k > 0:
        # 核大小必须是奇数
        k_size = (tophat_k * 2) + 1 
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k_size, k_size))
        gray = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, kernel)
        # 拉伸对比度，让剥离出来的字更亮
        gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)

    # === 5. 双边滤波 ===
    d = max(1, bilateral_d)
    filtered = cv2.bilateralFilter(gray, d=d, sigmaColor=sigma_color, sigmaSpace=75)

    # === 6. 阈值处理 ===
    if thresh_mode == 0:
        # 自适应
        bs = block_size
        if bs % 2 == 0: bs += 1
        if bs < 3: bs = 3
        binary = cv2.adaptiveThreshold(filtered, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                     cv2.THRESH_BINARY, bs, c_val)
    else:
        # 全局固定
        _, binary = cv2.threshold(filtered, c_val, 255, cv2.THRESH_BINARY)

    # === 7. 腐蚀 ===
    if erode_iter > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        binary = cv2.erode(binary, kernel, iterations=erode_iter)

    return binary

def main():
    img = cv2.imread(IMAGE_PATH)
    if img is None:
        print(f"找不到图片: {IMAGE_PATH}")
        return

    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 1200, 900)

    # === 滑块配置 ===
    cv2.createTrackbar('Scale (x10)', window_name, 40, 60, nothing) # 默认 4.0倍
    
    # 颜色模式: 试试 Mode 3 (R+G) 或 Mode 4 (Max)
    cv2.createTrackbar('Color Mode', window_name, 3, 4, nothing) 
    
    # 【核心】顶帽运算: 这一步决定能不能把黄字抠出来
    cv2.createTrackbar('TopHat (Extract)', window_name, 0, 30, nothing) 
    
    cv2.createTrackbar('Erode (Thin)', window_name, 0, 3, nothing)
    cv2.createTrackbar('Bilateral d', window_name, 9, 30, nothing)
    cv2.createTrackbar('SigmaColor', window_name, 100, 200, nothing)
    
    # 阈值模式
    cv2.createTrackbar('Thresh Mode', window_name, 0, 1, nothing)
    cv2.createTrackbar('BlockSize', window_name, 35, 151, nothing) # 放大4倍后BlockSize要大
    cv2.createTrackbar('C / Threshold', window_name, 10, 255, nothing)

    print("="*40)
    print("【黄色文字调试指南】")
    print("1. Color Mode: 设为 [3] (R+G混合) 或 [4] (Max)。不要用1。")
    print("2. TopHat (Extract): 这是关键！")
    print("   - 慢慢往右拉，直到看到背景变黑，文字浮现。")
    print("   - 典型值: 5 - 15。")
    print("3. C / Threshold:")
    print("   - 如果开了TopHat，背景会很黑，建议切到 [Thresh Mode 1] (全局)。")
    print("   - 然后调整 Threshold 值把字留住。")
    print("="*40)

    while True:
        result = processing_pipeline(img)
        cv2.imshow(window_name, result)
        k = cv2.waitKey(50) & 0xFF
        if k == 27: break
        
    cv2.destroyAllWindows()

if __name__ == '__main__':
    main()