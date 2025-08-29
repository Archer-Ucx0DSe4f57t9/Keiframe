import os

# 请修改为你的字体模板目录
TEMPLATE_DIR = "ocr_font_dataset"

# 需要检查的字符集合
required_chars = {
    '0': '0', '1': '1', '2': '2', '3': '3', '4': '4',
    '5': '5', '6': '6', '7': '7', '8': '8', '9': '9',
    ':': 'colon'
}

missing = []

for char, folder_name in required_chars.items():
    folder_path = os.path.join(TEMPLATE_DIR, folder_name)
    if not os.path.exists(folder_path):
        missing.append(char)
    else:
        # 检查文件夹下是否至少有一个模板图片
        files = [f for f in os.listdir(folder_path) if f.lower().endswith(('.png', '.jpg'))]
        if len(files) == 0:
            missing.append(char)

if missing:
    print("缺失以下字符模板：", missing)
else:
    print("所有数字和 ':' 模板都存在 ✅")