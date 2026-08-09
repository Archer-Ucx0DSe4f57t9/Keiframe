# -*- coding: utf-8 -*-
"""
Background handler for Cradle of Death countdown recognition.

This module bridges the screenshot recognizer and the pure phase detector. It
does not touch Qt, ToastManager, tables, databases, or the main window.
"""

from __future__ import annotations

from collections import deque
import math
import os
import threading
import time
import traceback
from typing import Deque, Dict, List, Optional

from src import config, game_state_service
from src.game_readers.cradle_of_death_countdown_recognizer import CradleOfDeathCountdownRecognizer
from src.map_handlers.cradle_of_death_phase_detector import CradleOfDeathPhaseDetector
from src.utils.fileutil import get_project_root
from src.utils.logging_util import get_logger


class CradleOfDeathMapHandler:
    HOLD_SECONDS = 4
    OCR_INTERVAL_SECONDS = 0.22
    MIN_PHASE_GAME_SECONDS = 60

    LANG_ALIASES = {
        "cn": "cn",
        "zh": "cn",
        "zh_cn": "cn",
        "zh-cn": "cn",
        "chinese": "cn",
        "en": "en",
        "english": "en",
    }

    def __init__(
        self,
        lang: Optional[str] = None,
        recognizer: Optional[CradleOfDeathCountdownRecognizer] = None,
        phase_detector: Optional[CradleOfDeathPhaseDetector] = None,
        state=None,
        hold_seconds: int = HOLD_SECONDS,
        ocr_interval_seconds: float = OCR_INTERVAL_SECONDS,
        min_phase_game_seconds: int = MIN_PHASE_GAME_SECONDS,
        logger=None,
    ):
        self.lang = self._normalize_lang(lang if lang is not None else getattr(config, "current_game_language", "cn"))
        self.state = state or game_state_service.state
        self.logger = logger or get_logger(__name__)
        self.hold_seconds = int(hold_seconds)
        self.ocr_interval_seconds = float(ocr_interval_seconds)
        self.min_phase_game_seconds = int(min_phase_game_seconds)

        self.recognizer = recognizer or self._create_recognizer(self.lang)
        self.phase_detector = phase_detector or CradleOfDeathPhaseDetector(
            min_baseline_game_seconds=self.min_phase_game_seconds
        )

        self._lock = threading.Lock()
        self._phase_events: Deque[Dict[str, object]] = deque()
        self._latest_data: Optional[Dict[str, object]] = None
        self._last_screenshot_timestamp = None
        self._last_valid_countdown_seconds: Optional[int] = None
        self._last_valid_game_second: Optional[int] = None
        self._last_valid_raw_digits: Optional[str] = None

        self._shutdown_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return

            self._shutdown_event.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                name="CradleOfDeathMapHandler",
                daemon=True,
            )
            self._thread.start()

    def reset(self) -> None:
        with self._lock:
            self._latest_data = None
            self._phase_events.clear()
            self._last_screenshot_timestamp = None
            self._last_valid_countdown_seconds = None
            self._last_valid_game_second = None
            self._last_valid_raw_digits = None
            self.phase_detector.reset()

    def shutdown(self) -> None:
        self._shutdown_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)
        with self._lock:
            if self._thread is thread:
                self._thread = None

    def get_latest_data(self) -> Optional[Dict[str, object]]:
        with self._lock:
            return dict(self._latest_data) if self._latest_data is not None else None

    def consume_phase_events(self) -> List[Dict[str, object]]:
        with self._lock:
            events = list(self._phase_events)
            self._phase_events.clear()
            return events

    def _run_loop(self) -> None:
        while not self._shutdown_event.is_set():
            started_at = time.perf_counter()
            try:
                self._process_once()
            except Exception:
                self.logger.error("死亡摇篮后台识别处理失败: %s", traceback.format_exc())

            elapsed = time.perf_counter() - started_at
            sleep_seconds = max(0.0, self.ocr_interval_seconds - elapsed)
            self._shutdown_event.wait(sleep_seconds)

    def _process_once(self) -> None:
        snapshot = self._read_latest_snapshot()
        if snapshot is None:
            return

        screenshot, screenshot_timestamp, scale_factor, game_time_seconds = snapshot
        if self._screenshot_was_processed(screenshot_timestamp):
            return

        result = self.recognizer.recognize(screenshot, scale_factor=scale_factor)
        with self._lock:
            if result is None:
                self._update_held_or_stale_data_locked(game_time_seconds)
                return

            countdown_seconds = self._coerce_seconds(result.get("countdown_seconds"))
            if countdown_seconds is None:
                self._update_held_or_stale_data_locked(game_time_seconds)
                return

            self._update_real_data_locked(result, countdown_seconds, game_time_seconds)

    def _screenshot_was_processed(self, screenshot_timestamp) -> bool:
        with self._lock:
            if screenshot_timestamp == self._last_screenshot_timestamp:
                return True
            self._last_screenshot_timestamp = screenshot_timestamp
            return False

    def _read_latest_snapshot(self):
        screenshot_lock = getattr(self.state, "screenshot_lock", None)
        if screenshot_lock is None:
            return None

        with screenshot_lock:
            screenshot = getattr(self.state, "latest_screenshot", None)
            screenshot_timestamp = getattr(self.state, "screenshot_timestamp", None)
            scale_factor = getattr(self.state, "scale_factor", 1.0)
            game_time_seconds = self._coerce_seconds(getattr(self.state, "game_time", None))
            if screenshot is None or screenshot_timestamp is None:
                return None
            screenshot_copy = screenshot.copy()

        return screenshot_copy, screenshot_timestamp, float(scale_factor or 1.0), game_time_seconds

    def _update_real_data_locked(
        self,
        result: Dict[str, object],
        countdown_seconds: int,
        game_time_seconds: Optional[int],
    ) -> None:
        real_data = self._build_real_data(result, countdown_seconds, game_time_seconds)
        phase_events: List[Dict[str, object]] = []

        if game_time_seconds is not None:
            self._last_valid_countdown_seconds = countdown_seconds
            self._last_valid_game_second = game_time_seconds
            self._last_valid_raw_digits = real_data.get("raw_digits")
            if game_time_seconds >= self.min_phase_game_seconds:
                confidence = real_data.get("score")
                self.phase_detector.update(countdown_seconds, game_time_seconds, confidence=confidence)
                phase_events = self._decorate_phase_events(self.phase_detector.consume_events())

        detector_state = self.phase_detector.get_state()
        real_data["phase"] = detector_state.get("current_phase", 0)
        self._latest_data = real_data
        self._phase_events.extend(phase_events)

    def _update_held_or_stale_data_locked(self, game_time_seconds: Optional[int]) -> None:
        held_data = self._build_held_data_locked(game_time_seconds)
        if held_data is not None:
            self._latest_data = held_data
            return

        self._latest_data = {
            "lang": self.lang,
            "is_held": False,
            "is_stale": True,
            "phase": self.phase_detector.get_state().get("current_phase", 0),
            "last_update_game_second": game_time_seconds,
        }

    def _build_held_data_locked(self, game_time_seconds: Optional[int]) -> Optional[Dict[str, object]]:
        if (
            game_time_seconds is None
            or self._last_valid_countdown_seconds is None
            or self._last_valid_game_second is None
        ):
            return None

        elapsed_game_seconds = max(0, game_time_seconds - self._last_valid_game_second)
        if elapsed_game_seconds > self.hold_seconds:
            return None

        estimated_countdown = max(0, self._last_valid_countdown_seconds - elapsed_game_seconds)
        return {
            "countdown_seconds": estimated_countdown,
            "formatted_time": self._format_seconds(estimated_countdown),
            "raw_digits": self._last_valid_raw_digits,
            "lang": self.lang,
            "score": None,
            "is_held": True,
            "is_stale": False,
            "last_real_countdown_seconds": self._last_valid_countdown_seconds,
            "last_real_game_second": self._last_valid_game_second,
            "phase": self.phase_detector.get_state().get("current_phase", 0),
            "last_update_game_second": game_time_seconds,
        }

    def _build_real_data(
        self,
        result: Dict[str, object],
        countdown_seconds: int,
        game_time_seconds: Optional[int],
    ) -> Dict[str, object]:
        score = result.get("min_score")
        if score is None:
            digit_scores = result.get("digit_scores")
            if digit_scores:
                score = min(float(value) for value in digit_scores)

        return {
            "countdown_seconds": countdown_seconds,
            "formatted_time": result.get("formatted_time") or self._format_seconds(countdown_seconds),
            "raw_digits": result.get("raw_digits"),
            "lang": self.lang,
            "score": score,
            "is_held": False,
            "is_stale": False,
            "phase": self.phase_detector.get_state().get("current_phase", 0),
            "last_update_game_second": game_time_seconds,
        }

    def _decorate_phase_events(self, events: List[Dict[str, object]]) -> List[Dict[str, object]]:
        decorated = []
        for event in events:
            enriched = dict(event)
            enriched.setdefault("type", "phase_started")
            enriched.setdefault("source", "cradle_of_death")
            decorated.append(enriched)
        return decorated

    @classmethod
    def _normalize_lang(cls, lang: Optional[str]) -> str:
        key = str(lang or "cn").strip().lower()
        return cls.LANG_ALIASES.get(key, "cn")

    @classmethod
    def _create_recognizer(cls, lang: str) -> CradleOfDeathCountdownRecognizer:
        template_root = os.path.join(
            get_project_root(),
            "resources",
            "templates",
            CradleOfDeathCountdownRecognizer.TEMPLATE_DIR_NAME,
            lang,
        )
        if not os.path.isdir(template_root):
            template_root = os.path.join(
                get_project_root(),
                "resources",
                "templates",
                CradleOfDeathCountdownRecognizer.TEMPLATE_DIR_NAME,
            )
        return CradleOfDeathCountdownRecognizer(template_root=template_root)

    @staticmethod
    def _coerce_seconds(value) -> Optional[int]:
        if value is None or isinstance(value, bool):
            return None
        try:
            seconds = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(seconds) or seconds < 0:
            return None
        return int(round(seconds))

    @staticmethod
    def _format_seconds(seconds: int) -> str:
        minutes = int(seconds) // 60
        remainder = int(seconds) % 60
        return f"{minutes}:{remainder:02d}"


__all__ = ["CradleOfDeathMapHandler"]