# template_creator.py
import cv2
import numpy as np
import os
import sys

# --- 1. 定义颜色范围 (参考自 malwarfare_map_handler.py 的 __init__ 方法) ---
# 这些范围应根据您的实际截图和需求进行微调
COLOR_RANGES = {
    # 倒计时和暂停的颜色
    'yellow': (np.array([20, 80, 80]), np.array([40, 255, 255])),
    
    # 已净化节点数的颜色 (人族)
    'green': (np.array([60, 70, 70]), np.array([90, 255, 255])),
    
    # 已净化节点数的颜色 (神族)
    'blue': (np.array([100, 100, 100]), np.array([125, 255, 255])),
    
    # 已净化节点数的颜色 (虫族)
    'orange': (np.array([10, 150, 150]), np.array([25, 255, 255])),
}

def generate_template_source(image_path: str, color_key: str, output_dir: str = "template_sources"):
    """
    根据颜色键从输入图像中提取颜色掩膜，并保存为适合制作模板的黑白图像。

    Args:
        image_path: 原始游戏截图的完整路径。
        color_key: 要提取的颜色名称 ('yellow', 'green', 'blue', 'orange')。
        output_dir: 结果图像保存的目录。
    """
    if color_key not in COLOR_RANGES:
        print(f"错误: 颜色键 '{color_key}' 无效。请选择 {list(COLOR_RANGES.keys())}")
        return

    # 1. 读取图像
    img_bgr = cv2.imread(image_path)
    if img_bgr is None:
        print(f"错误: 无法读取图像文件: {image_path}")
        return

    # 2. 转换为 HSV 颜色空间
    img_hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)

    # 3. 应用颜色范围过滤
    lower_bound, upper_bound = COLOR_RANGES[color_key]
    mask = cv2.inRange(img_hsv, lower_bound, upper_bound)
    
    # 4. (可选但推荐) 形态学操作：去除小噪点并连接字符间的微小断裂
    # 使用 3x3 矩形核进行闭运算
    kernel = np.ones((3, 3), np.uint8)
    processed_mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)

    # 5. 准备保存路径和文件名
    os.makedirs(output_dir, exist_ok=True)
    
    # 生成文件名: 例如 "screenshot_green_source.png"
    base_name = os.path.splitext(os.path.basename(image_path))[0]
    output_filename = f"{base_name}_{color_key}_source.png"
    output_path = os.path.join(output_dir, output_filename)

    # 6. 保存图像
    # 我们保存的是掩膜 (目标颜色为白色, 背景为黑色)，直接用于模板制作非常方便
    cv2.imwrite(output_path, processed_mask)
    
    print(f"\n✅ 成功生成模板源图像：")
    print(f"   颜色键: {color_key}")
    print(f"   保存路径: {output_path}")
    print(f"   图像大小: {processed_mask.shape}")
    print("\n💡提示: 您现在可以从生成的图像中裁剪出所需的中文或数字模板。")


if __name__ == '__main__':
    # --- 示例用法 ---
    
    # 假设您的游戏截图名为 'sc2_screenshot.png' 
    # 并且放在脚本的同一目录下
    
    # 注意：请替换为您的实际截图路径
    source_image_path = "sc2_screenshot_zh_example.png"
    
    # 检查示例文件是否存在
    if not os.path.exists(source_image_path):
        print(f"请将您的游戏截图文件重命名为 '{source_image_path}' 并放在脚本目录下，或修改 source_image_path 变量。")
        sys.exit(1)
        
    # --- 运行示例 ---
    
    # 1. 提取绿色（人族）节点数颜色 (用于制作中文“已净化”和数字模板)
    generate_template_source(source_image_path, 'green')

    # 2. 提取黄色（暂停）颜色 (用于制作中文“已暂停”模板)
    generate_template_source(source_image_path, 'yellow')
    
    # 如果您的UI颜色是蓝色或橙色，也可以这样运行：
    # generate_template_source(source_image_path, 'blue')
    # generate_template_source(source_image_path, 'orange')