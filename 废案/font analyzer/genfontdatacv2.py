from PIL import Image, ImageDraw, ImageFont
import os
import numpy as np
import cv2

# 假设你的字体文件路径
FONT_PATH = 'eng.otf' # 请替换为你的字体文件实际路径
FONT_SIZE = 30 # 根据你游戏里字体的大小调整，需要多尝试几次
TEMPLATE_DIR = 'char_templates_generated'

# 需要生成的字符
# 数字 0-9
# 冒号 :
# 斜杠 /
# PAUSED 的所有字母

CHARS_TO_GENERATE = [str(i) for i in range(10)] + [':', '/', 'P', 'A', 'U', 'S', 'E', 'D']

def generate_char_template(char, font_path, font_size, output_dir):
    try:
        font = ImageFont.truetype(font_path, font_size)
    except IOError:
        print(f"Error: Could not load font '{font_path}'. Please check the path.")
        return

    # Pillow 9.0+ 提供了更好的文本尺寸计算方法
    # draw.textbbox((x, y), text, font=font)
    # 它返回 (left, top, right, bottom) 的边界框，是相对于 (x,y) 绘制点的。
    # 为了得到真实尺寸，我们在 (0,0) 处绘制。
    # img = Image.new('L', (1, 1), color=255) # 创建一个足够小的临时图像
    # draw = ImageDraw.Draw(img)
    
    # 获取文本绘制所需的精确边界框
    # textbbox(xy, text, font) 返回 (left, top, right, bottom)
    # 我们将绘制点设为 (0,0) 来获取相对于原点的尺寸
    # 注意：textbbox 的 (left,top) 可能为负值，表示字符从基线左侧或上方开始
    left, top, right, bottom = font.getbbox(char) 

    # 计算文本的实际宽度和高度
    # 宽度是 right - left
    # 高度是 bottom - top
    text_width = right - left
    text_height = bottom - top

    # 增加额外的安全边距，确保不会被裁剪
    # 这个边距很重要，尤其是对于下方被“砍掉”的情况
    extra_padding_x = 4 # 左右额外像素
    extra_padding_y = 6 # 上下额外像素（下方通常需要更多）

    # 最终的图像尺寸
    img_width = text_width + extra_padding_x * 2
    img_height = text_height + extra_padding_y * 2

    # 为了使字符在模板中居中，我们需要调整绘制的起始位置
    # 因为 getbbox 可能会返回负的 left/top
    # 我们需要在 (extra_padding_x - left, extra_padding_y - top) 处绘制
    draw_x = extra_padding_x - left
    draw_y = extra_padding_y - top

    # 创建一个白色背景的图像
    img = Image.new('L', (img_width, img_height), color=255) # L模式是灰度图 (0-255)
    draw = ImageDraw.Draw(img)

    # 在图像上绘制黑色文本
    draw.text((draw_x, draw_y), char, font=font, fill=0) # fill=0 代表黑色

    # 保存模板
    output_filename = f"{char.replace(':', 'colon').replace('/', 'slash')}.png"
    output_path = os.path.join(output_dir, output_filename)
    img.save(output_path)
    print(f"Generated template for '{char}' at {output_path}")
    
    # （可选）显示生成的模板，以便肉眼检查
    # img.show() 

    # 返回 OpenCV 格式的模板（可选，用于测试）
    return cv2.imread(output_path, cv2.IMREAD_GRAYSCALE)

if __name__ == "__main__":
    if not os.path.exists(TEMPLATE_DIR):
        os.makedirs(TEMPLATE_DIR)

    for char in CHARS_TO_GENERATE:
        generate_char_template(char, FONT_PATH, FONT_SIZE, TEMPLATE_DIR)

    print(f"All templates generated in '{TEMPLATE_DIR}'")