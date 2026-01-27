# sc2_ocr.py
# -*- coding: utf-8 -*-
import cv2
import numpy as np
import os,sys

from src import config
from src.fileutil import get_resources_dir
from src.logging_util import get_logger

class SC2OCRProcessor:
    def __init__(self, lang='zh'):
        self.lang = lang
        self.scale_factor = 4.0
        self.templates = {} 
        self.logger = get_logger(__name__)
        self._load_all_templates()

    def _load_all_templates(self):
        # ... (这部分加载代码保持不变，省略以节省空间，直接复用之前的即可) ...
        colors = ['yellow', 'green', 'blue', 'orange']
        self.logger.info(f"=== 初始化 OCR ({self.lang}) ===")
        template_all_dir = get_resources_dir('templates')
        

        for color in colors:
            self.templates[color] = {}

            template_base_dir = os.path.join(template_all_dir, f'{self.lang}_{color}')
            if not os.path.exists(template_base_dir): 
                self.logger.error(f"❌ {color} 的模板目录不存在: {template_base_dir}")
                continue
            
            self.logger.info(f"加载模板目录: {template_base_dir}")
            count = 0
            for fname in os.listdir(template_base_dir):
                if not fname.lower().endswith('.png'): continue
                parts = fname.split('_')
                key = parts[0] # key 是识别结果，如 '0', '5', 'paused', 'c0'

                img_path = os.path.join(template_base_dir, fname)
                templ_img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)

                if templ_img is not None:
                    if key not in self.templates[color]:
                        self.templates[color][key] = []
                    self.templates[color][key].append(templ_img)
                    count += 1
            self.logger.info(f" -> 加载 {color}: {count} 个模板")

    def recognize(self, roi_img, color_type, confidence_thresh=0.7, debug_show=False):
        """
        [升级版] 能够识别多位数 (例如 "2:48") 或 单词 ("paused", "c0")
        逻辑：扫描所有可能的匹配 -> 去重 -> 按X坐标排序 -> 拼接结果
        """
        if roi_img is None or roi_img.size == 0: return None

        params = config.OCR_CONFIG.get(self.lang, {}).get(color_type)
        if not params: return None

        # 1. 预处理
        processed_img = self._preprocess_image(roi_img, params)
        
        if debug_show:
            cv2.imshow(f"Debug Binary ({color_type})", processed_img)

        # 2. 扫描所有模板，收集所有候选结果
        # candidates 结构: [ (score, x, y, w, h, key), ... ]
        candidates = []
        
        color_templates = self.templates.get(color_type, {})
        if not color_templates: return None

        for key, templ_list in color_templates.items():
            for templ in templ_list:
                t_h, t_w = templ.shape[:2]
                
                # 尺寸保护
                if t_h > processed_img.shape[0] or t_w > processed_img.shape[1]:
                    continue

                res = cv2.matchTemplate(processed_img, templ, cv2.TM_CCOEFF_NORMED)
                
                # 获取所有大于阈值的匹配点，而不仅仅是最大值
                locs = np.where(res >= confidence_thresh)
                
                # locs 是 (y_array, x_array)
                for pt in zip(*locs[::-1]): # pt = (x, y)
                    score = res[pt[1], pt[0]]
                    candidates.append((score, pt[0], pt[1], t_w, t_h, key))

        # 3. 非极大值抑制 (NMS) - 去除重叠的匹配
        # 如果两个匹配框重叠严重，只保留分数高的那个
        final_matches = self._nms(candidates, overlap_thresh=0.3)

        # 4. 结果排序与拼接
        if not final_matches:
            return None # 没识别到任何东西

        # 按 X 坐标从左到右排序
        final_matches.sort(key=lambda x: x[1])
        
        # 提取 Key 并拼接
        # 对于数字: "2" + ":" + "4" + "8" -> "2:48"
        # 对于单词: "paused" -> "paused"
        # 对于词组: "c0" -> "c0"
        result_keys = [m[5] for m in final_matches]
        
        # 简单拼接
        return "".join(result_keys)

    def _nms(self, candidates, overlap_thresh=0.3):
        """简单的非极大值抑制，去除重叠检测"""
        if not candidates: return []
        
        # 按分数从高到低排序
        candidates.sort(key=lambda x: x[0], reverse=True)
        
        kept_matches = []
        
        while candidates:
            # 取出最高分的那个
            current = candidates.pop(0)
            kept_matches.append(current)
            
            # 这里的 current: (score, x, y, w, h, key)
            cx, cy, cw, ch = current[1], current[2], current[3], current[4]
            c_area = cw * ch
            
            # 过滤掉剩余列表中与 current 重叠过大的
            remains = []
            for item in candidates:
                ix, iy, iw, ih = item[1], item[2], item[3], item[4]
                
                # 计算重叠区域 IOA (Intersection Over Area)
                xx1 = max(cx, ix)
                yy1 = max(cy, iy)
                xx2 = min(cx + cw, ix + iw)
                yy2 = min(cy + ch, iy + ih)
                
                w = max(0, xx2 - xx1)
                h = max(0, yy2 - yy1)
                inter = w * h
                
                # 如果重叠面积占 较小那个矩形 的比例超过阈值，则认为是同一个物体
                # 或者是包含关系
                min_area = min(c_area, iw * ih)
                overlap_ratio = inter / min_area
                
                if overlap_ratio < overlap_thresh:
                    remains.append(item)
            
            candidates = remains
            
        return kept_matches

    # ... (预处理函数 _preprocess_image 等保持不变，直接复制之前的即可) ...
    def _preprocess_image(self, img, params):
        # 复制之前的 _preprocess_image, _algo_hsv, _algo_channel_diff, _algo_single_channel 代码
        # 务必保留，这里省略是为了让你看清 NMS 逻辑
        method = params['method']
        h, w = img.shape[:2]
        img_resized = cv2.resize(img, (int(w * self.scale_factor), int(h * self.scale_factor)), 
                               interpolation=cv2.INTER_CUBIC)
        
        binary = None
        if method == 'hsv':
            binary = self._algo_hsv(img_resized, params)
        elif method == 'green_minus_red':
            binary = self._algo_channel_diff(img_resized, params, mode='g-r')
        elif method == 'red_minus_blue':
            binary = self._algo_channel_diff(img_resized, params, mode='r-b')
        elif method == 'blue_channel':
            binary = self._algo_single_channel(img_resized, params, channel=0)
        return binary

    def _algo_hsv(self, img, params):
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        lower = np.array([params['h_min'], params['s_min'], params['v_min']])
        upper = np.array([params['h_max'], 255, 255])
        mask = cv2.inRange(hsv, lower, upper)
        _, _, v = cv2.split(hsv)
        gray = cv2.bitwise_and(v, v, mask=mask)
        if cv2.countNonZero(mask) > 0:
            gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
        _, binary = cv2.threshold(gray, params['thresh'], 255, cv2.THRESH_BINARY)
        if params.get('morph_op'):
            op, it = params['morph_op']
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
            binary = cv2.morphologyEx(binary, op, kernel, iterations=it)
        return binary

    def _algo_channel_diff(self, img, params, mode):
        b, g, r = cv2.split(img)
        gray = cv2.subtract(g, r) if mode == 'g-r' else cv2.subtract(r, b)
        if params.get('tophat', 0) > 0:
            k = params['tophat']
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k*2+1, k*2+1))
            gray = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, kernel)
        if params.get('normalize', False):
            gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
        filtered = cv2.bilateralFilter(gray, d=9, sigmaColor=100, sigmaSpace=75)
        _, binary = cv2.threshold(filtered, params['thresh'], 255, cv2.THRESH_BINARY)
        if params.get('morph_op'):
            op, it = params['morph_op']
            k_size = 3 if op == cv2.MORPH_OPEN else 2
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k_size, k_size))
            binary = cv2.morphologyEx(binary, op, kernel, iterations=it)
        return binary

    def _algo_single_channel(self, img, params, channel):
        gray = cv2.split(img)[channel]
        if params.get('tophat', 0) > 0:
            k = params['tophat']
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k*2+1, k*2+1))
            gray = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, kernel)
            gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
        filtered = cv2.bilateralFilter(gray, d=9, sigmaColor=100, sigmaSpace=75)
        _, binary = cv2.threshold(filtered, params['thresh'], 255, cv2.THRESH_BINARY)
        if params.get('morph_op'):
            op, it = params['morph_op']
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
            binary = cv2.morphologyEx(binary, op, kernel, iterations=it)
        return binary