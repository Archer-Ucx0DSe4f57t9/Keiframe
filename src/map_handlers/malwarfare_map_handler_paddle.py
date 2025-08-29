# map_handlers/malwarfare_map_handler.py
import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
import window_utils
from window_utils import get_sc2_window_geometry
import cv2
import numpy as np
from PIL import Image
import pytesseract
import time
import re
import threading
from concurrent.futures import ThreadPoolExecutor
import config
from paddleocr import PaddleOCR
import time
import cv2


# ---- 正则模式（容错 OCR 错别字） ----
zh_time_pattern = re.compile(
    r"净化5个安全终端\((\d)/5\)\s*\(在(\d{1,2}:\d{2})后净化\)"
)
zh_pause_pattern = re.compile(
    r"净化5个安全终端\((\d)/5\)\s*\(暂停\)"
)

# 英文正则放宽，避免 OCR 拼写错误卡死
en_time_pattern = re.compile(
    r"Purify\s+5\s+\w*Terminals\((\d)/5\)\s*\(.*?(\d{1,2}:\d{2})\)",
    re.IGNORECASE,
)
en_pause_pattern = re.compile(
    r"Purify\s+5\s+\w*Terminals\((\d)/5\)\s*Purified\s*\(PAUSED\)",
    re.IGNORECASE,
)

