import os
import sys
import json
import csv
import cv2
import numpy as np
from PIL import Image

# 替换 pytesseract 为 easyocr
import easyocr 
import traceback

# 假设这些函数/模块在项目中可用
from src.fileutil import get_resources_dir
from src.window_utils import is_game_active 
from src import config 
from src.logging_util import get_logger

logger = get_logger(__name__)

READER = easyocr.Reader(['ch_sim', 'en']) 

def load_enemy_comps():
    """
    读取 resources/enemy_comps 路径下的所有 .txt 配置，并返回字典。
    配置格式：
        第1行：敌方配置名称
        第2-8行：提示信息，格式为 键,值 (例如 t1,雷车)
    """
    comp_configs = {}
    
    # 假设 'resources' 位于项目根目录，且 get_resources_dir 可正确处理
    try:
        enemy_comps_dir = get_resources_dir('enemy_comps')
        if not enemy_comps_dir or not os.path.exists(enemy_comps_dir):
            logger.error(f"资源目录不存在: {enemy_comps_dir}")
            return comp_configs
        
        for filename in os.listdir(enemy_comps_dir):
            if filename.lower().endswith('.csv'):
                file_path = os.path.join(enemy_comps_dir, filename)
                comp_name = os.path.splitext(filename)[0] # 文件名作为字典键

                with open(file_path, 'r', encoding='utf-8') as f:
                    lines = [line.strip() for line in f if line.strip()]

                if not lines:
                    logger.warning(f"配置文件为空: {filename}")
                    continue

                # 第一行是敌方配置名称（OCR匹配目标）
                ocr_targets = lines[0].split(',') # 允许第一行有多列作为匹配目标
                
                # 第 2 行开始是提示信息
                config_data = {'ocr_targets': ocr_targets}
                
                for line in lines[1:]:
                    parts = line.split(',')
                    if len(parts) == 2:
                        key = parts[0].strip().lower() # 键转小写 (t1, t2, ...)
                        value = parts[1].strip()
                        config_data[key] = value
                
                comp_configs[comp_name] = config_data
        
        logger.info(f"成功加载 {len(comp_configs)} 个敌方配置。")
        return comp_configs
        
    except Exception as e:
        logger.error(f"加载敌方配置失败: {e}\n{traceback.format_exc()}")
        return comp_configs


def preprocess_image_for_ocr(cv_image_roi, color_mode):
    """
    使用 OpenCV 对 ROI 图像进行颜色差分增强，返回增强后的灰度图片。
    EasyOCR 更倾向于灰度/彩色图像。
    """
    try:
        if cv_image_roi is None or cv_image_roi.size == 0:
            return None

        # 转换为 HSV 颜色空间
        hsv = cv2.cvtColor(cv_image_roi, cv2.COLOR_BGR2HSV)
        
        # 定义颜色范围，用于提取文字颜色 (假设文字比背景颜色更突出)
        if color_mode == 'Protoss':
            # 蓝色系
            lower = np.array([100, 50, 50])
            upper = np.array([140, 255, 255])
        elif color_mode == 'Zerg':
            # 橙色系
            lower1 = np.array([0, 50, 50])
            upper1 = np.array([20, 255, 255])
            lower2 = np.array([160, 50, 50]) 
            upper2 = np.array([180, 255, 255])
        elif color_mode == 'Terran':
            # 绿色系
            lower = np.array([40, 50, 50])
            upper = np.array([80, 255, 255])
        else:
            # 默认：直接返回灰度图
            return cv2.cvtColor(cv_image_roi, cv2.COLOR_BGR2GRAY)

        # 提取目标颜色
        if color_mode in ('Protoss', 'Terran'):
            mask = cv2.inRange(hsv, lower, upper)
        elif color_mode == 'Zerg':
            mask1 = cv2.inRange(hsv, lower1, upper1)
            mask2 = cv2.inRange(hsv, lower2, upper2)
            mask = mask1 + mask2

        # 增强步骤：将提取的文字颜色作为前景，背景置灰
        
        # 1. 原始灰度图作为基底
        gray_base = cv2.cvtColor(cv_image_roi, cv2.COLOR_BGR2GRAY)
        
        # 2. 将 mask 区域之外的像素全部排除（设为黑色）
        # 使用 mask 对原始图像进行裁剪，只保留目标颜色区域
        isolated_color = cv2.bitwise_and(gray_base, gray_base, mask=mask)
        
        # 3. 如果需要强调文字，可以尝试锐化或提升对比度
        # EasyOCR 通常表现良好，我们直接返回这个增强过的灰度图
        return isolated_color
        
    except Exception as e:
        logger.error(f"图像预处理失败: {e}\n{traceback.format_exc()}")
        return None

