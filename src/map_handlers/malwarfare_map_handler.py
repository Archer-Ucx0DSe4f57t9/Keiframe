# special_handlers/special_map_handler.py
import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
import cv2
import numpy as np
from PIL import Image
import pytesseract
import time
import re
import threading
from concurrent.futures import ThreadPoolExecutor
import config


class MalwarfareMapHandler:
    """
    专用地图处理器：不依赖 current_seconds，
    通过OCR读取屏幕区域文本触发事件；ROI随窗口分辨率自适应。
    """

    # ==== 1) ROI 计算：以 1920x1080 为基准 + 低分辨率纵向修正 ====
    @staticmethod
    def compute_roi(W, H):
        bx0, by0, bx1, by1 = 343, 136, 479, 150  # 1920x1080下的基准框
        sx, sy = W / 1920.0, H / 1080.0

        x0 = int(round(bx0 * sx))
        y0 = int(round(by0 * sy))
        x1 = int(round(bx1 * sx))
        y1 = int(round(by1 * sy))

        if H < 1080:
            dy = int(round(-0.105 * (1080 - H)))  # 经验值：768高度时约-33px
            y0 += dy
            y1 += dy

        return x0, y0, x1, y1

    def __init__(self, table_area, toast_manager, logger,
                 stable_frames=3, min_confidence=60):
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

        # 简单正则：支持 MM:SS 或 “NN秒”
        self.re_time = re.compile(r'(\d{1,2})[:：](\d{2})')
        self.re_seconds = re.compile(r'(\d{1,3})\s*秒')

    def load_map(self, file_path, lines):
        if self.logger:
            self.logger.info(f"SpecialMapHandler load_map: {file_path}")

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

    # ---- 屏幕帧转换为 ndarray(BGR) ----
    def _screen_to_bgr(self, game_screen):
        if isinstance(game_screen, np.ndarray):
            return game_screen
        try:
            from PyQt5.QtGui import QImage, QPixmap
            if isinstance(game_screen, QPixmap):
                image = game_screen.toImage()
            elif isinstance(game_screen, QImage):
                image = game_screen
            else:
                return None
            image = image.convertToFormat(QImage.Format.Format_RGBA8888)
            w, h = image.width(), image.height()
            ptr = image.bits()
            ptr.setsize(image.byteCount())
            arr = np.frombuffer(ptr, np.uint8).reshape((h, w, 4))
            return cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
        except Exception:
            return None

    # ---- 预处理：兼容不同背景（自适应二值 + 反色尝试）----
    def _preprocess_roi_both(self, img_bgr):
        H, W = img_bgr.shape[:2]
        x0, y0, x1, y1 = self.compute_roi(W, H)
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(W-1, x1), min(H-1, y1)
        roi = img_bgr[y0:y1, x0:x1]

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        gray = cv2.medianBlur(gray, 3)

        th = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 11, 2
        )
        th_inv = cv2.bitwise_not(th)
        return th, th_inv, (x0, y0, x1, y1)

    def _ocr_once(self, img):
        # 将两种二值图都试一遍，取更高置信度
        best_text, best_conf = "", 0

        def run_ocr(bin_img):
            config = '--psm 7 -c tessedit_char_whitelist=0123456789:：秒'
            data = pytesseract.image_to_data(
                Image.fromarray(bin_img),
                output_type=pytesseract.Output.DICT,
                config=config, lang='chi_sim+eng'
            )
            text = " ".join([w for w in data['text'] if w.strip()])
            confs = [int(c) for c in data['conf'] if c.strip() and c != '-1']
            conf = int(sum(confs)/len(confs)) if confs else 0
            return text.strip(), conf

        th, th_inv, _ = self._preprocess_roi_both(img)
        t1, c1 = run_ocr(th)
        t2, c2 = run_ocr(th_inv)
        if c1 >= c2:
            best_text, best_conf = t1, c1
        else:
            best_text, best_conf = t2, c2

        return best_text, best_conf

    def _ocr_worker(self, img_bgr):
        try:
            text, conf = self._ocr_once(img_bgr)
            return {"text": text, "conf": conf, "ts": time.time()}
        except Exception as e:
            if self.logger:
                self.logger.error(f"OCR error: {e}")
            return {"text": "", "conf": 0, "ts": time.time()}

    def _parse_text(self, text):
        if not text:
            return None
        m = self.re_time.search(text)
        if m:
            return int(m.group(1))*60 + int(m.group(2))
        m2 = self.re_seconds.search(text)
        if m2:
            return int(m2.group(1))
        return None

    def update_events(self, current_seconds, game_screen):
        if not self._running:
            return

        img = self._screen_to_bgr(game_screen)
        if img is None:
            return

        # 异步 OCR：避免阻塞 UI 线程
        with self._ocr_lock:
            if self._ocr_future is None or self._ocr_future.done():
                self._ocr_future = self._executor.submit(self._ocr_worker, img)

        # 读取结果 + 去抖
        if self._ocr_future is not None and self._ocr_future.done():
            result = self._ocr_future.result()
            if result and result["text"] and result["conf"] >= self.min_confidence:
                self._recent_texts.append(result["text"])
                if len(self._recent_texts) > self.stable_frames:
                    self._recent_texts.pop(0)

                # 连续 stable_frames 帧文本一致才触发
                if len(self._recent_texts) == self.stable_frames and \
                   all(t == self._recent_texts[0] for t in self._recent_texts):
                    seconds = self._parse_text(self._recent_texts[0])
                    if seconds is not None and self.toast_manager:
                        self.toast_manager.show_map_countdown_alert(
                            "special_dynamic_roi",
                            seconds,
                            f"OCR: {self._recent_texts[0]}",
                            None
                        )
