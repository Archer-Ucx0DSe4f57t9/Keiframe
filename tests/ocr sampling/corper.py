import os
from PIL import Image

def batch_crop_images(left, top, right, bottom):
    """
    裁剪当前目录下所有图片并保存。
    坐标系说明: (0,0) 为图片左上角。
    
    :param left: 左上角 X 坐标 (x1)
    :param top: 左上角 Y 坐标 (y1)
    :param right: 右下角 X 坐标 (x2)
    :param bottom: 右下角 Y 坐标 (y2)
    """
    
    # 支持的图片格式 (可根据需要添加)
    valid_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp')
    
    # 获取当前工作目录
    current_dir = os.getcwd()
    print(f"📂 正在处理目录: {current_dir}")
    print(f"✂️  裁剪区域: ({left}, {top}) 到 ({right}, {bottom})")
    print("-" * 30)

    count = 0
    
    # 遍历当前目录下的所有文件
    for filename in os.listdir(current_dir):
        # 1. 检查是否为图片格式 (忽略大小写)
        if filename.lower().endswith(valid_extensions):
            
            # 2. 防止重复处理已经处理过的图片
            if "_edited" in filename:
                continue

            try:
                original_path = os.path.join(current_dir, filename)
                
                # 打开图片
                with Image.open(original_path) as img:
                    # PIL 的 crop 方法接收一个元组: (left, top, right, bottom)
                    # 对应: (左上x, 左上y, 右下x, 右下y)
                    cropped_img = img.crop((left, top, right, bottom))
                    
                    # 构造新文件名
                    file_name_no_ext, file_ext = os.path.splitext(filename)
                    new_filename = f"{file_name_no_ext}_edited{file_ext}"
                    new_path = os.path.join(current_dir, new_filename)
                    
                    # 保存图片
                    cropped_img.save(new_path)
                    print(f"✅ 成功: {filename} -> {new_filename}")
                    count += 1
                    
            except Exception as e:
                print(f"❌ 失败: {filename} - 错误信息: {e}")

    print("-" * 30)
    print(f"🎉 处理完成，共裁剪了 {count} 张图片。")

if __name__ == "__main__":
    # ================= 配置区域 =================
    # 请在这里输入你的坐标数值
    
    X1 = 100  # 左上角 X (Left)
    Y1 = 100  # 左上角 Y (Top)
    X2 = 500  # 右下角 X (Right)
    Y2 = 500  # 右下角 Y (Bottom)
    
    # ===========================================
    
    batch_crop_images(X1, Y1, X2, Y2)