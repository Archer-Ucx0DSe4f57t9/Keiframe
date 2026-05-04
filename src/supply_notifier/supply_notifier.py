# src/supply_notifier.py
# -*- coding: utf-8 -*-
"""
SupplyNotifier

用途：
- 每个游戏秒读取右上角人口 current/max。
- 4 分钟前，当 max - current <= 2，且 max 不属于排除上限时，在人口 ROI 下方显示“建造补给”。
- 4 分钟后，当 max - current <= 4，且 max 不属于排除上限时，在人口 ROI 下方显示“建造补给”。
- 消息颜色每 1 游戏秒在白色/红色之间切换。
- 条件持续满足超过/达到配置秒数后，播放 notify_more_supplies.mp3。
- 一旦识别失败或条件不满足，立即隐藏消息并重置播报状态。

依赖：
- src.supply_notifier.white_supply_recognizer.WhiteSupplyRecognizer
- src.output.message_presenter.MessagePresenter
"""

from __future__ import annotations

from typing import Optional, Tuple

from PyQt5.QtCore import Qt

from src import config
from src.game_state_service import state
from src.output.message_presenter import MessagePresenter
from src.supply_notifier.white_supply_recognizer import WhiteSupplyRecognizer
from src.utils.logging_util import get_logger
from src.utils.window_utils import get_sc2_window_geometry, is_game_active


