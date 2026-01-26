# -*- coding: utf-8 -*-
import cv2
import numpy as np

# === 这里填入包含 2:48 的截图 ===
IMAGE_PATH = 'raw_screenshots/test.png' 
# ==============================

window_name = 'Yellow HSV Filter Tuner'

def nothing(x):
    pass

def processing_pipeline(img_bgr):
    # 1. 获取滑块参数
    scale_x10 = cv2.getTrackbarPos('Scale (x10)', window_name)
    
    # HSV 核心参数 (颜色范围)
    h_min = cv2.getTrackbarPos('H Min', window_name)
    h_max = cv2.getTrackbarPos('H Max', window_name)
    s_min = cv2.getTrackbarPos('S Min', window_name)
    v_min = cv2.getTrackbarPos('V Min', window_name)
    
    # 后期处理参数
    thresh = cv2.getTrackbarPos('Threshold', window_name)
    morph_k = cv2.getTrackbarPos('Close Kernel', window_name)

    # --- 处理流程 ---
    
    # A. 放大 (保持 4 倍)
    scale = max(1.0, scale_x10 / 10.0)
    h_img, w_img = img_bgr.shape[:2]
    img_resized = cv2.resize(img_bgr, (int(w_img * scale), int(h_img * scale)), interpolation=cv2.INTER_CUBIC)

    # B. 转到 HSV 空间
    hsv = cv2.cvtColor(img_resized, cv2.COLOR_BGR2HSV)

    # C. 创建颜色掩膜 (Color Mask)
    # OpenCV HSV范围: H(0-180), S(0-255), V(0-255)
    # 黄色通常在 H=20~35 之间
    lower_yellow = np.array([h_min, s_min, v_min])
    upper_yellow = np.array([h_max, 255, 255])
    
    mask = cv2.inRange(hsv, lower_yellow, upper_yellow)

    # D. 提取亮度层 (Value Channel) 作为文字骨架
    # 我们不直接用 mask 做字，因为 mask 边缘太硬。
    # 我们用 mask 把 V 通道里的背景抠掉，只留下黄色的 V 通道。
    _, _, v_channel = cv2.split(hsv)
    filtered_gray = cv2.bitwise_and(v_channel, v_channel, mask=mask)

    # E. 归一化 (拉伸对比度)
    # 因为背景被 mask 变成了纯黑(0)，现在拉伸只会增强文字
    if cv2.countNonZero(mask) > 0: # 防止全黑报错
        filtered_gray = cv2.normalize(filtered_gray, None, 0, 255, cv2.NORM_MINMAX)

    # F. 全局阈值
    # 由于背景已经通过 HSV 过滤得很干净，这里的阈值可以设得很低！
    _, binary = cv2.threshold(filtered_gray, thresh, 255, cv2.THRESH_BINARY)

    # G. 闭运算 (防断裂)
    if morph_k > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (morph_k, morph_k))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

    return binary

def main():
    img = cv2.imread(IMAGE_PATH)
    if img is None:
        print(f"错误：找不到图片 {IMAGE_PATH}")
        return

    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 1000, 800)

    # === 滑块配置 ===
    cv2.createTrackbar('Scale (x10)', window_name, 40, 60, nothing) # 4.0x
    
    # HSV 范围 (黄色预设)
    # H: 色相 (黄色大约在 20-35)
    cv2.createTrackbar('H Min', window_name, 20, 180, nothing) 
    cv2.createTrackbar('H Max', window_name, 35, 180, nothing)
    
    # S: 饱和度 (文字通常比背景饱和度高)
    cv2.createTrackbar('S Min', window_name, 50, 255, nothing)
    
    # V: 亮度 (文字很亮)
    cv2.createTrackbar('V Min', window_name, 50, 255, nothing)

    # 后处理
    # 这里的阈值是关键：因为背景被HSV清除了，试着把这个降到 10-30！
    cv2.createTrackbar('Threshold', window_name, 20, 255, nothing) 
    
    # 闭运算核大小 (0=关, 2=2x2, 3=3x3)
    cv2.createTrackbar('Close Kernel', window_name, 0, 5, nothing)

    print("="*40)
    print("【HSV 调试指南】")
    print("1. 调节 H Min/H Max: 只要把'黄色'留住，把旁边的'绿色'和'褐色'滤掉。")
    print("2. 调节 S Min: 往右拉，去除灰白色的噪点。")
    print("3. Threshold: 这是一个大招。一旦背景变黑，把 Threshold 拉到极低(比如 5-20)，笔画就全连上了！")
    print("4. Close Kernel: 如果还断，试试设为 2 或 3。")
    print("="*40)

    while True:
        res = processing_pipeline(img)
        cv2.imshow(window_name, res)
        if cv2.waitKey(50) & 0xFF == 27: break
    
    # 打印最终参数
    print(f"H Range: {cv2.getTrackbarPos('H Min', window_name)} - {cv2.getTrackbarPos('H Max', window_name)}")
    print(f"S Min: {cv2.getTrackbarPos('S Min', window_name)}")
    print(f"V Min: {cv2.getTrackbarPos('V Min', window_name)}")
    print(f"Threshold: {cv2.getTrackbarPos('Threshold', window_name)}")
    print(f"Close Kernel: {cv2.getTrackbarPos('Close Kernel', window_name)}")
    
    cv2.destroyAllWindows()

if __name__ == '__main__':
    main()