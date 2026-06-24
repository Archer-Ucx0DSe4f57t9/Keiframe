# -*- coding: utf-8 -*-
"""
Cradle of Death countdown recognizer.

Recognizes the fixed m:ss countdown shown in the upper-right objective panel.
Only the three white digit slots are matched; the colon region is skipped.
This module is intentionally standalone and does not read global state, start
threads, show UI, or trigger notifications.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from src.game_readers.white_supply_recognizer import WhiteSupplyRecognizer
from src.utils.fileutil import get_project_root
from src.utils.logging_util import get_logger


Slot = Tuple[int, int, int, int]
Roi = Tuple[int, int, int, int]


@dataclass(frozen=True)
class CradleCountdownConfig:
    # Coordinates are based on the shared 2560x1440 screenshot:
    # tests/screenshot_2026-06-23_23-33-29.png
    base_screen_size: Tuple[int, int] = (2560, 1440)
    roi: Roi = (2338, 188, 58, 22)
    digit_slots: Tuple[Slot, Slot, Slot] = (
        (0, 0, 20, 22),    # minute
        (25, 0, 18, 22),   # second tens
        (43, 0, 15, 22),   # second ones
    )
    slot_names: Tuple[str, str, str] = ("minute", "second_tens", "second_ones")

    template_scale: int = 4
    normalize_roi_to_base_size: bool = True
    match_threshold: float = 0.55

    # Same defaults as WhiteSupplyRecognizer's verified white text pipeline.
    white_gray_min: int = WhiteSupplyRecognizer.WHITE_GRAY_MIN
    white_rgb_min: int = WhiteSupplyRecognizer.WHITE_RGB_MIN
    white_rgb_delta_max: int = WhiteSupplyRecognizer.WHITE_RGB_DELTA_MAX
    white_percentile: int = WhiteSupplyRecognizer.WHITE_PERCENTILE
    white_use_percentile: bool = WhiteSupplyRecognizer.WHITE_USE_PERCENTILE
    white_blur_ksize: int = WhiteSupplyRecognizer.WHITE_BLUR_KSIZE
    white_dilate_iter: int = WhiteSupplyRecognizer.WHITE_DILATE_ITER
    white_erode_iter: int = WhiteSupplyRecognizer.WHITE_ERODE_ITER


@dataclass
class DigitSlotMatch:
    slot_name: str
    digit: Optional[str]
    score: float
    scores: Dict[str, float]
    slot: Slot

    def to_dict(self) -> dict:
        return {
            "slot_name": self.slot_name,
            "digit": self.digit,
            "score": self.score,
            "scores": dict(self.scores),
            "slot": list(self.slot),
        }


class CradleOfDeathCountdownRecognizer:
    """Template matcher for the Cradle of Death upper-right countdown."""

    TEMPLATE_DIR_NAME = "cradle_of_death_digits"
    TEMPLATE_NAME_RE = re.compile(r".+\.(png|bmp|jpg|jpeg)$", re.IGNORECASE)

    def __init__(
        self,
        template_root: Optional[str] = None,
        config: Optional[CradleCountdownConfig] = None,
        debug_dir: Optional[str] = None,
    ):
        self.logger = get_logger(__name__)
        self.config = config or CradleCountdownConfig()
        default_template_root = os.path.join(
            get_project_root(),
            "resources",
            "templates",
            self.TEMPLATE_DIR_NAME,
        )
        self.template_root = template_root or default_template_root
        self.debug_dir = debug_dir or os.path.join(os.getcwd(), "tests", "debug_cradle_of_death_countdown")
        self.last_debug_info: Optional[dict] = None
        self._templates_cache: Optional[Dict[str, List[Tuple[str, np.ndarray]]]] = None

        # Attribute names intentionally match WhiteSupplyRecognizer so its
        # make_white_text_mask implementation can be reused directly.
        self.white_gray_min = int(self.config.white_gray_min)
        self.white_rgb_min = int(self.config.white_rgb_min)
        self.white_rgb_delta_max = int(self.config.white_rgb_delta_max)
        self.white_percentile = int(self.config.white_percentile)
        self.white_use_percentile = bool(self.config.white_use_percentile)
        self.white_blur_ksize = int(self.config.white_blur_ksize)
        self.white_dilate_iter = int(self.config.white_dilate_iter)
        self.white_erode_iter = int(self.config.white_erode_iter)

    @staticmethod
    def _read_image_unicode(path: str, flags=cv2.IMREAD_COLOR) -> Optional[np.ndarray]:
        return WhiteSupplyRecognizer._read_image_unicode(path, flags)

    @staticmethod
    def _save_png_unicode(path: str, image: np.ndarray) -> bool:
        return WhiteSupplyRecognizer._save_png_unicode(path, image)

    @staticmethod
    def _to_binary_mask(gray: np.ndarray) -> np.ndarray:
        return WhiteSupplyRecognizer._to_binary_mask(gray)

    @staticmethod
    def _tight_crop_mask(mask: np.ndarray, padding: int = 0) -> np.ndarray:
        return WhiteSupplyRecognizer._tight_crop_mask(mask, padding=padding)

    def make_white_text_mask(self, img_bgr: np.ndarray) -> np.ndarray:
        return WhiteSupplyRecognizer.make_white_text_mask(self, img_bgr)

    def _load_templates(self) -> Dict[str, List[Tuple[str, np.ndarray]]]:
        if self._templates_cache is not None:
            return self._templates_cache

        templates: Dict[str, List[Tuple[str, np.ndarray]]] = {str(i): [] for i in range(10)}
        for digit in templates:
            digit_dir = os.path.join(self.template_root, digit)
            if not os.path.isdir(digit_dir):
                continue

            for filename in sorted(os.listdir(digit_dir)):
                if not self.TEMPLATE_NAME_RE.match(filename):
                    continue

                path = os.path.join(digit_dir, filename)
                img = self._read_image_unicode(path, cv2.IMREAD_GRAYSCALE)
                if img is None:
                    self.logger.warning("Failed to read Cradle countdown template: %s", path)
                    continue

                mask = self._to_binary_mask(img)
                mask = self._tight_crop_mask(mask, padding=0)
                if mask.size == 0 or int((mask > 0).sum()) == 0:
                    self.logger.warning("Empty Cradle countdown template skipped: %s", path)
                    continue
                templates[digit].append((filename, mask))

        loaded_count = sum(len(v) for v in templates.values())
        if loaded_count == 0:
            self.logger.warning("No Cradle countdown templates loaded from: %s", self.template_root)
        else:
            self.logger.info("Loaded Cradle countdown templates: %s", loaded_count)

        self._templates_cache = templates
        return templates

    def _scaled_roi(self, scale_factor: float, image_shape: Tuple[int, int, int]) -> Roi:
        return WhiteSupplyRecognizer._scaled_roi(self.config.roi, scale_factor, image_shape)

    @staticmethod
    def _scale_slot(slot: Slot, template_scale: int) -> Slot:
        x, y, w, h = slot
        return (
            int(round(x * template_scale)),
            int(round(y * template_scale)),
            max(1, int(round(w * template_scale))),
            max(1, int(round(h * template_scale))),
        )

    def _prepare_roi(
        self,
        game_screen: np.ndarray,
        scale_factor: float,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, Roi]:
        sx, sy, sw, sh = self._scaled_roi(scale_factor, game_screen.shape)
        roi_raw = game_screen[sy:sy + sh, sx:sx + sw].copy()
        roi_mask = self.make_white_text_mask(roi_raw)

        if self.config.normalize_roi_to_base_size:
            _, _, base_w, base_h = self.config.roi
            roi_norm = cv2.resize(roi_mask, (int(base_w), int(base_h)), interpolation=cv2.INTER_NEAREST)
        else:
            roi_norm = roi_mask

        if self.config.template_scale > 1:
            h, w = roi_norm.shape[:2]
            roi_scaled = cv2.resize(
                roi_norm,
                (w * self.config.template_scale, h * self.config.template_scale),
                interpolation=cv2.INTER_NEAREST,
            )
        else:
            roi_scaled = roi_norm.copy()

        return roi_raw, roi_mask, roi_scaled, (sx, sy, sw, sh)

    def _extract_scaled_slot(self, roi_scaled: np.ndarray, slot: Slot) -> np.ndarray:
        x, y, w, h = self._scale_slot(slot, self.config.template_scale)
        roi_h, roi_w = roi_scaled.shape[:2]
        x = max(0, min(roi_w - 1, x))
        y = max(0, min(roi_h - 1, y))
        ex = max(x + 1, min(roi_w, x + w))
        ey = max(y + 1, min(roi_h, y + h))
        return roi_scaled[y:ey, x:ex].copy()

    def _match_digit_slot(self, slot_mask: np.ndarray, slot_name: str, slot: Slot) -> DigitSlotMatch:
        templates = self._load_templates()
        slot_mask = self._to_binary_mask(slot_mask)
        slot_h, slot_w = slot_mask.shape[:2]
        scores: Dict[str, float] = {str(i): -1.0 for i in range(10)}

        for digit, tpl_list in templates.items():
            best = -1.0
            for template_name, tpl in tpl_list:
                tpl_h, tpl_w = tpl.shape[:2]
                if tpl_w > slot_w or tpl_h > slot_h:
                    continue
                result = cv2.matchTemplate(slot_mask, tpl, cv2.TM_CCOEFF_NORMED)
                if result.size == 0:
                    continue
                _, max_val, _, _ = cv2.minMaxLoc(result)
                best = max(best, float(max_val))
            scores[digit] = best

        best_digit = max(scores, key=lambda d: scores[d])
        best_score = float(scores[best_digit])
        if best_score < float(self.config.match_threshold):
            return DigitSlotMatch(slot_name=slot_name, digit=None, score=best_score, scores=scores, slot=slot)

        return DigitSlotMatch(slot_name=slot_name, digit=best_digit, score=best_score, scores=scores, slot=slot)

    @staticmethod
    def _format_result(matches: Sequence[DigitSlotMatch], roi: Roi) -> Optional[dict]:
        if len(matches) != 3 or any(m.digit is None for m in matches):
            return None

        raw_digits = "".join(str(m.digit) for m in matches)
        minute = int(raw_digits[0])
        seconds = int(raw_digits[1:])

        if not (0 <= minute <= 9):
            return None
        if not (0 <= seconds <= 59):
            return None

        digit_scores = [float(m.score) for m in matches]
        countdown_seconds = minute * 60 + seconds
        return {
            "raw_digits": raw_digits,
            "formatted_time": f"{minute}:{seconds:02d}",
            "countdown_seconds": countdown_seconds,
            "digit_scores": digit_scores,
            "min_score": min(digit_scores),
            "roi": list(roi),
        }

    def recognize(
        self,
        game_screen: np.ndarray,
        scale_factor: float = 1.0,
        save_debug: bool = False,
    ) -> Optional[dict]:
        """
        Recognize the m:ss countdown.

        Returns a dict on success and None on any failed slot, low confidence
        slot, illegal seconds value, or missing template set.
        """
        self.last_debug_info = None
        if game_screen is None or game_screen.size == 0:
            return None

        scale_factor = float(scale_factor)
        roi_raw, roi_mask, roi_scaled, roi = self._prepare_roi(game_screen, scale_factor)

        matches: List[DigitSlotMatch] = []
        slot_images: Dict[str, np.ndarray] = {}
        for slot_name, slot in zip(self.config.slot_names, self.config.digit_slots):
            slot_mask = self._extract_scaled_slot(roi_scaled, slot)
            slot_images[slot_name] = slot_mask
            matches.append(self._match_digit_slot(slot_mask, slot_name=slot_name, slot=slot))

        result = self._format_result(matches, roi)
        self.last_debug_info = {
            "result": result,
            "roi": list(roi),
            "base_roi": list(self.config.roi),
            "template_root": self.template_root,
            "threshold": float(self.config.match_threshold),
            "matches": [m.to_dict() for m in matches],
        }

        if save_debug:
            self._save_debug_images(
                game_screen=game_screen,
                roi_raw=roi_raw,
                roi_mask=roi_mask,
                roi_scaled=roi_scaled,
                roi=roi,
                slot_images=slot_images,
                matches=matches,
                result=result,
            )

        return result

    def _save_debug_images(
        self,
        game_screen: np.ndarray,
        roi_raw: np.ndarray,
        roi_mask: np.ndarray,
        roi_scaled: np.ndarray,
        roi: Roi,
        slot_images: Dict[str, np.ndarray],
        matches: Sequence[DigitSlotMatch],
        result: Optional[dict],
    ) -> None:
        os.makedirs(self.debug_dir, exist_ok=True)

        original = game_screen.copy()
        x, y, w, h = roi
        cv2.rectangle(original, (x, y), (x + w, y + h), (0, 220, 0), 2)
        label = result["formatted_time"] if result else "None"
        cv2.putText(
            original,
            label,
            (x, max(12, y - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 220, 0) if result else (0, 0, 255),
            2,
            cv2.LINE_AA,
        )

        self._save_png_unicode(os.path.join(self.debug_dir, "01_original_with_roi.png"), original)
        self._save_png_unicode(os.path.join(self.debug_dir, "02_countdown_roi_raw.png"), roi_raw)
        self._save_png_unicode(os.path.join(self.debug_dir, "03_countdown_roi_white_mask.png"), roi_mask)
        self._save_png_unicode(os.path.join(self.debug_dir, "04_countdown_roi_scaled_mask.png"), roi_scaled)

        roi_canvas = cv2.cvtColor(roi_scaled, cv2.COLOR_GRAY2BGR)
        for m in matches:
            sx, sy, sw, sh = self._scale_slot(m.slot, self.config.template_scale)
            color = (0, 220, 0) if m.digit is not None else (0, 0, 255)
            cv2.rectangle(roi_canvas, (sx, sy), (sx + sw, sy + sh), color, 1)
            text = m.digit if m.digit is not None else "?"
            cv2.putText(
                roi_canvas,
                f"{text}:{m.score:.2f}",
                (sx, max(10, sy + 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.35,
                color,
                1,
                cv2.LINE_AA,
            )
        self._save_png_unicode(os.path.join(self.debug_dir, "05_scaled_roi_slots.png"), roi_canvas)

        for index, (slot_name, slot_mask) in enumerate(slot_images.items(), start=1):
            self._save_png_unicode(os.path.join(self.debug_dir, f"slot_{index}_{slot_name}.png"), slot_mask)

        debug_json = {
            "result": result,
            "roi": list(roi),
            "base_roi": list(self.config.roi),
            "slots": [
                {"name": name, "slot": list(slot)}
                for name, slot in zip(self.config.slot_names, self.config.digit_slots)
            ],
            "matches": [m.to_dict() for m in matches],
        }
        with open(os.path.join(self.debug_dir, "matches.json"), "w", encoding="utf-8") as f:
            json.dump(debug_json, f, ensure_ascii=False, indent=2)

        with open(os.path.join(self.debug_dir, "matches.txt"), "w", encoding="utf-8") as f:
            f.write(f"result: {result}\n")
            f.write(f"roi: {list(roi)}\n")
            f.write(f"template_root: {self.template_root}\n")
            f.write(f"threshold: {self.config.match_threshold:.3f}\n\n")
            for m in matches:
                f.write(f"[{m.slot_name}] selected={m.digit} score={m.score:.3f}\n")
                for digit, score in sorted(m.scores.items(), key=lambda item: item[0]):
                    f.write(f"  {digit}: {score:.3f}\n")


__all__ = [
    "CradleCountdownConfig",
    "CradleOfDeathCountdownRecognizer",
]
