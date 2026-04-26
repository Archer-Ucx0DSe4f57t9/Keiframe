import math
import os

import cv2
from PyQt5.QtCore import Qt

from src import config
from src.game_state_service import state
from src.output.message_presenter import MessagePresenter
from src.utils.fileutil import get_resources_dir
from src.utils.logging_util import get_logger
from src.utils.window_utils import is_game_active, get_sc2_window_geometry


class ArtifactNotifier:
    """
    神器就绪提示模块

    规则整理：

    1. 初始激活阶段
       - reset 后先进入 VALIDATING
       - 激活条件：至少 3 个不同游戏秒检测到 idle（紫蓝色）
       - 这一步【无视英雄头像】，只看 idle 颜色
       - 若激活失败，则本局禁用，直到再次 reset

    2. 激活通过后的所有 idle / not_idle 判断
       - 无论是普通图像模式、定时模式、还是 force recovery
       - 都必须先检测到英雄存活头像（zeratul_alive.png）
       - 若未检测到头像，则本秒跳过 idle / not_idle 状态判断
       - 下一个游戏秒再重新尝试检测头像

    3. 普通图像模式
       - 激活通过后，若未开启定时模式，则按 idle -> not_idle 变化触发
       - 提示显示后，重新回到 idle 时隐藏
       - 随后进入冷却

    4. 定时模式
       - 激活通过后，先等待一次 not_idle -> idle 作为锚点
       - 从锚点开始计时
       - 若配置了提前倒计时，则在到时前 N 秒显示“神器即将{time}”
       - 到时后显示“神器已经就绪”
       - 若提示后 30 秒内仍未出现 not_idle，则关闭提示，并在 reset 前不再触发定时提醒
       - 若提示后已出现 not_idle，则在再次回到 idle 时隐藏，并重新进入下一轮定时等待

    5. force recovery（保底恢复）
       - 该接口供快捷键/UI 手动触发
       - 触发后无视初始激活结果，直接进入保底检测
       - 但【仍然受英雄头像门控限制】
       - 最多持续 180 游戏秒
       - 若第一次有效 idle -> not_idle 出现，则触发第一轮神器提醒
       - 第一轮触发后，关闭保底限时逻辑，并根据当前配置回到普通图像模式或定时模式
       - 若 180 游戏秒内始终未出现有效触发，则本次保底检测结束，直到再次手动触发
    """

    STATE_WAITING = "waiting_new_game"
    STATE_VALIDATING = "validating_idle_window"
    STATE_MONITORING = "monitoring"
    STATE_TIMED_WAITING = "timed_waiting_after_idle_anchor"
    STATE_TIMED_COUNTDOWN = "timed_countdown"
    STATE_READY_DETECTED = "ready_detected"
    STATE_COOLDOWN = "cooldown"
    STATE_DISABLED = "disabled_until_new_game"
    STATE_FORCE_RECOVERY = "force_recovery"
    STATE_FORCE_RECOVERY_DISABLED = "force_recovery_disabled"

    # ===== 神器 idle / ready 采样参数 =====
    ARTIFACT_IDLE_X = 888
    ARTIFACT_IDLE_Y = 40

    ARTIFACT_READY_X1 = 885
    ARTIFACT_READY_X2 = 895
    ARTIFACT_READY_Y1 = 94
    ARTIFACT_READY_Y2 = 96

    # ===== 初始激活参数 =====
    # reset 后至少要累计 3 个不同游戏秒检测到 idle，才算激活神器识别
    ARTIFACT_VALIDATE_MIN_START_SECOND = 10
    ARTIFACT_REQUIRED_IDLE_HITS = 3

    # ===== 普通图像模式参数 =====
    # 连续多少个游戏秒检测到 not idle 才触发
    ARTIFACT_NOT_IDLE_TRIGGER_SECONDS = 1

    # ===== 定时模式参数 =====
    # 只有当该值位于 [110, 180] 内时，启用定时模式
    ARTIFACT_TIMED_TRIGGER_SECONDS = 100

    # 定时模式下，提示触发后若在该秒数内仍未出现 not idle，则关闭本轮提示
    ARTIFACT_TIMED_TRIGGER_NO_NOT_IDLE_TIMEOUT_SECONDS = 30

    # 定时模式下，提前多少秒开始显示倒计时
    ARTIFACT_TIMED_COUNTDOWN_ADVANCE_SECONDS = 15

    # 定时模式倒计时文案
    ARTIFACT_TIMED_COUNTDOWN_TEXT = "{time}秒后神器就绪"

    # ===== 英雄头像识别参数 =====
    # 神器相关状态判断必须检测到英雄存活头像后才继续
    ARTIFACT_HERO_ICON_SEARCH_PADDING = 6
    ARTIFACT_HERO_ICON_MATCH_THRESHOLD = 0.82
    ARTIFACT_HERO_ICON_TEMPLATE = "zeratul_alive.png"
    # 两种 UI 状态下头像左上角基准位置（1920 基准）
    ARTIFACT_HERO_ICON_BASE_POSITIONS = (
        (37, 31),  # 默认 UI
        (37, 79),  # Replay UI
    )
    ARTIFACT_HERO_ICON_BASE_SIZE = 50

    # ===== force recovery 参数 =====
    # 保底检测最长持续游戏秒数
    ARTIFACT_FORCE_RECOVERY_MAX_SECONDS = 180

    # 若手动恢复时当前为 idle，则显示一条短提示
    ARTIFACT_FORCE_RECOVERY_NOTICE_SECONDS = 10
    ARTIFACT_FORCE_RECOVERY_NOTICE_TEXT = "检测已恢复"

    # ===== 其他参数 =====
    ARTIFACT_RECOGNITION_COOLDOWN_SECONDS = 110
    ARTIFACT_ENABLE_READY_DEBUG_COMPARE = False

    # ===== 提示显示参数 =====
    ARTIFACT_ALERT_OFFSET_X = 800
    ARTIFACT_ALERT_OFFSET_Y = 120
    ARTIFACT_ALERT_HEIGHT = 40
    ARTIFACT_ALERT_FONT_SIZE = 30
    ARTIFACT_ALERT_VERTICAL_OFFSET = -10
    ARTIFACT_ALERT_TEXT = "神器已经就绪"
    ARTIFACT_ALERT_COLOR = "rgb(80,255,120)"
    ARTIFACT_ALERT_SOUND = "Artifact.mp3"
    ARTIFACT_ICON_PATH = get_resources_dir("icons", "Artifact.jpg")
    # ===== 颜色参考 =====

    # 用户给出的紫蓝参考
    ARTIFACT_IDLE_COLORS_RGB = [
        (57, 55, 106),
        (42, 45, 80),
    ]

    # 保留 ready 参考色，方便后续对比
    ARTIFACT_READY_COLORS_RGB = [
        (61, 106, 95),
        (23, 149, 112),
        (46, 109, 89),
        (8, 160, 94),
        (19, 211, 127),
        (27, 112, 78),
    ]

    ARTIFACT_IDLE_TOLERANCE = 30
    ARTIFACT_READY_TOLERANCE = 38
    ARTIFACT_READY_RATIO_THRESHOLD = 0.25



    ARTIFACT_RUNTIME_CONFIG_KEYS = (
        "ARTIFACT_TIMED_TRIGGER_SECONDS",
        "ARTIFACT_TIMED_TRIGGER_NO_NOT_IDLE_TIMEOUT_SECONDS",
        "ARTIFACT_TIMED_COUNTDOWN_ADVANCE_SECONDS",
        "ARTIFACT_TIMED_COUNTDOWN_TEXT",
        "ARTIFACT_HERO_ICON_MATCH_THRESHOLD",
        "ARTIFACT_FORCE_RECOVERY_MAX_SECONDS",
        "ARTIFACT_FORCE_RECOVERY_NOTICE_SECONDS",
        "ARTIFACT_FORCE_RECOVERY_NOTICE_TEXT",
        "ARTIFACT_ALERT_OFFSET_X",
        "ARTIFACT_ALERT_OFFSET_Y",
        "ARTIFACT_ALERT_HEIGHT",
        "ARTIFACT_ALERT_FONT_SIZE",
        "ARTIFACT_ALERT_VERTICAL_OFFSET",
        "ARTIFACT_ALERT_TEXT",
        "ARTIFACT_ALERT_COLOR",
        "ARTIFACT_ALERT_SOUND",
    )

    def __init__(self, parent=None):
        self.parent = parent
        self.logger = get_logger(__name__)

        self.message_presenter = MessagePresenter(parent, icon_path=self.ARTIFACT_ICON_PATH)
        self.message_presenter.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        self._hero_icon_template = None
        self._hero_icon_template_loaded = False
        self._hero_icon_scaled_cache = {}
        self._hero_icon_last_match = False
        self._hero_icon_missing_logged = False

        self._refresh_runtime_config()
        self.reset()

    def _refresh_runtime_config(self):
        for key in self.ARTIFACT_RUNTIME_CONFIG_KEYS:
            default_value = getattr(self.__class__, key, None)
            setattr(self, key, getattr(config, key, default_value))

    def reset(self):
        """
        新游戏开始时调用。

        说明：
        - 重新进入初始激活阶段
        - 清空定时模式、force recovery、提示显示等所有运行时状态
        """
        self._refresh_runtime_config()
        self.logger.warning("ArtifactNotifier 状态已重置。")

        self._state = self.STATE_VALIDATING
        self._last_checked_second = -1
        self._cooldown_start_time = None
        self._idle_seen_count = 0
        self._last_ready_notify_second = None

        # reset 后动态决定何时开始验证紫蓝色
        self._validation_start_second = None
        self._validation_locked = False

        # not idle 连续秒数统计（默认模式用）
        self._not_idle_streak_seconds = 0
        self._last_not_idle_second = None
        self._idle_anchor_second = None

        # 记录上一秒 idle 状态，用于检测状态转换
        self._last_is_idle = None

        # 定时模式下：提示触发后，是否已经见过一次 post-alert non-idle
        self._timed_ready_seen_non_idle = False

        # 定时模式下：本次提示开始显示的游戏秒
        self._timed_ready_alert_start_second = None
        self._timed_countdown_last_remaining = None
        self._last_trigger_source = None

        self._force_recovery_requested = False
        self._force_recovery_start_second = None
        self._force_recovery_waiting_for_idle_first = False
        self._force_recovery_notice_until_second = None
        self._current_overlay_kind = None

        self._hide_message()

    def shutdown(self):
        self._hide_message()

    def request_force_recovery(self):
        """
        请求启动保底恢复流程。

        说明：
        - 该方法供快捷键或 UI 触发
        - 为避免和当前 update_game_time 正在执行的状态切换冲突，
          这里只记录请求，真正切换到 force recovery 放到下一次 update_game_time 中执行
        """
        self._force_recovery_requested = True
        self.logger.warning("ArtifactNotifier 已收到保底重置请求。")
    
    def _start_force_recovery(self, current_second, is_idle):
        """
        真正进入 force recovery 状态。

        规则：
        - 无视初始激活结果，直接进入保底检测
        - 但仍受英雄头像门控限制
        - 若进入时当前就是 not_idle，则不立即触发，
          而是先等待其回到 idle，再等待下一次 idle -> not_idle
        - 若进入时当前为 idle，则在神器提示位置显示一条短提示，
          表示保底检测已恢复
        """
        self._force_recovery_requested = False
        self._hide_message()

        self._state = self.STATE_FORCE_RECOVERY
        self._force_recovery_start_second = current_second
        self._force_recovery_waiting_for_idle_first = (not is_idle)

        self._idle_anchor_second = None
        self._cooldown_start_time = None
        self._not_idle_streak_seconds = 0
        self._last_not_idle_second = None
        self._timed_ready_seen_non_idle = False
        self._timed_ready_alert_start_second = None
        self._timed_countdown_last_remaining = None
        self._last_trigger_source = None
        self._last_is_idle = is_idle

        if is_idle:
            self._show_force_recovery_notice(current_second)

        self.logger.warning(
            f"ArtifactNotifier 已进入保底重置模式，起始游戏秒={current_second}，"
            f"当前 is_idle={is_idle}，waiting_for_idle_first={self._force_recovery_waiting_for_idle_first}"
        )
        
        
    def _show_force_recovery_notice(self, current_second):
        """
        手动恢复且当前为 idle 时，显示一条短提示。
        该提示仅用于告诉用户：神器检测已经恢复。
        """
        self._force_recovery_notice_until_second = (
            current_second + int(self.ARTIFACT_FORCE_RECOVERY_NOTICE_SECONDS)
        )

        self._show_message(
            text=self.ARTIFACT_FORCE_RECOVERY_NOTICE_TEXT,
            color=self.ARTIFACT_ALERT_COLOR,
            sound_filename="",
            kind="force_recovery_notice"
        )

        self.logger.warning(
            f"显示 force recovery 恢复提示，持续到游戏秒 {self._force_recovery_notice_until_second}。"
        )


    def _maybe_expire_force_recovery_notice(self, current_second):
        """
        如果当前显示的是 force recovery 恢复提示，
        且已经超过持续时间，则自动隐藏。
        """
        if self._current_overlay_kind != "force_recovery_notice":
            return

        if self._force_recovery_notice_until_second is None:
            return

        if current_second >= self._force_recovery_notice_until_second:
            self._hide_message()
            self._force_recovery_notice_until_second = None
            self.logger.warning("force recovery 恢复提示已自动隐藏。")


    def update_game_time(self, game_time_seconds):
        if game_time_seconds is None:
            return

        try:
            current_second = int(float(game_time_seconds))
        except Exception:
            return

        self._refresh_runtime_config()

        # 同一游戏秒只处理一次
        if current_second == self._last_checked_second:
            return
        self._last_checked_second = current_second

        if not is_game_active():
            return

        color_rgb = self._get_current_sample_color()
        if color_rgb is None:
            return

        is_idle = self._is_idle_color(color_rgb)
        self._maybe_expire_force_recovery_notice(current_second)

        # 只有真正需要判断 idle / not_idle 变化的状态，才去做头像门控
        need_hero_gate = self._state in {
            self.STATE_MONITORING,
            self.STATE_FORCE_RECOVERY,
            self.STATE_READY_DETECTED,
        }
        hero_gate_ok = True
        if need_hero_gate:
            hero_gate_ok = self._can_judge_idle_transitions(current_second)
        
        if self._force_recovery_requested:
            self._start_force_recovery(current_second, is_idle)

        if self._state == self.STATE_DISABLED:
            return

        # ===== 冷却阶段（仅默认模式用）=====
        if self._state == self.STATE_COOLDOWN:
            if self._cooldown_start_time is not None:
                if current_second - self._cooldown_start_time >= self.ARTIFACT_RECOGNITION_COOLDOWN_SECONDS:
                    self.logger.info("ArtifactNotifier 冷却结束，恢复监控。")
                    self._state = self.STATE_MONITORING
                    self._cooldown_start_time = None

                    # 冷却结束后，重新开始统计
                    self._not_idle_streak_seconds = 0
                    self._last_not_idle_second = None
                    self._idle_anchor_second = None
            return

        self.logger.debug(
            f"[ArtifactNotifier] sec={current_second}, state={self._state}, "
            f"idle={is_idle}, hero_gate_ok={hero_gate_ok}, idle_hits={self._idle_seen_count}"
        )

        # ===== 验证阶段 =====
        if self._state == self.STATE_VALIDATING:
            self._handle_validating_state(current_second, is_idle)
            self._last_is_idle = is_idle
            return
        # ===== 保底重置阶段 =====
        if self._state == self.STATE_FORCE_RECOVERY:
          self._handle_force_recovery_state(current_second, is_idle, hero_gate_ok)
          return
      
        # ===== 正式监控阶段 =====
        if self._state == self.STATE_MONITORING:
            self._handle_monitoring_state(current_second, is_idle, hero_gate_ok)
            return

        if self._state == self.STATE_TIMED_WAITING:
            self._handle_timed_waiting_state(current_second, is_idle)
            return

        if self._state == self.STATE_TIMED_COUNTDOWN:
            self._handle_timed_countdown_state(current_second, is_idle)
            return

        if self._state == self.STATE_READY_DETECTED:
            self._handle_ready_detected_state(current_second, is_idle, hero_gate_ok)
            return

    def _handle_monitoring_state(self, current_second, is_idle, hero_gate_ok):
        is_ready = None

        if self._is_timed_trigger_mode_enabled():
            if not hero_gate_ok:
                self.logger.warning(
                    f"[定时监控] sec={current_second} 未检测到英雄存活头像，暂停 idle 状态变化判断。"
                )
                self._last_is_idle = is_idle
                return

            self._update_idle_transition_tracking(current_second, is_idle)
            self.logger.warning(
                f"[定时监控] current_second={current_second}, is_idle={is_idle}, "
                f"idle_anchor_second={self._idle_anchor_second}, state={self._state}"
            )
            self._last_is_idle = is_idle
            return

        if not hero_gate_ok:
            self.logger.warning(
                f"[图像监控] sec={current_second} 未检测到英雄存活头像，暂停 idle/not_idle 判断。"
            )
            self._last_is_idle = is_idle
            return

        if self.ARTIFACT_ENABLE_READY_DEBUG_COMPARE and not self._should_skip_ready_region_recognition(current_second):
            is_ready = self._is_ready_by_region()

        self.logger.warning(
            f"[对比用] current_second={current_second}, is_idle={is_idle}, "
            f"is_ready={is_ready}, not_idle_streak={self._not_idle_streak_seconds}, "
            f"idle_anchor_second={self._idle_anchor_second}"
        )

        self._update_not_idle_streak(current_second, is_idle)
        if self._not_idle_streak_seconds >= self.ARTIFACT_NOT_IDLE_TRIGGER_SECONDS:
            self.logger.warning(
                f"检测到 not idle 已连续 {self.ARTIFACT_NOT_IDLE_TRIGGER_SECONDS} 个游戏秒，触发神器提示。"
            )
            self._trigger_ready_alert(current_second, is_idle, trigger_source="image")
            return

        self._last_is_idle = is_idle

    def _handle_timed_waiting_state(self, current_second, is_idle):
        remaining = self._get_timed_remaining_seconds(current_second)
        if remaining is None:
            self._state = self.STATE_MONITORING
            self._last_is_idle = is_idle
            return

        advance = max(0, int(self.ARTIFACT_TIMED_COUNTDOWN_ADVANCE_SECONDS))
        if advance > 0 and 0 < remaining <= advance:
            self._state = self.STATE_TIMED_COUNTDOWN
            self._timed_countdown_last_remaining = None
            self._update_timed_countdown_message(remaining)
            self._last_is_idle = is_idle
            return

        if remaining <= 0:
            self.logger.warning(
                f"定时模式触发：距离最近一次 not idle -> idle 已达到 "
                f"{self.ARTIFACT_TIMED_TRIGGER_SECONDS} 秒，直接触发神器提示。"
            )
            self._trigger_ready_alert(current_second, is_idle, trigger_source="timed")
            return

        self.logger.warning(
            f"[定时等待] current_second={current_second}, is_idle={is_idle}, "
            f"idle_anchor_second={self._idle_anchor_second}, remaining={remaining}"
        )
        self._last_is_idle = is_idle

    def _handle_timed_countdown_state(self, current_second, is_idle):
        remaining = self._get_timed_remaining_seconds(current_second)
        if remaining is None:
            self._hide_message()
            self._state = self.STATE_MONITORING
            self._timed_countdown_last_remaining = None
            self._last_is_idle = is_idle
            return

        if remaining <= 0:
            self.logger.warning("定时倒计时结束，直接触发神器提示。")
            self._trigger_ready_alert(current_second, is_idle, trigger_source="timed")
            return

        self._update_timed_countdown_message(remaining)
        self._last_is_idle = is_idle

    def _handle_ready_detected_state(self, current_second, is_idle, hero_gate_ok):
        if self._last_trigger_source == "timed":
            self._handle_timed_ready_detected_state(current_second, is_idle, hero_gate_ok)
        else:
            self._handle_image_ready_detected_state(current_second, is_idle, hero_gate_ok)

    def _handle_image_ready_detected_state(self, current_second, is_idle, hero_gate_ok):
        if not hero_gate_ok:
            self.logger.warning(
                f"[神器提示-图像模式] sec={current_second} 未检测到英雄存活头像，暂停关闭条件判断。"
            )
            self._last_is_idle = is_idle
            return

        if not is_idle:
            self._last_is_idle = is_idle
            return

        self._hide_message()
        self._not_idle_streak_seconds = 0
        self._last_not_idle_second = None
        self._timed_countdown_last_remaining = None
        self._timed_ready_seen_non_idle = False
        self._timed_ready_alert_start_second = None

        if self._is_timed_trigger_mode_enabled():
            self._idle_anchor_second = current_second
            self._state = self.STATE_TIMED_WAITING
            self.logger.warning("图像触发的神器提示已回到 idle，切入定时模式等待下一轮。")
        else:
            self._cooldown_start_time = current_second
            self._state = self.STATE_COOLDOWN
            self._idle_anchor_second = None
            self.logger.warning(
                f"神器区域已恢复为 idle，开始冷却 {self.ARTIFACT_RECOGNITION_COOLDOWN_SECONDS} 秒，"
                f"cooldown_start={self._cooldown_start_time}"
            )

        self._last_is_idle = is_idle

    def _handle_timed_ready_detected_state(self, current_second, is_idle, hero_gate_ok):
        timeout_seconds = int(self.ARTIFACT_TIMED_TRIGGER_NO_NOT_IDLE_TIMEOUT_SECONDS)

        if not self._timed_ready_seen_non_idle:
            if (
                timeout_seconds > 0
                and self._timed_ready_alert_start_second is not None
                and (current_second - self._timed_ready_alert_start_second) >= timeout_seconds
            ):
                self._hide_message()
                self._state = self.STATE_DISABLED
                self._idle_anchor_second = None
                self._timed_ready_seen_non_idle = False
                self._timed_ready_alert_start_second = None
                self._timed_countdown_last_remaining = None
                self.logger.warning(
                    f"定时模式下，提示触发后 {timeout_seconds} 秒内仍未出现 non-idle，"
                    f"关闭提示，并在 reset 前不再触发定时提醒。"
                )
                self._last_is_idle = is_idle
                return

            if not hero_gate_ok:
                self.logger.warning(
                    f"[神器提示-定时模式] sec={current_second} 未检测到英雄存活头像，"
                    f"仅保留 30 秒超时检查，不判断 non-idle/idle 变化。"
                )
                self._last_is_idle = is_idle
                return

            if not is_idle:
                self._timed_ready_seen_non_idle = True
                self.logger.warning(
                    "定时模式下，提示后首次检测到 non-idle；继续保持提示，等待再次回到 idle。"
                )

            self._last_is_idle = is_idle
            return

        if not hero_gate_ok:
            self.logger.warning(
                f"[神器提示-定时模式] sec={current_second} 未检测到英雄存活头像，暂停关闭条件判断。"
            )
            self._last_is_idle = is_idle
            return

        if is_idle:
            self._hide_message()
            self._idle_anchor_second = current_second
            self._state = self.STATE_TIMED_WAITING
            self._timed_ready_seen_non_idle = False
            self._timed_ready_alert_start_second = None
            self._timed_countdown_last_remaining = None
            self.logger.warning(
                "定时模式下检测到提示后的 non-idle -> idle，隐藏提示并重新进入等待。"
            )

        self._last_is_idle = is_idle

    def _handle_force_recovery_state(self, current_second, is_idle, hero_gate_ok):
        max_seconds = int(self.ARTIFACT_FORCE_RECOVERY_MAX_SECONDS)
        if (
            self._force_recovery_start_second is not None
            and (current_second - self._force_recovery_start_second) >= max_seconds
        ):
            self._state = self.STATE_FORCE_RECOVERY_DISABLED
            self._force_recovery_start_second = None
            self._force_recovery_waiting_for_idle_first = False
            self.logger.warning(
                f"保底重置模式在 {max_seconds} 游戏秒内未等到有效的 idle -> not_idle，"
                f"本次保底检测结束。"
            )
            self._last_is_idle = is_idle
            return

        if not hero_gate_ok:
            self.logger.warning(
                f"[保底模式] sec={current_second} 未检测到英雄存活头像，暂停 idle/not_idle 判断。"
            )
            self._last_is_idle = is_idle
            return

        if self._force_recovery_waiting_for_idle_first:
            if is_idle:
                self._force_recovery_waiting_for_idle_first = False
                self._last_is_idle = True
                self.logger.warning("保底模式：当前已重新回到 idle，开始等待下一次 idle -> not_idle。")
            else:
                self._last_is_idle = False
            return

        if self._last_is_idle is None:
            self._last_is_idle = is_idle
            return

        if self._last_is_idle is True and is_idle is False:
            self.logger.warning("保底模式检测到首次有效 idle -> not_idle，触发神器提示。")
            self._force_recovery_start_second = None
            self._trigger_ready_alert(current_second, is_idle, trigger_source="image")
            return

        self._last_is_idle = is_idle

    def _trigger_ready_alert(self, current_second, is_idle, trigger_source):
        """
        统一触发神器就绪提示。

        重点：
        - 定时模式从倒计时切到正式就绪时，先隐藏当前 presenter，
          强制重新走一次 ready 的完整显示/播音路径
        - 这样语音会在“到时”这一刻就播放，而不是拖到后续 idle/not_idle 变化
        """
        if trigger_source == "timed":
            self._hide_message()

        self._show_ready_message()
        self._last_ready_notify_second = current_second
        self._last_trigger_source = trigger_source
        self._state = self.STATE_READY_DETECTED
        self._timed_countdown_last_remaining = None

        if trigger_source == "timed":
            self._timed_ready_alert_start_second = current_second
            self._timed_ready_seen_non_idle = (not is_idle)
        else:
            self._timed_ready_alert_start_second = None
            self._timed_ready_seen_non_idle = False

        self._last_is_idle = is_idle

    def _update_timed_countdown_message(self, remaining):
        """
        定时模式提前倒计时显示。
        同一秒只刷新一次，避免重复刷消息。
        """
        if remaining == self._timed_countdown_last_remaining:
            return

        self._timed_countdown_last_remaining = remaining
        text = str(self.ARTIFACT_TIMED_COUNTDOWN_TEXT).format(time=remaining)
        self._show_message(
            text=text,
            color=self.ARTIFACT_ALERT_COLOR,
            sound_filename="",
            kind="timed_countdown",
        )
        self.logger.warning(f"定时倒计时显示：{text}")

    def _get_timed_remaining_seconds(self, current_second):
        if self._idle_anchor_second is None:
            return None
        trigger_seconds = int(self.ARTIFACT_TIMED_TRIGGER_SECONDS)
        elapsed = current_second - self._idle_anchor_second
        return trigger_seconds - elapsed

    def _is_timed_trigger_mode_enabled(self):
        if self.ARTIFACT_TIMED_TRIGGER_SECONDS is None:
            return False
        return 110 <= int(self.ARTIFACT_TIMED_TRIGGER_SECONDS) <= 180

    @staticmethod
    def _should_skip_ready_region_recognition(current_second):
        return current_second <= 239

    def _can_judge_idle_transitions(self, current_second):
        """
        判断当前游戏秒是否允许继续做神器相关 idle / not_idle 状态判断。

        规则：
        - 初始激活阶段（VALIDATING）不走这里，直接无视头像，只看 idle 颜色
        - 一旦进入真正的神器监控流程：
          无论是普通图像模式、定时模式还是 force recovery，
          都必须检测到英雄存活头像后，才允许继续判断 idle / not_idle
        """
        return self._has_hero_alive_icon()

    def _ensure_hero_icon_template_loaded(self):
        if self._hero_icon_template_loaded:
            return self._hero_icon_template is not None

        self._hero_icon_template_loaded = True
        template_path = os.path.join(
            get_resources_dir(),
            'templates',
            'heroicons',
            self.ARTIFACT_HERO_ICON_TEMPLATE
        )

        if not os.path.exists(template_path):
            self.logger.error(f"未找到神器英雄头像模板：{template_path}")
            self._hero_icon_template = None
            return False

        self._hero_icon_template = cv2.imread(template_path, cv2.IMREAD_COLOR)
        if self._hero_icon_template is None:
            self.logger.error(f"神器英雄头像模板加载失败：{template_path}")
            return False

        self.logger.warning(f"神器英雄头像模板加载成功：{template_path}")
        return True

    def _get_scaled_hero_icon_template(self, scale_factor):
        if not self._ensure_hero_icon_template_loaded():
            return None

        cache_key = round(float(scale_factor), 4)
        if cache_key in self._hero_icon_scaled_cache:
            return self._hero_icon_scaled_cache[cache_key]

        template = self._hero_icon_template
        if template is None:
            return None

        target_w = max(1, int(round(template.shape[1] * scale_factor)))
        target_h = max(1, int(round(template.shape[0] * scale_factor)))
        scaled = cv2.resize(template, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
        self._hero_icon_scaled_cache[cache_key] = scaled
        return scaled

    def _has_hero_alive_icon(self):
        """
        检测当前画面中是否存在英雄存活头像 zeratul_alive.png。

        说明：
        - 只认这一张模板，不做多英雄扩展
        - 同时兼容两种 UI 状态：
          1) 默认 UI：左上角基准约为 (37, 31)
          2) Replay UI：左上角基准约为 (37, 39)
        - 实际匹配区域会在 50x50 模板周围增加一定 padding，
          允许少量坐标抖动
        - 任意一个候选区域匹配成功，即认为头像存在
        """
        template_loaded = self._ensure_hero_icon_template_loaded()
        if not template_loaded:
            return False

        with state.screenshot_lock:
            game_screen = state.latest_screenshot
            scale_factor = state.scale_factor

        if game_screen is None:
            return False

        template = self._get_scaled_hero_icon_template(scale_factor)
        if template is None:
            return False

        tpl_h, tpl_w = template.shape[:2]
        h, w = game_screen.shape[:2]
        pad = int(round(float(self.ARTIFACT_HERO_ICON_SEARCH_PADDING) * scale_factor))
        threshold = float(self.ARTIFACT_HERO_ICON_MATCH_THRESHOLD)
        best_score = -1.0

        for base_x, base_y in self.ARTIFACT_HERO_ICON_BASE_POSITIONS:
            x1 = max(0, int(round(base_x * scale_factor)) - pad)
            y1 = max(0, int(round(base_y * scale_factor)) - pad)
            x2 = min(w, int(round((base_x + self.ARTIFACT_HERO_ICON_BASE_SIZE) * scale_factor)) + pad)
            y2 = min(h, int(round((base_y + self.ARTIFACT_HERO_ICON_BASE_SIZE) * scale_factor)) + pad)

            if x2 - x1 < tpl_w or y2 - y1 < tpl_h:
                continue

            roi = game_screen[y1:y2, x1:x2]
            if roi.size == 0:
                continue

            result = cv2.matchTemplate(roi, template, cv2.TM_CCOEFF_NORMED)
            score = float(result.max()) if result.size else -1.0
            best_score = max(best_score, score)

            if score >= threshold:
                self._hero_icon_last_match = True
                self._hero_icon_missing_logged = False
                self.logger.debug(
                    f"检测到英雄存活头像，base=({base_x},{base_y}), score={score:.3f}, threshold={threshold:.3f}"
                )
                return True

        self._hero_icon_last_match = False
        if not self._hero_icon_missing_logged:
            self.logger.warning(
                f"未检测到英雄存活头像，best_score={best_score:.3f}, threshold={threshold:.3f}"
            )
            self._hero_icon_missing_logged = True

        return False

    def _init_validation_start_second_if_needed(self, current_second):
        """按当前游戏时间动态确定紫蓝色验证起点。"""
        if self._validation_start_second is not None:
            return

        if current_second <= self.ARTIFACT_VALIDATE_MIN_START_SECOND:
            self._validation_start_second = self.ARTIFACT_VALIDATE_MIN_START_SECOND
        else:
            self._validation_start_second = current_second

        self.logger.warning(
            f"ArtifactNotifier 验证起始秒已设定为 {self._validation_start_second} "
            f"(当前游戏时间={current_second})"
        )

    def _update_not_idle_streak(self, current_second, is_idle):
        """
        默认模式：
        连续 N 个游戏秒检测到 not idle 才算成立。
        """
        if is_idle:
            self._not_idle_streak_seconds = 0
            self._last_not_idle_second = None
            self.logger.warning("ArtifactNotifier 当前为 idle，not idle 连续秒数已清零。")
            return

        if self._last_not_idle_second is None:
            self._not_idle_streak_seconds = 1
        elif current_second == self._last_not_idle_second + 1:
            self._not_idle_streak_seconds += 1
        else:
            self._not_idle_streak_seconds = 1

        self._last_not_idle_second = current_second
        self.logger.warning(f"ArtifactNotifier not idle 连续秒数 = {self._not_idle_streak_seconds}")

    def _update_idle_transition_tracking(self, current_second, is_idle):
        """
        记录 idle / not idle 状态转换。

        重点：
        - 只在 MONITORING 阶段使用
        - 检测到 not idle -> idle 时，记录一个“idle 锚点”
        - 定时模式将切换到等待阶段，基于这个锚点计时
        """
        if self._last_is_idle is None:
            self._last_is_idle = is_idle
            return

        # 检测到 not idle -> idle
        if self._last_is_idle is False and is_idle is True:
            self._idle_anchor_second = current_second
            self._state = self.STATE_TIMED_WAITING
            self._timed_countdown_last_remaining = None
            self.logger.warning(
                f"检测到 not idle -> idle，记录 idle_anchor_second = {self._idle_anchor_second}，"
                f"进入 {self.STATE_TIMED_WAITING}。"
            )

    def _handle_validating_state(self, current_second, is_idle):
        if self._validation_locked:
            return

        self._init_validation_start_second_if_needed(current_second)
        if current_second < self._validation_start_second:
            return

        if is_idle:
            self._idle_seen_count += 1
            self.logger.warning(
                f"ArtifactNotifier 验证阶段检测到紫蓝色，第 {self._idle_seen_count} 次。"
            )

            if self._idle_seen_count >= self.ARTIFACT_REQUIRED_IDLE_HITS:
                self._state = self.STATE_MONITORING
                self.logger.warning("ArtifactNotifier 验证通过，进入正式监控。")
            return

        if self._idle_seen_count < self.ARTIFACT_REQUIRED_IDLE_HITS:
            self._validation_locked = True
            self._state = self.STATE_DISABLED
            self.logger.warning(
                "ArtifactNotifier 验证失败：未达到 3 次紫蓝色检测，本局在 reset 前不启用。"
            )

    def _get_current_sample_color(self):
        with state.screenshot_lock:
            game_screen = state.latest_screenshot
            scale_factor = state.scale_factor

        if game_screen is None:
            return None

        h, w = game_screen.shape[:2]
        x = int(self.ARTIFACT_IDLE_X * scale_factor)
        y = int(self.ARTIFACT_IDLE_Y * scale_factor)

        if x < 0 or y < 0 or x >= w or y >= h:
            self.logger.debug(f"ArtifactNotifier 检测点越界: ({x}, {y}), screen=({w}, {h})")
            return None

        x0 = max(0, x - 1)
        y0 = max(0, y - 1)
        x1 = min(w, x + 2)
        y1 = min(h, y + 2)

        roi = game_screen[y0:y1, x0:x1]
        if roi.size == 0:
            return None

        mean_bgr = roi.mean(axis=(0, 1))
        b, g, r = mean_bgr
        return (int(r), int(g), int(b))

    def _show_ready_message(self):
        """显示正式的神器就绪提示。"""
        self._show_message(
            text=self.ARTIFACT_ALERT_TEXT,
            color=self.ARTIFACT_ALERT_COLOR,
            sound_filename=self.ARTIFACT_ALERT_SOUND,
            kind="ready",
        )

    def _show_message(self, text, color, sound_filename="", kind="generic"):
        """
        通用消息显示函数。

        kind 用途：
        - force_recovery_notice：保底恢复短提示
        - timed_countdown：定时模式提前倒计时
        - ready：正式神器就绪提示
        - generic：其他
        """
        sc2_rect = get_sc2_window_geometry()
        if not sc2_rect:
            self.logger.warning("ArtifactNotifier 无法获取游戏窗口位置，跳过提示。")
            return

        sc2_x, sc2_y, sc2_width, _ = sc2_rect
        msg_x = sc2_x + int(self.ARTIFACT_ALERT_OFFSET_X)
        msg_y = sc2_y + int(self.ARTIFACT_ALERT_OFFSET_Y)
        msg_w = sc2_width
        msg_h = int(self.ARTIFACT_ALERT_HEIGHT)

        self.logger.warning(
            f"ArtifactNotifier 显示位置 x={msg_x}, y={msg_y}, w={msg_w}, h={msg_h}, text={text}, kind={kind}"
        )

        try:
            self.message_presenter.setAttribute(Qt.WA_TransparentForMouseEvents, True)

            # 消息类型切换，或本次需要播音时，强制重新走一次 show 路径
            refresh_show = (self._current_overlay_kind != kind) or bool(sound_filename)
            if refresh_show and self.message_presenter.isVisible():
                self.message_presenter.hide()

            if self.message_presenter.x() != msg_x or self.message_presenter.y() != msg_y:
                self.message_presenter.move(msg_x, msg_y)

            self.message_presenter.resize(msg_w, msg_h)
            self.message_presenter.setFixedHeight(msg_h)

            # 尽量保持和其他 message_presenter 一致的图标/背景资源路径
            if hasattr(self.message_presenter, "icon_path"):
                icon_path = self.ARTIFACT_ICON_PATH
                if not icon_path or not os.path.exists(icon_path):
                    icon_path = "Artifact.jpg"
                self.message_presenter.icon_path = icon_path

            self.message_presenter.update_message(
                text,
                color,
                x=msg_x,
                y=msg_y,
                width=msg_w,
                height=msg_h,
                font_size=int(self.ARTIFACT_ALERT_FONT_SIZE),
                sound_filename=sound_filename or "",
                vertical_offset=int(self.ARTIFACT_ALERT_VERTICAL_OFFSET),
            )
            self.message_presenter.show()
            self.message_presenter.raise_()
            self._current_overlay_kind = kind

        except Exception as e:
            self.logger.error(f"ArtifactNotifier 显示提示失败: {e}")
    
    def _hide_message(self):
        """隐藏当前提示，并清空当前覆盖层类型。"""
        try:
            if self.message_presenter and self.message_presenter.isVisible():
                self.message_presenter.hide()
        except Exception:
            pass
        finally:
            self._current_overlay_kind = None
    
    def _ready_region_hit_ratio(self):
        with state.screenshot_lock:
            game_screen = state.latest_screenshot
            scale_factor = state.scale_factor

        if game_screen is None:
            return None

        h, w = game_screen.shape[:2]
        x1 = int(self.ARTIFACT_READY_X1 * scale_factor)
        x2 = int(self.ARTIFACT_READY_X2 * scale_factor)
        y1 = int(self.ARTIFACT_READY_Y1 * scale_factor)
        y2 = int(self.ARTIFACT_READY_Y2 * scale_factor)

        if x2 < x1:
            x1, x2 = x2, x1
        if y2 < y1:
            y1, y2 = y2, y1

        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(w - 1, x2)
        y2 = min(h - 1, y2)

        if x1 > x2 or y1 > y2:
            return None

        roi = game_screen[y1:y2 + 1, x1:x2 + 1]
        if roi.size == 0:
            return None

        b = roi[:, :, 0]
        g = roi[:, :, 1]
        r = roi[:, :, 2]
        ready_mask = (
            (r >= 0) & (r <= 34) &
            (g >= 85) & (g <= 105) &
            (b >= 56) & (b <= 76)
        )

        hit_count = int(ready_mask.sum())
        total_count = int(ready_mask.size)
        ratio = hit_count / total_count if total_count > 0 else 0.0
        self.logger.warning(
            f"Artifact ready ROI hit_count={hit_count}, total={total_count}, ratio={ratio:.2f}"
        )
        return ratio

    def _is_ready_by_region(self):
        ratio = self._ready_region_hit_ratio()
        if ratio is None:
            return False
        return ratio >= self.ARTIFACT_READY_RATIO_THRESHOLD

    def _is_idle_color(self, color):
        return self._is_similar_to_any(color, self.ARTIFACT_IDLE_COLORS_RGB, self.ARTIFACT_IDLE_TOLERANCE)

    def _is_ready_color(self, color):
        r, g, b = color
        if self._is_idle_color(color):
            return False
        if not (g >= 80 and g > r + 20 and g > b + 12):
            return False
        if self._is_similar_to_any(color, self.ARTIFACT_READY_COLORS_RGB, self.ARTIFACT_READY_TOLERANCE):
            return True
        return False

    @staticmethod
    def _color_distance(c1, c2):
        return math.sqrt(
            (c1[0] - c2[0]) ** 2 +
            (c1[1] - c2[1]) ** 2 +
            (c1[2] - c2[2]) ** 2
        )

    def _is_similar_to_any(self, color, ref_colors, tolerance):
        for ref in ref_colors:
            if self._color_distance(color, ref) <= tolerance:
                return True
        return False