"""Malwarfare map state handler backed by the frozen production OCR runtime."""

from __future__ import annotations

from collections import deque
import copy
import numbers
import threading
import time

import cv2
import numpy as np

from src import config
from src.game_state_service import state
from src.malwarfare.ocr_processor import (
    DEFAULT_PROFILE_PATH,
    MalwarfareOcrProcessor,
)
from src.malwarfare.profile import load_profile
from src.malwarfare.runtime_3840 import Malwarfare3840Runtime
from src.malwarfare.runtime_router import MalwarfareRuntimeRouter
from src.utils.logging_util import get_logger


class MalwarfareMapHandler:
    """Recognize Malwarfare visuals and preserve the existing game-state contract."""

    COUNT_INTERVAL_SECONDS = 1.0
    STATUS_INTERVAL_SECONDS = 0.13
    LOOP_IDLE_SECONDS = 0.02
    FAILURE_RELOCATION_THRESHOLD = 30
    CANONICAL_FRAME_SHAPE = (1080, 1920, 3)
    NATIVE_3840_FRAME_SHAPE = (2160, 3840, 3)

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
    DIAGNOSTIC_LOG_INTERVAL_SECONDS = 10.0

    def __init__(
        self,
        game_state=None,
        debug=False,
        ocr_processor=None,
        runtime_router=None,
        enable_3840_runtime=None,
        diagnostic_ui_profile_override=None,
        diagnostic_count_color_override=None,
    ):
        self.logger = get_logger(__name__)
        self.logger.info("初始化 MalwarfareMapHandler...")
        self.debug = debug
        self.game_state = game_state or state
        self.lang = config.current_game_language

        # Resource/manifest/SHA errors are intentionally not swallowed. The frozen
        # runtime is loaded once for the lifetime of this handler.
        self.ocr = ocr_processor or MalwarfareOcrProcessor.from_default_resources()
        self._ui_geometry = getattr(self.ocr, "profile", None) or load_profile(
            DEFAULT_PROFILE_PATH
        )
        if tuple(self._ui_geometry.ui_offsets) != self.UI_PROFILES:
            raise ValueError("Malwarfare UI profile order does not match shared config")
        if dict(self._ui_geometry.ui_offsets) != self.UI_PROFILE_OFFSETS:
            raise ValueError("Malwarfare UI offsets do not match shared config")
        normal_count = self._ui_geometry.resolved_task("count", "Normal")[1]
        if self._roi_diagnostic(normal_count) != self.COUNT_PROBE_ROI:
            raise ValueError("Malwarfare Count probe does not match shared config")
        self.enable_3840_runtime = (
            getattr(config, "enable_malwarfare_3840_runtime", False) is True
            if enable_3840_runtime is None
            else bool(enable_3840_runtime)
        )
        if diagnostic_ui_profile_override not in (None, *self.UI_PROFILES):
            raise ValueError(
                "3840 diagnostic UI override must name a configured UI profile"
            )
        if (
            diagnostic_count_color_override is not None
            and diagnostic_count_color_override not in self.COUNT_COLOR_PROFILES
        ):
            raise ValueError(
                "3840 diagnostic Count color override must be green, blue, or orange"
            )
        self._diagnostic_ui_profile_override = diagnostic_ui_profile_override
        self._diagnostic_count_color_override = diagnostic_count_color_override
        self._diagnostic_log_times = {}
        self.logger.warning(
            "[HandlerDiag] Malwarfare Runtime 配置: enable_3840=%s, config_module=%s, "
            "ui_override=%r, color_override=%r",
            self.enable_3840_runtime,
            getattr(config, "__file__", None),
            self._diagnostic_ui_profile_override,
            self._diagnostic_count_color_override,
        )
        self.runtime_router = None
        if self.enable_3840_runtime:
            try:
                runtime_3840 = (
                    Malwarfare3840Runtime.from_default_resources()
                    if runtime_router is None
                    else None
                )
                self.runtime_router = runtime_router or MalwarfareRuntimeRouter(
                    runtime_2560=self.ocr,
                    runtime_3840=runtime_3840,
                )
            except Exception as exc:
                raise RuntimeError(
                    "Malwarfare 3840 Runtime 初始化失败；不会静默回退到 2560 模型"
                ) from exc

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
            self.logger.warning(
                "[HandlerDiag] MalwarfareMapHandler 已启动: running_flag=%s, "
                "worker_alive=%s",
                self._running,
                self._running_thread.is_alive(),
            )

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
                native_screenshot = getattr(
                    self.game_state,
                    "latest_malwarfare_native_screenshot",
                    None,
                )
                if self.enable_3840_runtime and native_screenshot is not None:
                    native_frame = native_screenshot.copy()
                else:
                    native_frame = None
                native_shape = getattr(
                    self.game_state,
                    "latest_screenshot_native_shape",
                    None,
                )

            if (
                frame is None
                or screenshot_timestamp == self._last_game_screen_timestamp
            ):
                self._log_diagnostic(
                    "waiting_for_frame",
                    "warning",
                    "[HandlerDiag] 等待新截图: frame=%s, timestamp=%r, "
                    "is_in_game=%r, app_closing=%r",
                    frame is not None,
                    screenshot_timestamp,
                    getattr(self.game_state, "is_in_game", None),
                    getattr(self.game_state, "app_closing", None),
                )
                time.sleep(self.LOOP_IDLE_SECONDS)
                continue

            # Mark the frame before OCR. If OCR takes longer than a capture interval,
            # the next pass reads the newest screenshot and intermediate frames vanish.
            self._last_game_screen_timestamp = screenshot_timestamp
            self._process_frame(
                frame,
                native_frame=native_frame,
                native_shape=native_shape,
                now=time.perf_counter(),
            )

        self._running = False

    def _process_frame(
        self,
        frame,
        *,
        now=None,
        native_frame=None,
        native_shape=None,
    ):
        """Validate and synchronously dispatch due OCR operations for one frame."""
        if not self._validate_frame(frame):
            self._set_latest_count(None)
            self._update_latest_result()
            return

        source_shape = (
            tuple(native_shape)
            if native_shape is not None
            else getattr(native_frame, "shape", None)
        )
        if self.enable_3840_runtime and source_shape == self.NATIVE_3840_FRAME_SHAPE:
            if not isinstance(native_frame, np.ndarray):
                if not self._missing_native_3840_reported:
                    self.logger.error(
                        "检测到原生 3840x2160 客户端区，但原生帧不可用；"
                        "本帧不会回退到 2560 模型。"
                    )
                    self._missing_native_3840_reported = True
                return
            self._log_diagnostic(
                "route_3840",
                "warning",
                "[HandlerDiag] 3840 Runtime 已进入: canonical=%s %s, native=%s %s",
                getattr(frame, "shape", None),
                getattr(frame, "dtype", None),
                getattr(native_frame, "shape", None),
                getattr(native_frame, "dtype", None),
            )
            self._process_3840_frame(frame, native_frame, now=now)
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

    def _process_3840_frame(self, canonical_frame, native_frame, *, now=None):
        """Route a confirmed native 3840 frame without any 2560 fallback."""
        with self._state_lock:
            self._latest_3840_diagnostics.update(
                {
                    "route_reached": True,
                    "canonical_frame_shape": tuple(canonical_frame.shape),
                    "native_frame_shape": tuple(native_frame.shape),
                }
            )
        if self.runtime_router is None:
            self.logger.error(
                "3840 Runtime 已启用但未初始化；不会静默回退到 2560 模型。"
            )
            return
        current_time = time.perf_counter() if now is None else float(now)
        count_due = self._is_due(
            current_time,
            self._last_count_update,
            self.COUNT_INTERVAL_SECONDS,
        )
        status_due = self._is_due(
            current_time,
            self._last_status_update,
            self.STATUS_INTERVAL_SECONDS,
        )
        if not count_due and not status_due:
            return

        with self._state_lock:
            needs_initialization = (
                self._current_ui_profile is None
                or self._detected_count_color is None
            )
        if needs_initialization:
            if count_due:
                self._last_count_update = current_time
                started = time.perf_counter()
                self._detect_and_set_ui_state_3840(
                    canonical_frame,
                )
                self._record_timing(
                    "count",
                    (time.perf_counter() - started) * 1000.0,
                )
                self._last_status_update = current_time
            self._update_latest_result()
            return

        rois = self._resolved_rois(self._current_ui_profile)
        inference_succeeded = False
        if count_due:
            self._last_count_update = current_time
            started = time.perf_counter()
            try:
                count = self.runtime_router.recognize_count_canonical_3840(
                    canonical_frame,
                    count_rect=rois["count"],
                    count_color_profile=self._detected_count_color,
                )
            except Exception:
                self.logger.exception(
                    "3840 Count Runtime 执行失败；本帧不会回退到 2560 模型。"
                )
            else:
                inference_succeeded = True
                if count.value is not None and not self._is_valid_count(count.value):
                    self.logger.error(
                        "3840 Count Runtime 返回非法值: %r", count.value
                    )
                    self._set_latest_count(None)
                else:
                    self._set_latest_count(
                        int(count.value) if count.value is not None else None
                    )
            finally:
                self._record_timing(
                    "count", (time.perf_counter() - started) * 1000.0
                )
        if status_due:
            self._last_status_update = current_time
            started = time.perf_counter()
            try:
                status = self.runtime_router.recognize_status_canonical_3840(
                    canonical_frame,
                    time_rect=rois["time"],
                    paused_rect=rois["paused"],
                )
            except Exception:
                self.logger.exception(
                    "3840 Time/Paused Runtime 执行失败；本帧不会回退到 2560 模型。"
                )
            else:
                inference_succeeded = True
                self._apply_time_paused_result(
                    status.production_time_first_time,
                    status.production_time_first_paused,
                    source="3840",
                )
            finally:
                self._record_timing(
                    "status", (time.perf_counter() - started) * 1000.0
                )
        if not inference_succeeded:
            return
        self._update_latest_result()

    @staticmethod
    def _is_due(now, last_update, interval):
        return last_update is None or now - last_update >= interval

    def _resolved_rois(self, ui_profile):
        return {
            task_id: self._ui_geometry.resolved_task(task_id, ui_profile)[1]
            for task_id in ("count", "time", "paused")
        }

    @staticmethod
    def _roi_diagnostic(rect):
        return (rect.x, rect.y, rect.right, rect.bottom)

    def _scan_ui_profile_candidates(self, frame, count_reader):
        """Use shared HSV filtering and Count confirmation for every runtime."""

        candidates = []
        scans = {}
        for ui_profile in self._ordered_ui_profiles():
            rois = self._resolved_rois(ui_profile)
            probe_pixels = self._count_probe_color_pixels(frame, ui_profile)
            hsv_candidate = (
                sum(probe_pixels.values()) > self.COUNT_PROBE_MIN_PIXELS
                or ui_profile == self._diagnostic_ui_profile_override
            )
            scan = {
                "offset": int(self._ui_geometry.ui_offsets[ui_profile]),
                "rois": {
                    task_id: self._roi_diagnostic(rect)
                    for task_id, rect in rois.items()
                },
                "hsv_count_probe_pixels": dict(probe_pixels),
                "hsv_candidate": bool(hsv_candidate),
                "probe_color": self._select_count_color_from_probe(probe_pixels),
                "per_color_count_results": {},
            }
            scans[ui_profile] = scan
            if not hsv_candidate:
                continue
            for color_profile in self.COUNT_COLOR_PROFILES:
                try:
                    evidence = count_reader(ui_profile, color_profile, rois)
                except Exception:
                    self.logger.exception(
                        "UI Profile Count 候选探测失败: profile=%s, color=%s",
                        ui_profile,
                        color_profile,
                    )
                    raise
                count = evidence.get("count")
                present = bool(evidence.get("present"))
                scan["per_color_count_results"][color_profile] = {
                    "count": count,
                    "present": present,
                    "score": evidence.get("score"),
                    "raw_prediction": evidence.get("raw_prediction"),
                }
                if present and self._is_valid_count(count):
                    candidates.append((ui_profile, color_profile, int(count)))
                elif count is not None and not self._is_valid_count(count):
                    self.logger.error(
                        "Count OCR 违反输出 contract: profile=%s, color=%s, value=%r",
                        ui_profile,
                        color_profile,
                        count,
                    )
        return candidates, scans

    def _detect_and_set_ui_state_3840(self, canonical_frame):
        """Detect six shared UI profiles, then adapt their ROIs to frozen 3840 OCR."""

        previous_profile = self._last_successful_ui_profile

        def read_count(ui_profile, color_profile, rois):
            details = self.runtime_router.recognize_count_canonical_3840(
                canonical_frame,
                count_rect=rois["count"],
                count_color_profile=color_profile,
            )
            return {
                "count": details.value,
                "present": bool(details.present),
                "score": float(details.best_score),
                "raw_prediction": details.raw_prediction,
            }

        try:
            candidates, scans = self._scan_ui_profile_candidates(
                canonical_frame,
                read_count,
            )
            for ui_profile in self.UI_PROFILES:
                rois = self._resolved_rois(ui_profile)
                status = self.runtime_router.recognize_status_canonical_3840(
                    canonical_frame,
                    time_rect=rois["time"],
                    paused_rect=rois["paused"],
                )
                scans[ui_profile]["status"] = {
                    "time_present": bool(status.raw_time_presence),
                    "raw_time": status.raw_time_prediction,
                    "time": status.production_time_first_time,
                    "raw_paused": bool(status.raw_paused_prediction),
                    "paused": bool(status.production_time_first_paused),
                }
        except Exception:
            self.logger.exception(
                "3840 共享 UI Profile 探测失败；本帧不会回退到 2560 模型。"
            )
            return False

        if self._diagnostic_ui_profile_override is not None:
            candidates = [
                candidate
                for candidate in candidates
                if candidate[0] == self._diagnostic_ui_profile_override
            ]
        if self._diagnostic_count_color_override is not None:
            candidates = [
                candidate
                for candidate in candidates
                if candidate[1] == self._diagnostic_count_color_override
            ]
        selected = self._select_ui_candidate(candidates)
        selected_status = None
        if selected is not None:
            ui_profile, color_profile, count = selected
            selected_status = scans[ui_profile]["status"]
            with self._state_lock:
                self._current_ui_profile = ui_profile
                self._detected_count_color = color_profile
                self._latest_count = count
                self._last_successful_ui_profile = ui_profile
            self._apply_time_paused_result(
                selected_status["time"],
                selected_status["paused"],
                source="3840",
            )

        normal_scan = scans["Normal"]
        legacy_status = (
            selected_status
            or scans.get(self._diagnostic_ui_profile_override or "Normal", {}).get(
                "status"
            )
        )
        selected_profile = None if selected is None else selected[0]
        selected_color = None if selected is None else selected[1]
        selected_rois = (
            None if selected_profile is None else scans[selected_profile]["rois"]
        )
        with self._state_lock:
            self._latest_3840_diagnostics.update(
                {
                    "route_reached": True,
                    "original_ui_profile": previous_profile,
                    "profile_scans": copy.deepcopy(scans),
                    "candidate_results": list(candidates),
                    "selected_ui_profile": selected_profile,
                    "selected_y_offset": (
                        None
                        if selected_profile is None
                        else scans[selected_profile]["offset"]
                    ),
                    "selected_rois": copy.deepcopy(selected_rois),
                    "hsv_count_probe_pixels": copy.deepcopy(
                        normal_scan["hsv_count_probe_pixels"]
                    ),
                    "normal_hsv_candidate": bool(normal_scan["hsv_candidate"]),
                    "normal_ui_accepted": selected_profile == "Normal",
                    "selected_count_color": selected_color,
                    "raw_count": None if selected is None else selected[2],
                    "per_color_count_results": copy.deepcopy(
                        normal_scan["per_color_count_results"]
                    ),
                    "raw_time": (
                        None if legacy_status is None else legacy_status["raw_time"]
                    ),
                    "raw_time_present": (
                        False
                        if legacy_status is None
                        else legacy_status["time_present"]
                    ),
                    "raw_paused": (
                        None
                        if legacy_status is None
                        else legacy_status["raw_paused"]
                    ),
                }
            )

        scan_summary = {
            profile: {
                "offset": scan["offset"],
                "hsv": scan["hsv_count_probe_pixels"],
                "count_hits": [
                    (color, result["count"], result["score"])
                    for color, result in scan["per_color_count_results"].items()
                    if result["present"]
                ],
                "time_present": scan["status"]["time_present"],
                "paused": scan["status"]["raw_paused"],
            }
            for profile, scan in scans.items()
        }
        self._log_diagnostic(
            "initial_probe",
            "warning",
            "[HandlerDiag] 3840 UI Profile 探测: candidates=%s, selected=%s, summary=%s",
            candidates,
            selected,
            scan_summary,
        )
        if selected is None:
            self._set_latest_count(None)
            self._set_3840_blocking_condition(
                "ui_profile_ambiguous" if candidates else "ui_profile_not_confirmed"
            )
            return False

        self.logger.info(
            "3840 UI 状态探测成功: profile=%s, y_offset=%s, "
            "count_color=%s, count=%s",
            selected[0],
            scans[selected[0]]["offset"],
            selected[1],
            selected[2],
        )
        return True

    def _count_probe_color_pixels(self, frame, ui_profile):
        count_rect = self._resolved_rois(ui_profile)["count"]
        roi = frame[
            count_rect.y : count_rect.bottom,
            count_rect.x : count_rect.right,
        ]
        if roi.size == 0:
            return {color: 0 for color in self.COUNT_COLOR_PROFILES}
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        return {
            color: int(cv2.countNonZero(cv2.inRange(hsv, lower, upper)))
            for color, (lower, upper) in zip(
                self.COUNT_COLOR_PROFILES,
                self._count_probe_ranges,
            )
        }

    def _select_count_color_from_probe(self, probe_pixels):
        if not probe_pixels:
            return None
        maximum = max(probe_pixels.values())
        if maximum <= self.COUNT_PROBE_MIN_PIXELS:
            return None
        winners = [
            color for color, pixels in probe_pixels.items() if pixels == maximum
        ]
        return winners[0] if len(winners) == 1 else None

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
        def read_count(ui_profile, color_profile, _rois):
            count = self._timed_recognize_count(
                frame,
                ui_profile=ui_profile,
                color_profile=color_profile,
            )
            valid = self._is_valid_count(count)
            return {
                "count": count,
                "present": valid,
                "score": None,
                "raw_prediction": f"c{int(count)}" if valid else None,
            }

        try:
            candidates, _scans = self._scan_ui_profile_candidates(
                frame,
                read_count,
            )
        except Exception:
            return False

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
        return (
            sum(self._count_probe_color_pixels(frame, ui_profile).values())
            > self.COUNT_PROBE_MIN_PIXELS
        )

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

        self._apply_time_paused_result(time_value, paused, source="新版")

    def _apply_time_paused_result(self, time_value, paused, *, source):
        """Apply mutually exclusive OCR values to the unchanged state contract."""

        if time_value is not None:
            normalized_time = self._normalize_time_value(time_value)
            if normalized_time is None:
                self.logger.error("%s Time OCR 返回非法 MSS 值: %r", source, time_value)
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
            self.logger.error("%s Paused OCR 返回非法值: %r", source, paused)
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
            self._log_diagnostic(
                "publish_blocked_count_none",
                "warning",
                "[PublishDiag] 结果暂不发布: Count=None, profile=%r, color=%r, "
                "raw_time=%r, raw_paused=%r",
                self._current_ui_profile,
                self._detected_count_color,
                latest_time,
                latest_paused,
            )
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
            self.logger.warning("[PublishDiag] 最新状态已生成: %s", parsed)
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

    def get_runtime_diagnostics(self):
        """Return a copy of the latest 3840 routing/initialization diagnostics."""

        with self._state_lock:
            result = copy.deepcopy(self._latest_3840_diagnostics)
            result.update(
                {
                    "runtime_enabled": self.enable_3840_runtime,
                    "handler_running_flag": bool(self._running),
                    "worker_alive": bool(
                        self._running_thread is not None
                        and self._running_thread.is_alive()
                    ),
                    "handler_running": bool(
                        self._running_thread is not None
                        and self._running_thread.is_alive()
                    ),
                    "ui_profile": self._current_ui_profile,
                    "count_color": self._detected_count_color,
                    "latest_count": self._latest_count,
                    "latest_time": self._latest_time,
                    "latest_paused": self._latest_paused,
                }
            )
        return result

    def _set_3840_blocking_condition(self, condition):
        with self._state_lock:
            if self._latest_3840_diagnostics["first_blocking_condition"] is None:
                self._latest_3840_diagnostics["first_blocking_condition"] = condition

    def _log_diagnostic(self, key, level, message, *args):
        now = time.monotonic()
        previous = self._diagnostic_log_times.get(key)
        if (
            previous is not None
            and now - previous < self.DIAGNOSTIC_LOG_INTERVAL_SECONDS
        ):
            return
        self._diagnostic_log_times[key] = now
        getattr(self.logger, level)(message, *args)

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
            self._unsupported_3840_ui_profile_reported = False
            self._missing_native_3840_reported = False
            self._latest_3840_diagnostics = {
                "route_reached": False,
                "original_ui_profile": None,
                "profile_scans": {},
                "candidate_results": [],
                "selected_ui_profile": None,
                "selected_y_offset": None,
                "selected_rois": None,
                "hsv_count_probe_pixels": None,
                "normal_hsv_candidate": None,
                "normal_ui_accepted": None,
                "selected_count_color": None,
                "raw_count": None,
                "per_color_count_results": {},
                "raw_time": None,
                "raw_time_present": None,
                "raw_paused": None,
                "first_blocking_condition": None,
            }
        with self._result_lock:
            self._latest_result = None
