"""Malwarfare map state handler backed by the frozen production OCR runtime."""

from __future__ import annotations

from collections import deque
import numbers
import threading
import time

import cv2
import numpy as np

from src import config
from src.game_state_service import state
from src.malwarfare import MalwarfareOcrProcessor
from src.utils.logging_util import get_logger


class MalwarfareMapHandler:
    """Recognize Malwarfare visuals and preserve the existing game-state contract."""

    COUNT_INTERVAL_SECONDS = 1.0
    STATUS_INTERVAL_SECONDS = 0.13
    LOOP_IDLE_SECONDS = 0.02
    FAILURE_RELOCATION_THRESHOLD = 30
    CANONICAL_FRAME_SHAPE = (1080, 1920, 3)

    UI_PROFILES = (
        "Normal",
        "Replay",
        "Hero",
        "HeroReplay",
        "Zweihaka",
        "ZweihakaReplay",
    )
    COUNT_COLOR_PROFILES = ("green", "blue", "orange")
    UI_PROFILE_OFFSETS = {
        "Normal": 0,
        "Replay": 49,
        "Hero": 97,
        "HeroReplay": 146,
        "Zweihaka": 181,
        "ZweihakaReplay": 230,
    }
    COUNT_PROBE_ROI = (172, 72, 219, 103)
    COUNT_PROBE_MIN_PIXELS = 0

    def __init__(self, game_state=None, debug=False, ocr_processor=None):
        self.logger = get_logger(__name__)
        self.logger.info("初始化 MalwarfareMapHandler...")
        self.debug = debug
        self.game_state = game_state or state
        self.lang = config.current_game_language

        # Resource/manifest/SHA errors are intentionally not swallowed. The frozen
        # runtime is loaded once for the lifetime of this handler.
        self.ocr = ocr_processor or MalwarfareOcrProcessor.from_default_resources()

        self._running = False
        self._running_thread = None
        self._state_lock = threading.RLock()
        self._result_lock = threading.Lock()

        self._count_timings_ms = deque(maxlen=120)
        self._status_timings_ms = deque(maxlen=120)
        self._count_timing_samples = 0
        self._status_timing_samples = 0

        self._count_probe_ranges = (
            (np.array([60, 70, 70]), np.array([90, 255, 255])),
            (np.array([100, 100, 100]), np.array([125, 255, 255])),
            (np.array([10, 150, 150]), np.array([25, 255, 255])),
        )

        self._reset_state()

    def start(self):
        """Start the single sequential OCR worker."""
        if self._running_thread is None or not self._running_thread.is_alive():
            self._running = True
            self._running_thread = threading.Thread(
                target=self._run_loop,
                name="MalwarfareOcrWorker",
                daemon=True,
            )
            self._running_thread.start()
            self.logger.info("MalwarfareMapHandler 已启动单序列后台 OCR 线程。")

    def cleanup(self):
        """Stop the worker; the cached OCR models remain owned by this instance."""
        self._running = False
        worker = self._running_thread
        if (
            worker is not None
            and worker.is_alive()
            and worker is not threading.current_thread()
        ):
            worker.join(timeout=1)
        self._running_thread = None
        self.logger.info("MalwarfareMapHandler 已停止。")

    def shutdown(self):
        self.logger.info("请求关闭 MalwarfareMapHandler...")
        self.cleanup()

    def _run_loop(self):
        """Process only the newest screenshot, with no executor or queued frames."""
        while self._running and not getattr(self.game_state, "app_closing", False):
            with self.game_state.screenshot_lock:
                screenshot = self.game_state.latest_screenshot
                screenshot_timestamp = self.game_state.screenshot_timestamp
                if screenshot is None:
                    frame = None
                else:
                    # Shared state is copied under the lock and processed after release.
                    frame = screenshot.copy()

            if (
                frame is None
                or screenshot_timestamp == self._last_game_screen_timestamp
            ):
                time.sleep(self.LOOP_IDLE_SECONDS)
                continue

            # Mark the frame before OCR. If OCR takes longer than a capture interval,
            # the next pass reads the newest screenshot and intermediate frames vanish.
            self._last_game_screen_timestamp = screenshot_timestamp
            self._process_frame(frame, now=time.perf_counter())

        self._running = False

    def _process_frame(self, frame, *, now=None):
        """Validate and synchronously dispatch due OCR operations for one frame."""
        if not self._validate_frame(frame):
            self._set_latest_count(None)
            self._update_latest_result()
            return

        if self._current_ui_profile is None:
            if not self._detect_and_set_ui_state(frame):
                return

        current_time = time.perf_counter() if now is None else float(now)

        if self._is_due(current_time, self._last_count_update, self.COUNT_INTERVAL_SECONDS):
            self._last_count_update = current_time
            self._ocr_and_process_count(frame)

        if self._is_due(current_time, self._last_status_update, self.STATUS_INTERVAL_SECONDS):
            self._last_status_update = current_time
            self._ocr_and_process_time_and_paused(frame)

        self._update_latest_result()

    @staticmethod
    def _is_due(now, last_update, interval):
        return last_update is None or now - last_update >= interval

    def _validate_frame(self, frame):
        if not isinstance(frame, np.ndarray):
            self.logger.error(
                "Malwarfare OCR 输入必须为 numpy.ndarray，实际为 %s。",
                type(frame).__name__,
            )
            return False
        if frame.dtype != np.uint8 or frame.shape != self.CANONICAL_FRAME_SHAPE:
            self.logger.error(
                "Malwarfare OCR 输入必须为 1920x1080 uint8 BGR，实际 shape=%s, dtype=%s；不会静默缩放。",
                frame.shape,
                frame.dtype,
            )
            return False
        return True

    def _detect_and_set_ui_state(self, frame):
        """Find a unique UI profile/color pair using production Count OCR."""
        self.logger.info("正在使用新版 Count OCR 探测 UI profile 和颜色...")
        candidates = []
        for ui_profile in self._ordered_ui_profiles():
            if not self._coarse_profile_has_count_color(frame, ui_profile):
                continue
            for color_profile in self.COUNT_COLOR_PROFILES:
                try:
                    count = self._timed_recognize_count(
                        frame,
                        ui_profile=ui_profile,
                        color_profile=color_profile,
                    )
                except Exception:
                    self.logger.exception(
                        "UI 探测调用新版 Count OCR 失败: profile=%s, color=%s",
                        ui_profile,
                        color_profile,
                    )
                    return False
                if self._is_valid_count(count):
                    candidates.append((ui_profile, color_profile, int(count)))
                elif count is not None:
                    self.logger.error(
                        "新版 Count OCR 违反输出 contract: profile=%s, color=%s, value=%r",
                        ui_profile,
                        color_profile,
                        count,
                    )

        selected = self._select_ui_candidate(candidates)
        if selected is None:
            if candidates:
                self.logger.warning("UI 探测结果不唯一，暂不采用: %s", candidates)
            else:
                self.logger.debug("UI 探测未找到可见的 Count。")
            return False

        ui_profile, color_profile, count = selected
        with self._state_lock:
            self._current_ui_profile = ui_profile
            self._detected_count_color = color_profile
            self._latest_count = count
            self._last_successful_ui_profile = ui_profile
        self.logger.info(
            "UI 状态探测成功: profile=%s, count_color=%s, count=%s",
            ui_profile,
            color_profile,
            count,
        )
        return True

    def _coarse_profile_has_count_color(self, frame, ui_profile):
        """Cheap legacy HSV presence probe; production OCR remains authoritative."""
        offset = self.UI_PROFILE_OFFSETS[ui_profile]
        x0, y0, x1, y1 = self.COUNT_PROBE_ROI
        roi = frame[y0 + offset : y1 + offset, x0:x1]
        if roi.size == 0:
            return False
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        combined_mask = None
        for lower, upper in self._count_probe_ranges:
            color_mask = cv2.inRange(hsv, lower, upper)
            combined_mask = (
                color_mask
                if combined_mask is None
                else cv2.bitwise_or(combined_mask, color_mask)
            )
        return cv2.countNonZero(combined_mask) > self.COUNT_PROBE_MIN_PIXELS

    def _ordered_ui_profiles(self):
        preferred = self._last_successful_ui_profile
        if preferred in self.UI_PROFILES:
            return (preferred,) + tuple(
                profile for profile in self.UI_PROFILES if profile != preferred
            )
        return self.UI_PROFILES

    def _select_ui_candidate(self, candidates):
        if len(candidates) == 1:
            return candidates[0]

        preferred = self._last_successful_ui_profile
        preferred_candidates = [
            candidate for candidate in candidates if candidate[0] == preferred
        ]
        if len(preferred_candidates) == 1:
            return preferred_candidates[0]
        return None

    def _ocr_and_process_count(self, frame):
        """Recognize Count as int | None without legacy text cleanup or hacks."""
        ui_profile = self._current_ui_profile
        if ui_profile is None:
            return

        if self._detected_count_color is None:
            color_results = []
            for color_profile in self.COUNT_COLOR_PROFILES:
                try:
                    count = self._timed_recognize_count(
                        frame,
                        ui_profile=ui_profile,
                        color_profile=color_profile,
                    )
                except Exception:
                    self.logger.exception(
                        "Count 颜色自动探测失败: profile=%s, color=%s",
                        ui_profile,
                        color_profile,
                    )
                    self._set_latest_count(None)
                    return
                if self._is_valid_count(count):
                    color_results.append((color_profile, int(count)))
                elif count is not None:
                    self.logger.error("新版 Count OCR 返回非法值: %r", count)

            if len(color_results) != 1:
                if color_results:
                    self.logger.warning("Count 颜色探测结果不唯一: %s", color_results)
                self._set_latest_count(None)
                return
            self._detected_count_color, parsed_count = color_results[0]
        else:
            try:
                parsed_count = self._timed_recognize_count(
                    frame,
                    ui_profile=ui_profile,
                    color_profile=self._detected_count_color,
                )
            except Exception:
                self.logger.exception(
                    "Count OCR 执行失败: profile=%s, color=%s",
                    ui_profile,
                    self._detected_count_color,
                )
                self._set_latest_count(None)
                return

        if parsed_count is not None and not self._is_valid_count(parsed_count):
            self.logger.error("新版 Count OCR 返回非法值: %r", parsed_count)
            parsed_count = None
        self._set_latest_count(
            int(parsed_count) if parsed_count is not None else None
        )

    def _ocr_and_process_time_and_paused(self, frame):
        """Apply OCR output while keeping pause history and the 25-second rule here."""
        ui_profile = self._current_ui_profile
        if ui_profile is None:
            return

        started = time.perf_counter()
        try:
            time_value, paused = self.ocr.recognize_time_paused(
                frame,
                ui_profile=ui_profile,
            )
        except Exception:
            self.logger.exception(
                "Time/Paused OCR 执行失败: profile=%s",
                ui_profile,
            )
            return
        finally:
            self._record_timing("status", (time.perf_counter() - started) * 1000.0)

        if time_value is not None:
            normalized_time = self._normalize_time_value(time_value)
            if normalized_time is None:
                self.logger.error("新版 Time OCR 返回非法 MSS 值: %r", time_value)
                return
            with self._state_lock:
                self._latest_time = normalized_time
                self._latest_paused = False
            return

        if paused is True:
            with self._state_lock:
                self._latest_time = None
                self._latest_paused = True
            return

        if paused not in (False, None):
            self.logger.error("新版 Paused OCR 返回非法值: %r", paused)
            return

        # Neither Time nor Paused is visible. Above 25 seconds this is treated
        # as a transient miss and the previous raw state is retained unchanged.
        last_time_seconds = self._last_valid_time_seconds()
        if last_time_seconds is not None and last_time_seconds > 25:
            self.logger.debug(
                "时间识别暂时失败，但历史时间 >25 秒；保留上一有效时间。"
            )
            with self._state_lock:
                self._latest_time = self._formatted_time_to_mss(
                    self._last_valid_parsed.get("time")
                )
                self._latest_paused = False
            return

        # At/below 25 seconds (or without history), the legacy state machine
        # enters the normal movement/no-timer phase.
        with self._state_lock:
            self._latest_time = None
            self._latest_paused = False

    def _timed_recognize_count(self, frame, *, ui_profile, color_profile):
        started = time.perf_counter()
        try:
            return self.ocr.recognize_count(
                frame,
                ui_profile=ui_profile,
                count_color_profile=color_profile,
            )
        finally:
            self._record_timing("count", (time.perf_counter() - started) * 1000.0)

    def _record_timing(self, operation, elapsed_ms):
        if operation == "count":
            samples = self._count_timings_ms
            self._count_timing_samples += 1
            sample_count = self._count_timing_samples
        else:
            samples = self._status_timings_ms
            self._status_timing_samples += 1
            sample_count = self._status_timing_samples
        samples.append(float(elapsed_ms))
        self.logger.debug("Malwarfare %s OCR 耗时 %.2f ms", operation, elapsed_ms)
        if sample_count % 50 == 0:
            self.logger.info(
                "Malwarfare %s OCR 最近 %d 次平均 %.2f ms，最大 %.2f ms。",
                operation,
                len(samples),
                sum(samples) / len(samples),
                max(samples),
            )

    def get_performance_metrics(self):
        """Return lightweight in-process timing metrics for diagnostics."""
        return {
            "count": self._timing_summary(self._count_timings_ms),
            "time_paused": self._timing_summary(self._status_timings_ms),
        }

    @staticmethod
    def _timing_summary(samples):
        if not samples:
            return {"samples": 0, "average_ms": None, "maximum_ms": None}
        return {
            "samples": len(samples),
            "average_ms": sum(samples) / len(samples),
            "maximum_ms": max(samples),
        }

    def _update_latest_result(self):
        with self._state_lock:
            latest_count = self._latest_count
            latest_paused = bool(self._latest_paused)
            latest_time = self._latest_time

        if latest_count is None:
            if self._current_ui_profile is not None:
                self._consecutive_failures += 1
                if self._consecutive_failures > self.FAILURE_RELOCATION_THRESHOLD:
                    self.logger.info("Count 连续识别失败，重新定位 UI profile。")
                    recent_profile = self._current_ui_profile
                    self.reset()
                    # A relocation may yield more than one Count candidate. Keep
                    # only the recently successful profile as a tie-break hint;
                    # the active profile and color themselves were reset above.
                    with self._state_lock:
                        self._last_successful_ui_profile = recent_profile
            return

        final_time = None
        if not latest_paused and latest_time is not None:
            current_mss = self._normalize_time_value(latest_time)
            if current_mss is not None:
                current_seconds = int(current_mss[0]) * 60 + int(current_mss[1:])
                final_time = f"{current_mss[0]}:{current_mss[1:]}"

                if (
                    self._last_valid_parsed
                    and self._last_valid_parsed.get("time")
                    and latest_count == self._last_valid_parsed.get("n")
                ):
                    last_seconds = self._parse_formatted_time(
                        self._last_valid_parsed.get("time")
                    )
                    if (
                        last_seconds is not None
                        and current_seconds - 1 > last_seconds
                    ):
                        final_time = self._last_valid_parsed.get("time")
            else:
                self.logger.warning("时间处理错误: %r", latest_time)
        elif latest_paused and self._last_valid_parsed:
            final_time = self._last_valid_parsed.get("time")

        parsed = {
            "lang": self.lang,
            "n": latest_count,
            "time": final_time,
            "is_paused": latest_paused,
        }
        self._consecutive_failures = 0
        if self._last_valid_parsed is None or parsed != self._last_valid_parsed:
            self.logger.info("状态更新: %s", parsed)
            self._last_valid_parsed = parsed

        with self._result_lock:
            self._latest_result = self._last_valid_parsed

    @staticmethod
    def _is_valid_count(value):
        return (
            isinstance(value, numbers.Integral)
            and not isinstance(value, bool)
            and 0 <= int(value) <= 4
        )

    @staticmethod
    def _normalize_time_value(value):
        if isinstance(value, bool):
            return None
        if isinstance(value, numbers.Integral):
            numeric = int(value)
            raw_value = f"{numeric:03d}" if 0 <= numeric <= 999 else ""
        elif isinstance(value, str):
            raw_value = value
        else:
            return None
        if (
            len(raw_value) == 3
            and raw_value.isascii()
            and raw_value.isdigit()
            and 0 <= int(raw_value[0]) <= 3
            and 0 <= int(raw_value[1:]) <= 59
        ):
            return raw_value
        return None

    @staticmethod
    def _parse_formatted_time(value):
        try:
            minutes, seconds = (int(part) for part in str(value).split(":"))
        except (TypeError, ValueError):
            return None
        if minutes < 0 or not 0 <= seconds <= 59:
            return None
        return minutes * 60 + seconds

    @classmethod
    def _formatted_time_to_mss(cls, value):
        total_seconds = cls._parse_formatted_time(value)
        if total_seconds is None:
            return None
        minutes, seconds = divmod(total_seconds, 60)
        if minutes > 3:
            return None
        return f"{minutes}{seconds:02d}"

    def _last_valid_time_seconds(self):
        if not self._last_valid_parsed:
            return None
        return self._parse_formatted_time(self._last_valid_parsed.get("time"))

    def _set_latest_count(self, value):
        with self._state_lock:
            self._latest_count = value

    def get_latest_data(self):
        with self._result_lock:
            return self._latest_result.copy() if self._latest_result else None

    def reset(self):
        """Reset game/UI state without reloading frozen OCR resources."""
        self.logger.info("重置 MalwarfareMapHandler...")
        self._reset_state()

    def _reset_state(self):
        with self._state_lock:
            self._consecutive_failures = 0
            self._time_recognition_failures = 0
            self._current_ui_profile = None
            self._detected_count_color = None
            self._last_successful_ui_profile = None
            self._latest_count = None
            self._latest_paused = None
            self._latest_time = None
            self._last_valid_parsed = None
            self._last_count_update = None
            self._last_status_update = None
            self._last_game_screen_timestamp = None
        with self._result_lock:
            self._latest_result = None
