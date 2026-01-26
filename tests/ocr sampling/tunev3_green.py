# -*- coding: utf-8 -*-
import cv2
import numpy as np

# === 填入你的截图路径 ===
IMAGE_PATH = 'test.png'
# =====================

window_name = 'Ultimate OCR Tuner V3'

def nothing(x):
    pass

def processing_pipeline(img_bgr):
    # === 1. 获取滑块参数 ===
    scale_x10 = cv2.getTrackbarPos('Scale (x10)', window_name)
    color_mode = cv2.getTrackbarPos('Color Mode', window_name) # 新功能：选择颜色策略
    erode_iter = cv2.getTrackbarPos('Erode (Thin)', window_name) # 新功能：把字变细
    
    bilateral_d = cv2.getTrackbarPos('Bilateral d', window_name)
    sigma_color = cv2.getTrackbarPos('SigmaColor', window_name)
    
    thresh_mode = cv2.getTrackbarPos('Thresh Mode', window_name) # 0=Adaptive, 1=Global
    block_size = cv2.getTrackbarPos('BlockSize', window_name)
    c_val = cv2.getTrackbarPos('C / Global Thresh', window_name)

    # === 2. 放大 (Scale) ===
    # 针对"3"这种小字，必须放大，否则根本没有像素空间去展示中间的空隙
    scale = max(1.0, scale_x10 / 10.0)
    h, w = img_bgr.shape[:2]
    img_resized = cv2.resize(img_bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

    # === 3. 颜色分离策略 (核心修正) ===
    b, g, r = cv2.split(img_resized)
    
    if color_mode == 0:
        # [模式0] 默认灰度 (适合黑白字)
        gray = cv2.cvtColor(img_resized, cv2.COLOR_BGR2GRAY)
    
    elif color_mode == 1:
        # [模式1] 绿字专用 (Green - Red)
        # 杀手锏：利用沙子有红色而绿字没红色的特性
        # 结果：沙子变黑，绿字极亮
        gray = cv2.subtract(g, r)
        
    elif color_mode == 2:
        # [模式2] 蓝字/青字专用 (Blue Channel)
        # 那个"3"其实有点偏青色(Cyan)，蓝色通道里它很亮，而黄沙(R+G)在蓝色通道很暗
        gray = b
        
    elif color_mode == 3:
        # [模式3] 高亮滤镜 (Max Channel)
        # 适合黄字、白字
        gray = cv2.max(cv2.max(b, g), r)

    # === 4. 双边滤波 (去噪) ===
    d = max(1, bilateral_d)
    filtered = cv2.bilateralFilter(gray, d=d, sigmaColor=sigma_color, sigmaSpace=75)

    # === 5. 阈值处理 (二值化) ===
    if thresh_mode == 0:
        # 自适应阈值 (应对光照不均)
        bs = block_size
        if bs % 2 == 0: bs += 1
        if bs < 3: bs = 3
        binary = cv2.adaptiveThreshold(filtered, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                     cv2.THRESH_BINARY, bs, c_val)
    else:
        # 全局阈值 (Fixed Threshold)
        # 如果背景已经通过颜色分离变成了纯黑，用这个往往比自适应更干净！
        # 此时 C_val 用作固定阈值 (0-255)
        _, binary = cv2.threshold(filtered, c_val, 255, cv2.THRESH_BINARY)

    # === 6. 腐蚀/削细 (Erode) ===
    # 专门解决“3中间糊成一团黑”的问题
    # 原理：把白色的像素剥掉一层，让字变细，中间的洞就显出来了
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
    # 放大: 必须有，针对"3"这种小字，不放大没法搞
    cv2.createTrackbar('Scale (x10)', window_name, 25, 50, nothing)
    
    # 核心1: 颜色模式。对付绿字，请选 Mode 1 或 2
    cv2.createTrackbar('Color Mode', window_name, 1, 3, nothing) 
    
    # 核心2: 削细。解决"糊成一团"
    cv2.createTrackbar('Erode (Thin)', window_name, 0, 3, nothing)

    # 滤波
    cv2.createTrackbar('Bilateral d', window_name, 9, 30, nothing)
    cv2.createTrackbar('SigmaColor', window_name, 100, 200, nothing)
    
    # 阈值模式: 0=自适应, 1=固定全局
    cv2.createTrackbar('Thresh Mode', window_name, 0, 1, nothing)
    
    # BlockSize (仅自适应模式有效)
    cv2.createTrackbar('BlockSize', window_name, 25, 101, nothing)
    
    # C / Global Thresh: 
    # 在自适应模式下是 C (推荐 5-20)
    # 在固定模式下是 阈值 (推荐 50-150)
    cv2.createTrackbar('C / Global Thresh', window_name, 10, 255, nothing)

    print("="*40)
    print("【调试指南】")
    print("1. Color Mode (颜色模式):")
    print("   - 试着切到 [1] (绿-红) 或 [2] (纯蓝)。")
    print("   - 这通常能瞬间把黄沙背景变黑，把绿字变白。")
    print("2. Thresh Mode (阈值模式):")
    print("   - 如果 Mode 1 背景已经很黑了，切到 [1] (全局阈值)。")
    print("   - 然后调整 'C / Global Thresh' 直到字迹清晰。")
    print("3. Erode (Thin):")
    print("   - 如果'3'中间是黑的，往右拉一格！")
    print("   - 这会把字变细，中间的洞就出来了。")
    print("="*40)

    while True:
        result = processing_pipeline(img)
        cv2.imshow(window_name, result)
        if cv2.waitKey(50) & 0xFF == 27: break
        
    cv2.destroyAllWindows()

if __name__ == '__main__':
    main()