class SupplyNotifier:
    """人口不足提示模块。"""

    # ===== 功能开关 =====
    SUPPLY_ALERT_ENABLED = True  # 总开关；False 时完全关闭人口提醒。

    # ===== 触发规则 =====
    # 早期/中后期使用不同人口余量阈值。
    # 例如 4 分钟前剩余 <=2 提醒，4 分钟后剩余 <=4 提醒。
    SUPPLY_WARNING_PHASE_SWITCH_SECONDS = 240
    SUPPLY_WARNING_REMAINING_BEFORE_SWITCH = 2
    SUPPLY_WARNING_REMAINING_AFTER_SWITCH = 4

    # 兼容旧配置：如果外部仍然只设置 SUPPLY_WARNING_REMAINING，则作为 after_switch 的 fallback。
    SUPPLY_WARNING_REMAINING = 3

    SUPPLY_EXCLUDED_MAX_VALUES = (100, 150)
    SUPPLY_MAX_ALERT_LIMIT = 190

    # 满足条件持续多少游戏秒后播放声音。
    # 例如首次满足在 10 秒，13 秒时 current_second - start_second == 3，会播放。
    SUPPLY_SOUND_AFTER_SECONDS = 3

    # 音频提醒最短间隔，单位：游戏秒。
    # 即使本轮满足 SUPPLY_SOUND_AFTER_SECONDS，也必须距离上一次播放至少这么久才会再次播放。
    SUPPLY_SOUND_MIN_INTERVAL_SECONDS = 30

    # ===== 显示内容 =====
    SUPPLY_ALERT_TEXT = "建造补给"
    SUPPLY_ALERT_COLOR_ONE = "rgb(255,255,255)"
    SUPPLY_ALERT_COLOR_TWO = "rgb(255,60,60)"
    SUPPLY_ALERT_SOUND = "Default.mp3"

    # ===== 显示位置 =====
    SUPPLY_ALERT_OFFSET_X = 1800
    SUPPLY_ALERT_OFFSET_Y = 40
    SUPPLY_ALERT_WIDTH = 90
    SUPPLY_ALERT_HEIGHT = 32
    SUPPLY_ALERT_FONT_SIZE = 20
    SUPPLY_ALERT_VERTICAL_OFFSET = -5

    # 若右对齐后仍然过界，用这个边距做窗口内限制。
    SUPPLY_ALERT_WINDOW_MARGIN = 8

    # 识别失败是否立即隐藏。按当前需求：中途一旦不满足/无法确认，就取消消息。
    SUPPLY_HIDE_ON_RECOGNITION_FAIL = True

    SUPPLY_RUNTIME_CONFIG_KEYS = (
        "SUPPLY_ALERT_ENABLED",
        "SUPPLY_WARNING_PHASE_SWITCH_SECONDS",
        "SUPPLY_WARNING_REMAINING_BEFORE_SWITCH",
        "SUPPLY_WARNING_REMAINING_AFTER_SWITCH",
        "SUPPLY_WARNING_REMAINING",
        "SUPPLY_EXCLUDED_MAX_VALUES",
        "SUPPLY_MAX_ALERT_LIMIT",
        "SUPPLY_SOUND_MIN_INTERVAL_SECONDS",
        "SUPPLY_ALERT_TEXT",
        "SUPPLY_ALERT_COLOR_ONE",
        "SUPPLY_ALERT_COLOR_TWO",
        "SUPPLY_ALERT_SOUND",
        "SUPPLY_ALERT_OFFSET_X",
        "SUPPLY_ALERT_OFFSET_Y",
        "SUPPLY_ALERT_WIDTH",
        "SUPPLY_ALERT_HEIGHT",
        "SUPPLY_ALERT_FONT_SIZE",
        "SUPPLY_ALERT_VERTICAL_OFFSET",
    )

    def __init__(self, parent=None, recognizer: Optional[WhiteSupplyRecognizer] = None):
        self.parent = parent
        self.logger = get_logger(__name__)

        self._refresh_runtime_config()

        self.message_presenter = MessagePresenter(parent)
        self.message_presenter.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        self.recognizer = recognizer or WhiteSupplyRecognizer(debug=False)

        self.reset()

    def _refresh_runtime_config(self):
        for key in self.SUPPLY_RUNTIME_CONFIG_KEYS:
            default_value = getattr(self.__class__, key, None)
            setattr(self, key, getattr(config, key, default_value))

        # 允许 config 里写 list/tuple/set，也允许写 "100,150"。
        self.SUPPLY_EXCLUDED_MAX_VALUES = self._normalize_excluded_values(
            self.SUPPLY_EXCLUDED_MAX_VALUES
        )

    @staticmethod
    def _normalize_excluded_values(value):
        if value is None:
            return set()
        if isinstance(value, str):
            result = set()
            for item in value.split(","):
                item = item.strip()
                if not item:
                    continue
                try:
                    result.add(int(item))
                except ValueError:
                    pass
            return result
        try:
            return {int(v) for v in value}
        except Exception:
            return set()


    def reset(self):
        self._refresh_runtime_config()

        self._last_checked_second = -1
        self._condition_active = False
        self._condition_start_second = None
        self._last_condition_second = None
        self._sound_played_for_current_streak = False
        self._last_sound_second = None
        self._current_overlay_visible = False
        self._last_result = None
        self._last_screen_shape = None

        self._hide_message()
        self.logger.info("SupplyNotifier 状态已重置。")

    def shutdown(self):
        self._hide_message()

    def update_game_time(self, game_time_seconds):
        if game_time_seconds is None:
            return

        try:
            current_second = int(float(game_time_seconds))
        except Exception:
            return

        self._refresh_runtime_config()

        if not bool(self.SUPPLY_ALERT_ENABLED):
            self._reset_condition_and_hide(reason="disabled")
            return

        # 同一游戏秒只处理一次。
        if current_second == self._last_checked_second:
            return
        self._last_checked_second = current_second

        if not is_game_active():
            self._reset_condition_and_hide(reason="game_not_active")
            return

        with state.screenshot_lock:
            game_screen = state.latest_screenshot
            scale_factor = state.scale_factor

        if game_screen is None:
            self._reset_condition_and_hide(reason="no_screenshot")
            return

        self._last_screen_shape = game_screen.shape[:2]
        lang = self._get_recognizer_lang()

        try:
            result = self.recognizer.recognize(
                game_screen,
                lang=lang,
                scale_factor=scale_factor,
                save_debug=False,
            )
        except Exception as e:
            self.logger.error(f"SupplyNotifier 识别人口失败: {e}", exc_info=True)
            result = None

        if not result:
            if bool(self.SUPPLY_HIDE_ON_RECOGNITION_FAIL):
                self._reset_condition_and_hide(reason="recognition_failed")
            return

        self._last_result = result
        current_supply = int(result.get("current", -1))
        max_supply = int(result.get("max", -1))

        if not self._should_show_alert(current_supply, max_supply, current_second):
            threshold = self._get_warning_remaining_threshold(current_second)
            self._reset_condition_and_hide(
                reason=f"condition_false:{current_supply}/{max_supply}, threshold={threshold}"
            )
            return

        self._handle_condition_true(current_second, result)

    def _get_recognizer_lang(self) -> str:
        """
        读取 config.current_game_language。
        zh/cn/中文 -> cn；en/英文 -> en。
        """
        value = str(getattr(config, "current_game_language", "zh") or "zh").strip().lower()
        if value.startswith("en") or value in {"english", "英文"}:
            return "en"
        return "cn"

    def _get_warning_remaining_threshold(self, current_second: int) -> int:
        """
        根据游戏时间选择人口余量提醒阈值。

        默认：
        - 4 分钟前：剩余 <= 2 提醒
        - 4 分钟后：剩余 <= 4 提醒
        """
        try:
            switch_second = int(self.SUPPLY_WARNING_PHASE_SWITCH_SECONDS)
        except Exception:
            switch_second = 240

        if current_second < switch_second:
            try:
                return int(self.SUPPLY_WARNING_REMAINING_BEFORE_SWITCH)
            except Exception:
                return 2

        try:
            return int(self.SUPPLY_WARNING_REMAINING_AFTER_SWITCH)
        except Exception:
            # 兼容旧配置。
            return int(self.SUPPLY_WARNING_REMAINING)

    def _should_show_alert(self, current_supply: int, max_supply: int, current_second: int) -> bool:
        if current_supply < 0 or max_supply <= 0:
            return False

        if max_supply in self.SUPPLY_EXCLUDED_MAX_VALUES:
            return False

        if max_supply > int(self.SUPPLY_MAX_ALERT_LIMIT):
            return False

        remaining = max_supply - current_supply
        threshold = self._get_warning_remaining_threshold(current_second)
        return remaining <= threshold

    def _handle_condition_true(self, current_second: int, result: dict):
        if not self._condition_active:
            self._condition_active = True
            self._condition_start_second = current_second
            self._last_condition_second = current_second
            self._sound_played_for_current_streak = False
            self.logger.info(
                f"SupplyNotifier 进入提示条件: {result.get('raw')}, sec={current_second}"
            )
        else:
            # 如果游戏秒跳变，重新计算本轮持续时间，避免暂停/跳秒导致误播。
            if self._last_condition_second is not None and current_second > self._last_condition_second + 2:
                self._condition_start_second = current_second
                self._sound_played_for_current_streak = False
                self.logger.info(
                    f"SupplyNotifier 检测到游戏秒跳变，重置本轮持续计时: sec={current_second}"
                )
            self._last_condition_second = current_second

        elapsed = 0
        if self._condition_start_second is not None:
            elapsed = max(0, current_second - self._condition_start_second)

        color = self._get_blink_color(current_second)

        sound_filename = ""
        if (
            not self._sound_played_for_current_streak
            and elapsed >= int(self.SUPPLY_SOUND_AFTER_SECONDS)
            and self._can_play_sound(current_second)
        ):
            sound_filename = str(self.SUPPLY_ALERT_SOUND or "")
            self._sound_played_for_current_streak = True
            self._last_sound_second = current_second
            self.logger.info(
                f"SupplyNotifier 条件持续 {elapsed} 秒，播放声音: {sound_filename}, result={result.get('raw')}"
            )

        self._show_message(result=result, color=color, sound_filename=sound_filename)

    def _can_play_sound(self, current_second: int) -> bool:
        min_interval = int(self.SUPPLY_SOUND_MIN_INTERVAL_SECONDS)
        if min_interval <= 0:
            return True
        if self._last_sound_second is None:
            return True
        return (current_second - self._last_sound_second) >= min_interval

    def _get_blink_color(self, current_second: int) -> str:
        # 每 1 游戏秒在白色和红色之间切换。
        if current_second % 2 == 0:
            return str(self.SUPPLY_ALERT_COLOR_ONE)
        return str(self.SUPPLY_ALERT_COLOR_TWO)

    def _reset_condition_and_hide(self, reason: str = ""):
        if self._condition_active or self._current_overlay_visible:
            self.logger.info(f"SupplyNotifier 取消提示: {reason}")

        self._condition_active = False
        self._condition_start_second = None
        self._last_condition_second = None
        self._sound_played_for_current_streak = False
        self._hide_message()

    def _calc_message_geometry(self, result: dict) -> Optional[Tuple[int, int, int, int]]:
        """
        计算提示窗口位置。

        与 ToastManager 保持一致：
        - SUPPLY_ALERT_OFFSET_X / SUPPLY_ALERT_OFFSET_Y 是相对游戏窗口左上角的像素坐标；
        - SUPPLY_ALERT_WIDTH / HEIGHT / FONT_SIZE 都直接使用配置值，不按分辨率额外缩放。

        这样玩家在设置里填多少，实际就尽量显示多少。
        """
        sc2_rect = get_sc2_window_geometry()
        if not sc2_rect:
            self.logger.error("SupplyNotifier 无法获取游戏窗口位置，跳过提示。")
            return None

        sc2_x, sc2_y, sc2_w, sc2_h = sc2_rect

        msg_x = sc2_x + int(self.SUPPLY_ALERT_OFFSET_X)
        msg_y = sc2_y + int(self.SUPPLY_ALERT_OFFSET_Y)
        msg_w = max(80, int(self.SUPPLY_ALERT_WIDTH))
        msg_h = max(20, int(self.SUPPLY_ALERT_HEIGHT))

        # 限制在游戏窗口内。
        margin = int(self.SUPPLY_ALERT_WINDOW_MARGIN)
        min_x = sc2_x + margin
        max_x = sc2_x + sc2_w - msg_w - margin
        min_y = sc2_y + margin
        max_y = sc2_y + sc2_h - msg_h - margin

        msg_x = max(min_x, min(max_x, msg_x))
        msg_y = max(min_y, min(max_y, msg_y))

        return msg_x, msg_y, msg_w, msg_h

    def _show_message(self, result: dict, color: str, sound_filename: str = ""):
        geometry = self._calc_message_geometry(result)
        if geometry is None:
            return

        msg_x, msg_y, msg_w, msg_h = geometry
        text = str(self.SUPPLY_ALERT_TEXT or "建造补给")
        font_size = max(8, int(self.SUPPLY_ALERT_FONT_SIZE))
        vertical_offset = int(self.SUPPLY_ALERT_VERTICAL_OFFSET)

        try:
            self.message_presenter.setAttribute(Qt.WA_TransparentForMouseEvents, True)

            # 需要播音时强制刷新 show 路径，避免 MessagePresenter 可见时不重复播放。
            if sound_filename and self.message_presenter.isVisible():
                self.message_presenter.hide()

            if self.message_presenter.x() != msg_x or self.message_presenter.y() != msg_y:
                self.message_presenter.move(msg_x, msg_y)

            self.message_presenter.resize(msg_w, msg_h)
            self.message_presenter.setFixedHeight(msg_h)


            self.message_presenter.update_message(
                text,
                color,
                x=msg_x,
                y=msg_y,
                width=msg_w,
                height=msg_h,
                font_size=font_size,
                sound_filename=sound_filename or "",
                vertical_offset=vertical_offset,
            )
            self.message_presenter.show()
            self.message_presenter.raise_()
            self._current_overlay_visible = True

        except Exception as e:
            self.logger.error(f"SupplyNotifier 显示提示失败: {e}", exc_info=True)

    def _hide_message(self):
        try:
            if self.message_presenter and self.message_presenter.isVisible():
                self.message_presenter.hide()
        except Exception:
            pass
        finally:
            self._current_overlay_visible = False
