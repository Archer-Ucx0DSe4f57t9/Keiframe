# -*- coding: utf-8 -*-
import cv2
import numpy as np

# === 填入截图路径 ===
IMAGE_PATH = 'raw_screenshots/test.png'
# ===================

window_name = 'OCR Tuner V3 (Perfect Ratio)'
MIN_CANVAS_W = 1200  # 画布最小宽度
MIN_CANVAS_H = 800   # 画布最小高度

def nothing(x):
    pass

def processing_pipeline(img_bgr):
    # 获取参数
    preset_mode = cv2.getTrackbarPos('Preset Mode', window_name)
    scale_x10 = cv2.getTrackbarPos('Alg Scale(x10)', window_name)
    
    tophat_k = cv2.getTrackbarPos('TopHat', window_name)
    thresh_val = cv2.getTrackbarPos('Threshold', window_name)
    erode_iter = cv2.getTrackbarPos('Erode', window_name)
    
    # 1. 算法放大 (OCR核心步骤)
    scale = max(1.0, scale_x10 / 10.0)
    h, w = img_bgr.shape[:2]
    img_resized = cv2.resize(img_bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

    # 2. 颜色/特征提取
    b, g, r = cv2.split(img_resized)
    gray = None

    if preset_mode == 0: # 绿字 (ZH)
        gray = cv2.subtract(g, r)
    elif preset_mode == 1: # 蓝字
        gray = b
    elif preset_mode == 2: # 黄字 (R+G)
        gray = cv2.addWeighted(r, 0.5, g, 0.5, 0)
    elif preset_mode == 3: # 橙字 (R-B)
        gray = cv2.subtract(r, b)
    elif preset_mode == 4: # 饱和度
        hsv = cv2.cvtColor(img_resized, cv2.COLOR_BGR2HSV)
        gray = hsv[:,:,1]
    else: # Max
        gray = cv2.max(cv2.max(b, g), r)

    # 3. 顶帽运算
    if tophat_k > 0:
        k_size = (tophat_k * 2) + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k_size, k_size))
        gray = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, kernel)
        gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)

    # 4. 滤波
    filtered = cv2.bilateralFilter(gray, d=9, sigmaColor=100, sigmaSpace=75)

    # 5. 阈值
    _, binary = cv2.threshold(filtered, thresh_val, 255, cv2.THRESH_BINARY)

    # 6. 腐蚀
    if erode_iter > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        binary = cv2.erode(binary, kernel, iterations=erode_iter)

    return binary

def place_image_on_canvas(img):
    """
    将图片居中放置在一个足够大的黑色画布上
    """
    h, w = img.shape[:2]
    
    # 画布大小至少是 MIN_CANVAS，如果图片更大，就跟随图片
    canvas_w = max(MIN_CANVAS_W, w + 50)
    canvas_h = max(MIN_CANVAS_H, h + 50)
    
    # 创建黑色画布 (单通道)
    canvas = np.zeros((canvas_h, canvas_w), dtype=np.uint8)
    
    # 计算居中坐标
    x_offset = (canvas_w - w) // 2
    y_offset = (canvas_h - h) // 2
    
    # 贴图
    canvas[y_offset:y_offset+h, x_offset:x_offset+w] = img
    
    # 画个白框框住图片，方便看清边界
    cv2.rectangle(canvas, (x_offset-1, y_offset-1), (x_offset+w, y_offset+h), (100), 1)
    
    return canvas

def main():
    img = cv2.imread(IMAGE_PATH)
    if img is None:
        print(f"错误：找不到图片 {IMAGE_PATH}")
        return

    # === 关键修正：使用 AUTOSIZE ===
    # 这会强制窗口大小等于我们喂给它的图片大小（也就是画布大小）
    # 从而禁止任何形式的拉伸变形
    cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)

    # === 滑块配置 ===
    cv2.createTrackbar('Preset Mode', window_name, 2, 5, nothing)
    cv2.createTrackbar('Alg Scale(x10)', window_name, 40, 60, nothing)
    
    # 视图缩放：只改变显示大小
    cv2.createTrackbar('View Zoom %', window_name, 100, 200, nothing)

    cv2.createTrackbar('TopHat', window_name, 2, 20, nothing) 
    cv2.createTrackbar('Threshold', window_name, 40, 255, nothing) 
    cv2.createTrackbar('Erode', window_name, 0, 3, nothing)

    print("="*40)
    print("【完美比例调试器 V3】")
    print("1. 窗口永远固定在 1200x800 以上，滑块不会消失。")
    print("2. 图片居中显示，100% 无变形。")
    print("3. 使用 View Zoom 放大缩小看细节。")
    print("="*40)

    while True:
        # 1. 计算OCR结果
        result_img = processing_pipeline(img)
        
        # 2. 处理显示缩放
        view_zoom = max(10, cv2.getTrackbarPos('View Zoom %', window_name)) / 100.0
        h, w = result_img.shape[:2]
        new_w = int(w * view_zoom)
        new_h = int(h * view_zoom)
        
        # 缩放用于显示 (Nearest插值保持像素锐利)
        preview_img = cv2.resize(result_img, (new_w, new_h), interpolation=cv2.INTER_NEAREST)
        
        # 3. 放入画布
        final_display = place_image_on_canvas(preview_img)

        cv2.imshow(window_name, final_display)
        
        if cv2.waitKey(50) & 0xFF == 27: # ESC退出
            break
            
    cv2.destroyAllWindows()

if __name__ == '__main__':
    main()