# debug_ocr_scan_dir.py
# -*- coding: utf-8 -*-
import cv2
import os
import sys

#导入模块
from src.map_handlers.malwarfate_ocr_processor import MalwarfareOcrProcessor

# ==============================
# 1. 核心路径修正 (Path Patching)
# ==============================
# 获取当前脚本所在目录 (即 project/tests/)
current_test_dir = os.path.dirname(os.path.abspath(__file__))

# ==============================
# 2. 默认配置修正
# ==============================
# 默认指向: tests/ocr sampling/00zh
DEFAULT_DIR = os.path.join(current_test_dir, 'samples', '00zh')
#DEFAULT_DIR = os.path.join(current_test_dir, 'samples', '01en')
DEFAULT_LANG = 'zh'
DEFAULT_COLOR = 'blue'

def main():
    # 打印当前工作环境信息
    print(f"工作目录: {os.getcwd()}")
    print(f"脚本位置: {current_test_dir}")
    print("-" * 50)

    # 1. 获取参数
    # 显示默认路径给用户看
    target_dir = DEFAULT_DIR
    lang = DEFAULT_LANG
    
    print("\n请选择识别颜色:")
    print("1: yellow (System/Time/Paused)")
    print("2: green  (Terran/Player)")
    print("3: blue   (Protoss/Shield)")
    print("4: orange (Zerg/HP)")
    choice = input(f"输入序号或名称 (默认 {DEFAULT_COLOR}): ").strip().lower()
    
    color_map = {'1': 'yellow', '2': 'green', '3': 'blue', '4': 'orange'}
    color_type = color_map.get(choice, choice)
    if not color_type: color_type = DEFAULT_COLOR
    target_dir = os.path.join(target_dir, color_type)


    # 2. 初始化
    print(f"\n正在初始化 OCR [{lang}]...")
    try:
        # 注意：SC2OCRProcessor 内部加载模板是基于 config.py 的
        # 请确保 config.py 里的 TEMPLATE_BASE_DIR 路径是正确的
        # 如果 config.py 在 src/map_handlers，且模板在 tests/../templates
        # 可能需要去 config.py 里调整一下 TEMPLATE_BASE_DIR 为绝对路径或者基于项目根目录的路径
        processor = MalwarfareOcrProcessor(lang=lang)
    except Exception as e:
        print(f"初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return

    if not os.path.exists(target_dir):
        print(f"错误：找不到目录 {target_dir}")
        return

    files = [f for f in os.listdir(target_dir) if f.lower().endswith(('.png', '.jpg', '.bmp'))]
    files.sort()
    
    if not files:
        print(target_dir)
        print("目录中没有图片。")
        return

    print(f"\n开始批量扫描 {len(files)} 张图片，颜色模式: [{color_type}]...")
    print("="*50)
    print(f"{'文件名':<30} | {'识别结果':<15}")
    print("-" * 50)

    # 3. 批量执行
    count = 0
    for fname in files:
        img_path = os.path.join(target_dir, fname)
        # 支持中文路径读取
        img = cv2.imdecode(np.fromfile(img_path, dtype=np.uint8), cv2.IMREAD_COLOR)
        
        if img is None: 
            print(f"[警告] 无法读取: {fname}")
            continue
        
        # === 核心调用 ===
        try:
            result_str = processor.recognize(img, color_type, debug_show=False)
            display_res = result_str if result_str else "[无结果]"
            print(f"{fname:<30} | {display_res:<15}")
        except Exception as e:
            print(f"{fname:<30} | [Error: {str(e)}]")
            
        count += 1

    print("="*50)
    print(f"完成！共处理 {count} 张图片。")

# 补充: 处理中文路径读取问题所需的 numpy 引用
import numpy as np

if __name__ == '__main__':
    main()