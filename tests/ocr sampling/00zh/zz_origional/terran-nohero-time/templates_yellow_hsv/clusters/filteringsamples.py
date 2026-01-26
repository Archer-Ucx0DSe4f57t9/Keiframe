# -*- coding: utf-8 -*-
import cv2
import numpy as np
import os

# === 配置 ===
INPUT_DIR = 'candidates_2'  # 你的模板文件夹
SIMILARITY_THRESHOLD = 0.95 # 相似度阈值
# ============

def get_roi_rect(img):
    """获取非零像素的最小外接矩形 (裁剪黑边)"""
    points = cv2.findNonZero(img)
    if points is None: return None
    x, y, w, h = cv2.boundingRect(points)
    return (x, y, w, h)

def deduplicate_advanced():
    if not os.path.exists(INPUT_DIR):
        print(f"错误：找不到文件夹 {INPUT_DIR}")
        return

    files = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith('.png')]
    files.sort()
    
    # 1. 读取并预处理
    templates = []
    valid_files = []
    
    print("正在加载模板并分析尺寸...")
    for f in files:
        img = cv2.imread(os.path.join(INPUT_DIR, f), 0)
        if img is None: continue
        
        # 即使是原图，也建议先切掉纯黑边，只比较内容核心
        # 这样能避免因为"多了一行黑边"导致匹配位置偏移
        rect = get_roi_rect(img)
        if rect is None: continue # 全黑图片
        
        # 这里我们可以选择是否真正裁剪，或者保留原图
        # 为了稳妥，我们保留原图，但在比较逻辑里处理
        templates.append(img)
        valid_files.append(f)

    print(f"初始候选: {len(templates)} 个。开始智能去重...")
    
    keep_indices = set(range(len(templates)))
    
    # 2. 两两对比 (大鱼吃小鱼模式)
    for i in range(len(templates)):
        if i not in keep_indices: continue
        
        for j in range(i + 1, len(templates)):
            if j not in keep_indices: continue

            img_a = templates[i]
            img_b = templates[j]
            file_a = valid_files[i]
            file_b = valid_files[j]
            
            # 判断谁大谁小
            h_a, w_a = img_a.shape
            h_b, w_b = img_b.shape
            area_a = h_a * w_a
            area_b = h_b * w_b
            
            # 逻辑：用小的去匹配大的
            if area_a <= area_b:
                small, large = img_a, img_b
                small_idx, large_idx = i, j
                small_name, large_name = file_a, file_b
            else:
                small, large = img_b, img_a
                small_idx, large_idx = j, i
                small_name, large_name = file_b, file_a
            
            # 只有当小图尺寸确实小于等于大图时才能由cv2匹配
            if small.shape[0] > large.shape[0] or small.shape[1] > large.shape[1]:
                # 这种情况极其罕见（比如A高但窄，B矮但宽），直接跳过或者按重合度算
                # 简单处理：跳过
                continue

            # 执行匹配
            res = cv2.matchTemplate(large, small, cv2.TM_CCOEFF_NORMED)
            score = res.max() # 只要能在某个位置重合，就算相似
            
            if score > SIMILARITY_THRESHOLD:
                # 命中！淘汰小的。
                # 原因：大的通常包含了小的（是全集），且保留大图能提供更多背景容错
                print(f"淘汰 {small_name} (被 {large_name} 包含, 相似度 {score:.4f})")
                keep_indices.remove(small_idx)
                
                # 如果淘汰的是外层循环的 i，那就没必要继续拿 i 去比别人了
                if small_idx == i:
                    break

    # 3. 输出结果
    print("="*30)
    final_list = sorted(list(keep_indices))
    print(f"最终保留 {len(final_list)} 个模板：")
    for idx in final_list:
        print(f" -> {valid_files[idx]}")

if __name__ == '__main__':
    deduplicate_advanced()