def recognize_comp(image_path=None, enemy_race='Protoss'):
    """
    执行截图/加载图片、预处理和 OCR 识别。
    :param image_path: 用于测试的图片路径 (可选)。
    :param enemy_race: 敌方种族，用于颜色预处理。
    :return: 匹配到的配置字典或 None。
    """
    # 1. 加载所有敌方配置 (保持不变)
    enemy_comps = load_enemy_comps()
    if not enemy_comps:
        logger.warning("未加载到敌方配置，跳过识别。")
        return None

    # 2. 截图或加载图片
    try:
        if image_path:
            # 加载用于测试的本地图片
            full_img_pil = Image.open(image_path).convert('RGB')
        else:
            # 调用截图函数（需要确保 SC2 窗口活动）
            if not is_game_active():
                 logger.debug("SC2 游戏未活动，跳过截图。")
                 return None
            
            # 实际截图逻辑（这里假设 get_sc2_window_geometry 包含截图并返回 PIL Image 的逻辑，或需要一个辅助函数）
            # 由于没有完整的截图API，这里简化为：如果无路径，则跳过
            logger.warning("实际截图功能未实现，跳过识别。")
            return None # 实际应用中需要实现截图

        # 3. 图像预处理和裁剪
        
        # 缩放至 1920 宽度
        scale_factor = 1920 / full_img_pil.width
        new_height = int(full_img_pil.height * scale_factor)
        full_img_pil = full_img_pil.resize((1920, new_height), Image.Resampling.LANCZOS)
        
        # 裁剪 ROI
        # 假设 config.ENEMY_COMP_RECOGNIZER_ROI = (x1, y1, x2, y2)
        roi = config.ENEMY_COMP_RECOGNIZER_ROI 
        roi_img_pil = full_img_pil.crop(roi)
        
        # 转换为 OpenCV 格式
        roi_img_cv = cv2.cvtColor(np.array(roi_img_pil), cv2.COLOR_RGB2BGR)

        # 颜色差分增强
        processed_img_cv = preprocess_image_for_ocr(roi_img_cv, enemy_race)
        if processed_img_cv is None:
            return None
        
        # 4. EasyOCR 识别
        
        # 图像预处理（返回增强的灰度图）
        processed_img_cv = preprocess_image_for_ocr(roi_img_cv, enemy_race) 
        if processed_img_cv is None:
            return None
        
        # EasyOCR 识别
        # detail=0 得到纯文本列表，detail=1 得到边界框和置信度 (推荐使用 detail=1 来过滤低置信度结果)
        results = READER.readtext(processed_img_cv, detail=0) 
        
        ocr_result_raw = "".join(results).strip()
        
        ocr_result_cleaned = ocr_result_raw.replace(' ', '').replace('　', '')
        
        # 合并识别结果并取前 30 个字符
        ocr_result = ocr_result_cleaned[:100] 
        
        logger.info(f"EasyOCR 原始结果: {ocr_result}")
        print(f"EasyOCR 原始结果: {ocr_result}")
        
        # 5. 匹配逻辑
        
        for comp_name, comp_data in enemy_comps.items():
            # 匹配逻辑：OCR结果需完整包含配置文件的任意一个匹配目标
            for target_text in comp_data['ocr_targets']:
                if target_text and target_text in ocr_result:
                    logger.info(f"成功匹配到敌方配置: {comp_name}")
                    
                    # 构建输出字典
                    output = {'enemycomp': target_text}
                    for k, v in comp_data.items():
                        if k.startswith('t'): # 只包含 t1, t2, ...
                            output[k] = v
                    return output
        
        logger.warning("OCR 结果未匹配到任何已知敌方配置。")
        return None

    except pytesseract.TesseractNotFoundError:
        logger.error("PyTesseract 未安装或路径错误。")
        return None
    except Exception as e:
        logger.error(f"核心识别函数出错: {e}\n{traceback.format_exc()}")
        return None
      
      
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python enemy_comp_recognizer.py <race_mode> [test_file]")
        print(" race_mode: Protoss, Zerg, Terran")
        sys.exit(1)

    race_mode = sys.argv[1]
    
    # 假设 config.py 中定义了 ENEMY_COMP_RECOGNIZER_ROI = (x, y, x+w, y+h)
    if not hasattr(config, 'ENEMY_COMP_RECOGNIZER_ROI'):
        class MockConfig:
            ENEMY_COMP_RECOGNIZER_ROI = (0, 0, 100, 50) # Mock ROI for testing
        config = MockConfig()
        
    test_file = None
    if len(sys.argv) >= 3:
        test_file_name = sys.argv[2]
        test_file = get_resources_dir('tests', 'samples', test_file_name)
        if not os.path.exists(test_file):
            logger.error(f"测试文件不存在: {test_file}")
            sys.exit(1)

    print(f"\n--- 启动敌方配置识别测试 (Race: {race_mode}) ---")
    result = recognize_comp(image_path=test_file, enemy_race=race_mode)
    print("\n--- 识别结果 ---")
    print(json.dumps(result, ensure_ascii=False, indent=4))
    print("------------------")