# ---- OCR 文本规范化 ----
def normalize_text(text: str) -> str:
    replacements = {
        "secruity": "security",
        "Secruity": "Security",
        "pruified": "Purified",
        "Pruified": "Purified",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text.strip()


def parse_text(ocr_text: str, logger=None):
    """解析 OCR 文本，返回结构化结果，如果失败打印调试日志"""
    text = normalize_text(ocr_text)

    m = zh_time_pattern.fullmatch(text)
    if m:
        return {"lang": "zh", "n": int(m.group(1)), "time": m.group(2)}

    m = zh_pause_pattern.fullmatch(text)
    if m:
        return {"lang": "zh", "n": int(m.group(1)), "time": "暂停"}

    m = en_time_pattern.fullmatch(text)
    if m:
        return {"lang": "en", "n": int(m.group(1)), "time": m.group(2)}

    m = en_pause_pattern.fullmatch(text)
    if m:
        return {"lang": "en", "n": int(m.group(1)), "time": "PAUSED"}

    # ---- 如果没匹配成功，打印调试信息 ----
    if logger:
        logger.warning(f"[parse_text] 未匹配 OCR 文本: '{ocr_text}' → 规范化后: '{text}'")
    else:
        print(f"[parse_text] 未匹配 OCR 文本: '{ocr_text}' → 规范化后: '{text}'")

    return None

def compute_dynamic_roi(W, H, margin_x=5, margin_y=8):
    """
    根据窗口分辨率计算 ROI 区域 (x0,y0,x1,y1)
    1920x1080 基准，低分辨率时修正 y0
    """
    # 基准比例
    x0 = int(0.034 * W)
    w  = int(0.216 * W)
    y0 = int(0.125 * H if H >= 1080 else 0.083 * H)
    h  = int(0.015 * H)

    # 留边容错
    x0 = max(0, x0 - margin_x)
    y0 = max(0, y0 - margin_y)
    w  = min(W - x0, w + 2*margin_x)
    h  = min(H - y0, h + 2*margin_y)

    return x0, y0, x0+w, y0+h


class MalwarfareMapHandler:
    """
    只处理一个特殊地图，通过 OCR + 正则解析文本:
      - 净化5个安全终端({n}/5) (在{m:ss}后净化)
      - 净化5个安全终端({n}/5) (暂停)
      - Purify 5 Security Terminals({n}/5) (Purified in {m:ss})
      - Purify 5 Security Terminals({n}/5) Purified (PAUSED)
    """

    def __init__(self, table_area, toast_manager, logger,
                 stable_frames=2, min_confidence=50, use_gpu=True):
        self.table_area = table_area
        self.toast_manager = toast_manager
        self.logger = logger
        self.stable_frames = stable_frames
        self.min_confidence = min_confidence

        self._executor = ThreadPoolExecutor(max_workers=1)
        self._ocr_future = None
        self._ocr_lock = threading.Lock()
        self._recent_texts = []
        self._running = True
        try:
            self._ocr = PaddleOCR(
                use_angle_cls=True,
                lang="en",
                use_gpu=use_gpu
            )
            print("[DEBUG] PaddleOCR 初始化成功")
        except Exception as e:
            self._ocr = None
            print("[DEBUG] PaddleOCR 初始化失败:", e)

        # --------- PaddleOCR 初始化（只加载一次） ---------
        try:
            self._ocr = PaddleOCR(
                use_angle_cls=True,
                lang="en",        # 只识别英文和数字，速度快
                #use_gpu=use_gpu   # 如果有 GPU，可以 True
            )
            if self.logger:
                self.logger.info("PaddleOCR initialized.")
        except Exception as e:
            self._ocr = None
            if self.logger:
                self.logger.error(f"Failed to initialize PaddleOCR: {e}")
        # ------------------------------------------------


    def load_map(self, file_path, lines):
        if self.logger:
            self.logger.info(f"MalwarfareMapHandler load_map: {file_path}")

    def cleanup(self):
        self.hide_all_alerts()
        self._running = False
        try:
            self._executor.shutdown(wait=False)
        except Exception:
            pass

    def hide_all_alerts(self):
        try:
            if self.toast_manager:
                self.toast_manager.hide_toast()
        except Exception:
            pass

    # ---- OCR ----
    def _ocr_once(self, img_bgr, roi):
        if self._ocr is None:
            print("[DEBUG] OCR 引擎未初始化")
            return ""

        x0, y0, x1, y1 = roi
        roi_img = img_bgr[y0:y1, x0:x1]
        print("[DEBUG] ROI shape:", roi_img.shape if roi_img is not None else None)

        if roi_img is None or roi_img.size == 0:
            print("[DEBUG] ROI 区域为空")
            return ""
        
        """ 对 ROI 使用 PaddleOCR 识别 """
        if self._ocr is None:
            return ""

        x0, y0, x1, y1 = roi
        roi_img = img_bgr[y0:y1, x0:x1]

        t0 = time.time()
        try:
            # --- 预处理 ---
            gray = cv2.cvtColor(roi_img, cv2.COLOR_BGR2GRAY)
            gray = cv2.resize(gray, None, fx=2.0, fy=2.0,
                              interpolation=cv2.INTER_CUBIC)
            # 转回 RGB，因为 OCR 要 RGB 格式
            proc = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)

            # --- OCR 调用 ---
            result = self._ocr.ocr(proc, cls=True)

            # 提取文本
            texts = []
            if result and len(result) > 0:
                for line in result[0]:
                    txt = line[1][0].strip()
                    if txt:
                        texts.append(txt)
            text = " ".join(texts)

            elapsed = time.time() - t0
            if self.logger:
                self.logger.debug(f"PaddleOCR elapsed {elapsed:.3f}s, text='{text}'")
            return text
        except Exception as e:
            if self.logger:
                self.logger.error(f"OCR error: {e}")
            return ""

    def _ocr_worker(self, img_bgr, roi):
        try:
            text = self._ocr_once(img_bgr, roi)
            return {"text": text, "ts": time.time()}
        except Exception as e:
            if self.logger:
                self.logger.error(f"OCR worker exception: {e}")
            return {"text": "", "ts": time.time()}

    # ---- 主接口 ----
    def update_events(self, current_seconds, game_screen):
        if not self._running:
            return None

        # 获取 SC2 窗口尺寸
        sc2_rect = get_sc2_window_geometry()
        if not sc2_rect:
            return None
        _, _, w, h = sc2_rect

        roi = compute_dynamic_roi(w, h, margin_x=5, margin_y=8)

        img = game_screen
        if img is None:
            return None

        # 提交 OCR 异步任务
        with self._ocr_lock:
            if self._ocr_future is None or self._ocr_future.done():
                self._ocr_future = self._executor.submit(self._ocr_worker, img, roi)

        # 取结果并解析
        if self._ocr_future is not None and self._ocr_future.done():
            result = self._ocr_future.result()
            if result and result["text"]:
                self._recent_texts.append(result["text"])
                if len(self._recent_texts) > self.stable_frames:
                    self._recent_texts.pop(0)

                if len(self._recent_texts) == self.stable_frames and \
                   all(t == self._recent_texts[0] for t in self._recent_texts):
                    parsed = parse_text(self._recent_texts[0])
                    if parsed and self.toast_manager:
                        self.toast_manager.show_simple_toast(str(parsed))
                    return parsed
        return None
