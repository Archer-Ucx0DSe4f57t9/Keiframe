import cv2
import numpy as np
import os

# ========= 配置 =========
MIN_HEIGHT = 20          # 高度小于该值视为噪点
OUTPUT_DIR = "output_slices"
VALID_EXT = (".png", ".jpg", ".jpeg", ".bmp")
# ========================

os.makedirs(OUTPUT_DIR, exist_ok=True)

def parse_filename(filename: str):
    """
    从  任意-序号-关键字-参数.png
    解析出 关键字, 参数
    """
    name = os.path.splitext(filename)[0]
    parts = name.split("-")
    print(parts)

    if len(parts) < 3:
        raise ValueError(f"文件名格式不符合规则: {filename}")

    # 从右往左取
    param = parts[-1]
    keyword = parts[-2]

    return keyword, param


for file in os.listdir("."):
    if not file.lower().endswith(VALID_EXT):
        continue

    try:
        keyword, param = parse_filename(file)
    except ValueError as e:
        print(e)
        continue

    img = cv2.imread(file, cv2.IMREAD_GRAYSCALE)
    if img is None:
        print(f"跳过无法读取的文件: {file}")
        continue

    # 二值化（假设黑底白图）
    _, binary = cv2.threshold(img, 127, 255, cv2.THRESH_BINARY)

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        binary, connectivity=8
    )

    slice_index = 1

    for i in range(1, num_labels):  # 0 是背景
        x, y, w, h, area = stats[i]

        # 噪点过滤（高度）
        if h < MIN_HEIGHT:
            continue

        slice_img = img[y:y+h, x:x+w]

        out_name = f"{param}_v{slice_index:02d}_{keyword}.png"
        out_path = os.path.join(OUTPUT_DIR, out_name)

        cv2.imwrite(out_path, slice_img)
        slice_index += 1

    print(f"{file} → 切出 {slice_index - 1} 个图形")
