import cv2
import numpy as np
import argparse
import os

# --- 从你的主代码中复制过来 ---
# 这里我们硬编码 'count' 区域的基准ROI，请确保它与你config文件中的值一致
# 这是在0偏移状态下的坐标
BASE_COUNT_ROI = (298, 85, 334, 103) 
OCR_SCALE_FACTOR = 2.5
# -----------------------------

def nothing(x):
    pass

def main():
    parser = argparse.ArgumentParser(description="HSV颜色范围实时调节工具")
    parser.add_argument('image_path', type=str, help="要进行颜色提取的图像文件路径。")
    args = parser.parse_args()

    if not os.path.exists(args.image_path):
        print(f"错误: 图像文件未找到: {args.image_path}")
        return

    img_bgr = cv2.imread(args.image_path)
    if img_bgr is None:
        print(f"错误: 无法读取图像: {args.image_path}")
        return
        
    # 提取ROI并放大
    x0, y0, x1, y1 = BASE_COUNT_ROI
    roi_img = img_bgr[y0:y1, x0:x1]
    h, w = roi_img.shape[:2]
    enlarged_roi = cv2.resize(roi_img, (int(w * OCR_SCALE_FACTOR), int(h * OCR_SCALE_FACTOR)), interpolation=cv2.INTER_CUBIC)
    
    # 转换为HSV
    hsv_img = cv2.cvtColor(enlarged_roi, cv2.COLOR_BGR2HSV)

    # 创建一个窗口和6个轨迹条
    cv2.namedWindow("Trackbars")
    cv2.createTrackbar("H_min", "Trackbars", 10, 179, nothing) # 橙色 H 大约在 10-25
    cv2.createTrackbar("S_min", "Trackbars", 150, 255, nothing)
    cv2.createTrackbar("V_min", "Trackbars", 150, 255, nothing)
    cv2.createTrackbar("H_max", "Trackbars", 25, 179, nothing)
    cv2.createTrackbar("S_max", "Trackbars", 255, 255, nothing)
    cv2.createTrackbar("V_max", "Trackbars", 255, 255, nothing)

    print("\n--- HSV 调色板 ---")
    print("实时拖动滑块，观察'Mask'窗口中的效果。")
    print("目标：让白色的数字/字符最清晰、最完整，同时背景的噪点最少。")
    print("完成后，按 'q' 键退出，最终的HSV值将打印在控制台。")

    while True:
        # 读取轨迹条的当前值
        h_min = cv2.getTrackbarPos("H_min", "Trackbars")
        s_min = cv2.getTrackbarPos("S_min", "Trackbars")
        v_min = cv2.getTrackbarPos("V_min", "Trackbars")
        h_max = cv2.getTrackbarPos("H_max", "Trackbars")
        s_max = cv2.getTrackbarPos("S_max", "Trackbars")
        v_max = cv2.getTrackbarPos("V_max", "Trackbars")

        # 根据当前值创建mask
        lower_bound = np.array([h_min, s_min, v_min])
        upper_bound = np.array([h_max, s_max, v_max])
        mask = cv2.inRange(hsv_img, lower_bound, upper_bound)

        # 显示原始ROI和生成的Mask
        cv2.imshow("Original ROI (Enlarged)", enlarged_roi)
        cv2.imshow("Mask", mask)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
            
    cv2.destroyAllWindows()

    print("\n--- 校准完成 ---")
    print("请将以下值复制到你的 MalwarfareMapHandler 的 __init__ 方法中，替换掉旧的 orange_lower/upper 值：")
    print(f"self.orange_lower = np.array([{h_min}, {s_min}, {v_min}])")
    print(f"self.orange_upper = np.array([{h_max}, {s_max}, {v_max}])")


if __name__ == "__main__":
    main()