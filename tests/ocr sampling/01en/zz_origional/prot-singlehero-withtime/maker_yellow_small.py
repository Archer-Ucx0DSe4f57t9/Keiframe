# -*- coding: utf-8 -*-
import cv2
import numpy as np
import os

# === 黄色文字 (HSV Mode) 专用制作脚本 ===
INPUT_DIR = 'raw_screenshots'
OUTPUT_DIR = 'templates_yellow_hsv'

# === 你验证过的参数 ===
SCALE_FACTOR = 4.0

# HSV 核心参数 (基于 Tuner 默认值)
H_MIN = 28
H_MAX = 35
S_MIN = 50
V_MIN = 50

# 你调整后的关键阈值
GLOBAL_THRESH = 110 

# 形态学参数 (Tuner 默认为 0，如需闭运算防断裂可改为 2 或 3)
CLOSE_KERNEL_SIZE = 0 

def preprocess_yellow_hsv(img_bgr):
    if img_bgr is None: return None

    # 1. 放大
    h, w = img_bgr.shape[:2]
    img_resized = cv2.resize(img_bgr, (int(w * SCALE_FACTOR), int(h * SCALE_FACTOR)), interpolation=cv2.INTER_CUBIC)

    # 2. 转到 HSV 空间
    hsv = cv2.cvtColor(img_resized, cv2.COLOR_BGR2HSV)

    # 3. 创建颜色掩膜 (Color Mask)
    # 只保留 H(20-35), S(>50), V(>50) 的像素
    lower_yellow = np.array([H_MIN, S_MIN, V_MIN])
    upper_yellow = np.array([H_MAX, 255, 255])
    mask = cv2.inRange(hsv, lower_yellow, upper_yellow)

    # 4. 提取亮度层 (Value Channel)
    # 利用 mask 把背景扣掉，只留下文字的亮度信息
    _, _, v_channel = cv2.split(hsv)
    filtered_gray = cv2.bitwise_and(v_channel, v_channel, mask=mask)

    # 5. 归一化 (Normalize)
    # 这一步至关重要！把过滤后的文字亮度拉满到 255
    if cv2.countNonZero(mask) > 0:
        filtered_gray = cv2.normalize(filtered_gray, None, 0, 255, cv2.NORM_MINMAX)

    # 6. 全局阈值 (User: 110)
    _, binary = cv2.threshold(filtered_gray, GLOBAL_THRESH, 255, cv2.THRESH_BINARY)

    # 7. 闭运算 (可选，用于缝合断裂)
    if CLOSE_KERNEL_SIZE > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (CLOSE_KERNEL_SIZE, CLOSE_KERNEL_SIZE))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

    return binary

def main():
    if not os.path.exists(INPUT_DIR):
        print(f"错误：找不到文件夹 '{INPUT_DIR}'")
        return
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    files = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith(('.png', '.jpg'))]
    print(f"开始处理 {len(files)} 张图片 (黄色 HSV 模式)...")
    print(f"参数: H[{H_MIN}-{H_MAX}], Thresh={GLOBAL_THRESH}")

    for filename in files:
        img = cv2.imread(os.path.join(INPUT_DIR, filename))
        if img is None: continue
        
        # 建议：如果是处理原始大图，可以在这里加个简单的 ROI 裁剪
        # 比如：img = img[0:100, 1000:1500] 
        # 这样能避免全图噪点干扰 Normalize 的效果
        
        result = preprocess_yellow_hsv(img)
        
        if result is not None:
            out_path = os.path.join(OUTPUT_DIR, 'yellow_hsv_' + filename)
            cv2.imwrite(out_path, result)
            print(f"已保存: {out_path}")

    print("完成！请检查 templates_yellow_hsv 文件夹。")

if __name__ == '__main__':
    main()