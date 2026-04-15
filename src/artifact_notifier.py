import math

from PyQt5.QtCore import Qt

from src.game_state_service import state
from src.output.message_presenter import MessagePresenter
from src.utils.logging_util import get_logger
from src.utils.window_utils import is_game_active, get_sc2_window_geometry


class ArtifactNotifier:
    """
    神器就绪提示模块

    当前版本规则：

    1. reset 后，先进入 VALIDATING 状态
       - 如果 reset 后首次拿到的游戏时间 <= 10 秒，则等到 10 秒开始验证
       - 如果 reset 后首次拿到的游戏时间 > 10 秒，则立即开始验证
       - 验证条件：至少 3 个不同游戏秒检测到紫蓝色（idle）
       - 否则在本次 reset 前不启用

    2. 验证通过后进入 MONITORING 状态

       A. 默认模式（ARTIFACT_TIMED_TRIGGER_SECONDS 不在 [110,180] 内）：
          - 只要 not idle 连续 1 个游戏秒，就触发神器提示
          - 不再依赖 is_ready 作为触发条件

       B. 定时模式（ARTIFACT_TIMED_TRIGGER_SECONDS 在 [110,180] 内）：
          - 不再依赖 not idle 是否触发
          - 当检测到一次 not idle -> idle 转换时，记录时间点
          - 从该时间点开始计时，到达设定秒数后直接触发神器提示

    3. 进入 READY_DETECTED 后

       A. 默认模式：
          - 提示持续显示
          - 直到检测区域重新回到 idle，隐藏提示
          - 然后进入冷却

       B. 定时模式：
          - 提示持续显示
          - 直到下一次 idle -> not idle，隐藏提示
          - 然后等待下一轮 not idle -> idle 锚点重新开始计时

    4. 冷却结束后恢复 MONITORING（仅默认模式使用冷却）

    说明：
    - 坐标按 1920 基准，用 scale_factor 缩放
    - idle 判断使用单点附近 3x3 平均色
    - ready 判断逻辑仍然保留，但只在 MONITORING 阶段按需调试时才调用
    """

    # ===== 状态定义 =====
    STATE_WAITING = "waiting_new_game"
    STATE_VALIDATING = "validating_idle_window"
    STATE_MONITORING = "monitoring"
    STATE_READY_DETECTED = "ready_detected"
    STATE_COOLDOWN = "cooldown"
    STATE_DISABLED = "disabled_until_new_game"

    # ===== 神器检测相关参数 =====

    # idle 判定采样点（1920 基准坐标）
    ARTIFACT_IDLE_X = 888
    ARTIFACT_IDLE_Y = 40

    # ready 区域（1920 基准坐标）
    ARTIFACT_READY_X1 = 885
    ARTIFACT_READY_X2 = 895
    ARTIFACT_READY_Y1 = 94
    ARTIFACT_READY_Y2 = 96

    # 验证参数
    ARTIFACT_VALIDATE_MIN_START_SECOND = 10
    ARTIFACT_REQUIRED_IDLE_HITS = 3

    # 默认触发模式：not idle 连续 N 秒触发
    ARTIFACT_NOT_IDLE_TRIGGER_SECONDS = 1

    # 定时触发模式：
    # 当该值位于 [110,180] 时启用定时模式
    # 逻辑为：从 not idle -> idle 的那个时刻开始计时，到该秒数后直接触发提示
    ARTIFACT_TIMED_TRIGGER_SECONDS = 100

    # 默认模式下的冷却时间
    ARTIFACT_RECOGNITION_COOLDOWN_SECONDS = 110

    # 是否在 MONITORING 阶段做 ready 区域对比调试
    ARTIFACT_ENABLE_READY_DEBUG_COMPARE = False

    # 提示显示参数
    ARTIFACT_ALERT_OFFSET_X = 800
    ARTIFACT_ALERT_OFFSET_Y = 120
    ARTIFACT_ALERT_HEIGHT = 40
    ARTIFACT_ALERT_FONT_SIZE = 30
    ARTIFACT_ALERT_VERTICAL_OFFSET = -10
    ARTIFACT_ALERT_TEXT = "神器已经就绪"
    ARTIFACT_ALERT_COLOR = "rgb(80,255,120)"
    ARTIFACT_ALERT_SOUND = "Artifact.mp3"

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

    def __init__(self, parent=None):
        self.parent = parent
        self.logger = get_logger(__name__)

        self.message_presenter = MessagePresenter(
            parent,
            icon_path='AggressiveDeployment.png'
        )
        self.message_presenter.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        self.reset()

    def reset(self):
        """新游戏开始时调用。"""
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

        # 用于定时模式：
        # 记录最近一次 not idle -> idle 的时间
        self._idle_anchor_second = None

        # 记录上一秒 idle 状态，用于检测状态转换
        self._last_is_idle = None

        self._hide_message()

    def shutdown(self):
        """程序退出时调用。"""
        self._hide_message()

    def update_game_time(self, game_time_seconds):
        """
        外部驱动入口。
        建议在主循环的 update_game_time 里每次调用。
        """
        if game_time_seconds is None:
            return

        try:
            current_second = int(float(game_time_seconds))
        except Exception:
            return

        # 同一游戏秒只处理一次
        if current_second == self._last_checked_second:
            return
        self._last_checked_second = current_second

        # 本局已禁用，直接退出
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

        if not is_game_active():
            return

        color_rgb = self._get_current_sample_color()
        if color_rgb is None:
            return

        is_idle = self._is_idle_color(color_rgb)

        # 默认不在验证阶段和无关阶段计算 ready
        is_ready = None

        self.logger.debug(
            f"[ArtifactNotifier] sec={current_second}, state={self._state}, "
            f"color={color_rgb}, idle={is_idle}, idle_hits={self._idle_seen_count}"
        )

        # ===== 验证阶段 =====
        if self._state == self.STATE_VALIDATING:
            self._handle_validating_state(current_second, is_idle)
            self._last_is_idle = is_idle
            return

        # ===== 正式监控阶段 =====
        if self._state == self.STATE_MONITORING:
            # 仅在验证通过后，按需做 ready 对比调试
            if self.ARTIFACT_ENABLE_READY_DEBUG_COMPARE:
                is_ready = self._is_ready_by_region()

            # 先记录 idle / not idle 转换
            self._update_idle_transition_tracking(current_second, is_idle)

            self.logger.warning(
                f"[对比用] current_second={current_second}, is_idle={is_idle}, "
                f"is_ready={is_ready}, not_idle_streak={self._not_idle_streak_seconds}, "
                f"idle_anchor_second={self._idle_anchor_second}"
            )

            # ===== 定时模式 =====
            if self._is_timed_trigger_mode_enabled():
                if self._should_trigger_by_idle_anchor_time(current_second):
                    self.logger.warning(
                        f"定时模式触发：距离最近一次 not idle -> idle 已达到 "
                        f"{self.ARTIFACT_TIMED_TRIGGER_SECONDS} 秒，直接触发神器提示。"
                    )
                    self._show_ready_message()
                    self._last_ready_notify_second = current_second
                    self._state = self.STATE_READY_DETECTED
                    self._last_is_idle = is_idle
                    return

            # ===== 默认模式 =====
            else:
                self._update_not_idle_streak(current_second, is_idle)

                if self._not_idle_streak_seconds >= self.ARTIFACT_NOT_IDLE_TRIGGER_SECONDS:
                    self.logger.warning(
                        f"检测到 not idle 已连续 {self.ARTIFACT_NOT_IDLE_TRIGGER_SECONDS} 个游戏秒，触发神器提示。"
                    )
                    self._show_ready_message()
                    self._last_ready_notify_second = current_second
                    self._state = self.STATE_READY_DETECTED
                    self._last_is_idle = is_idle
                    return

            self._last_is_idle = is_idle
            return

        # ===== 已触发神器提示 =====
        if self._state == self.STATE_READY_DETECTED:
            # 无论默认模式还是定时模式，
            # 只要当前重新回到 idle，就隐藏提示
            if is_idle:
                self._hide_message()

                # 默认模式：隐藏后进入冷却
                if not self._is_timed_trigger_mode_enabled():
                    self._cooldown_start_time = current_second
                    self._state = self.STATE_COOLDOWN

                    self._not_idle_streak_seconds = 0
                    self._last_not_idle_second = None
                    self._idle_anchor_second = None

                    self.logger.warning(
                        f"神器区域已恢复为 idle，开始冷却 {self.ARTIFACT_RECOGNITION_COOLDOWN_SECONDS} 秒，"
                        f"cooldown_start={self._cooldown_start_time}"
                    )

                # 定时模式：隐藏后直接回到 MONITORING，等待下一轮 anchor
                else:
                    self._state = self.STATE_MONITORING

                    self._not_idle_streak_seconds = 0
                    self._last_not_idle_second = None
                    self._idle_anchor_second = None

                    self.logger.warning(
                        "定时模式下检测到重新回到 idle，隐藏神器提示，返回 MONITORING。"
                    )

            self._last_is_idle = is_idle
            return

    def _is_timed_trigger_mode_enabled(self):
        """
        定时模式启用条件：
        只有当用户设置时间位于 [110,180] 内时启用。
        """
        if self.ARTIFACT_TIMED_TRIGGER_SECONDS is None:
            return False
        return 110 <= int(self.ARTIFACT_TIMED_TRIGGER_SECONDS) <= 180

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

        self.logger.warning(
            f"ArtifactNotifier not idle 连续秒数 = {self._not_idle_streak_seconds}"
        )

    def _update_idle_transition_tracking(self, current_second, is_idle):
        """
        记录 idle / not idle 状态转换。

        重点：
        - 只在 MONITORING 阶段使用
        - 检测到 not idle -> idle 时，记录一个“idle 锚点”
        - 定时模式将基于这个锚点计时
        """
        if self._last_is_idle is None:
            self._last_is_idle = is_idle
            return

        # 检测到 not idle -> idle
        if self._last_is_idle is False and is_idle is True:
            self._idle_anchor_second = current_second
            self.logger.warning(
                f"检测到 not idle -> idle，记录 idle_anchor_second = {self._idle_anchor_second}"
            )

    def _should_trigger_by_idle_anchor_time(self, current_second):
        """
        定时模式：
        当最近一次 not idle -> idle 已经记录，
        且距离该锚点达到用户设定秒数时，直接触发神器提示。
        """
        if not self._is_timed_trigger_mode_enabled():
            return False

        if self._idle_anchor_second is None:
            return False

        return (current_second - self._idle_anchor_second) >= int(self.ARTIFACT_TIMED_TRIGGER_SECONDS)

    def _handle_validating_state(self, current_second, is_idle):
        """
        reset 后动态决定验证起点：
        - 若首次看到的游戏时间 <= 10，则从 10 秒开始验证
        - 若首次看到的游戏时间 > 10，则立刻开始验证

        启用条件：
        - 从验证起点开始，累计至少 3 个不同游戏秒检测到紫蓝色
        - 达到 3 次后，进入正式监控

        否则：
        - 在本次 reset 前始终不启用
        """
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
        """
        取 idle 采样点附近 3x3 区域平均色。
        返回 RGB tuple。
        """
        with state.screenshot_lock:
            game_screen = state.latest_screenshot
            scale_factor = state.scale_factor

        if game_screen is None:
            return None

        h, w = game_screen.shape[:2]

        x = int(self.ARTIFACT_IDLE_X * scale_factor)
        y = int(self.ARTIFACT_IDLE_Y * scale_factor)

        if x < 0 or y < 0 or x >= w or y >= h:
            self.logger.debug(
                f"ArtifactNotifier 检测点越界: ({x}, {y}), screen=({w}, {h})"
            )
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
        """显示神器就绪提示。"""
        sc2_rect = get_sc2_window_geometry()
        if not sc2_rect:
            self.logger.warning("ArtifactNotifier 无法获取游戏窗口位置，跳过提示。")
            return

        sc2_x, sc2_y, sc2_width, _ = sc2_rect

        msg_x = sc2_x + self.ARTIFACT_ALERT_OFFSET_X
        msg_y = sc2_y + self.ARTIFACT_ALERT_OFFSET_Y
        msg_w = sc2_width
        msg_h = self.ARTIFACT_ALERT_HEIGHT

        self.logger.warning(
            f"ArtifactNotifier 显示位置 x={msg_x}, y={msg_y}, w={msg_w}, h={msg_h}"
        )

        try:
            self.message_presenter.setAttribute(Qt.WA_TransparentForMouseEvents, True)

            if (self.message_presenter.x() != msg_x or
                    self.message_presenter.y() != msg_y):
                self.message_presenter.move(msg_x, msg_y)

            self.message_presenter.resize(msg_w, msg_h)
            self.message_presenter.setFixedHeight(msg_h)

            self.message_presenter.update_message(
                self.ARTIFACT_ALERT_TEXT,
                self.ARTIFACT_ALERT_COLOR,
                x=msg_x,
                y=msg_y,
                width=msg_w,
                height=msg_h,
                font_size=self.ARTIFACT_ALERT_FONT_SIZE,
                sound_filename=self.ARTIFACT_ALERT_SOUND,
                vertical_offset=self.ARTIFACT_ALERT_VERTICAL_OFFSET
            )

            self.message_presenter.show()
            self.message_presenter.raise_()

            self.logger.warning(
                f"message_presenter visible={self.message_presenter.isVisible()}, "
                f"pos=({self.message_presenter.x()}, {self.message_presenter.y()}), "
                f"size=({self.message_presenter.width()}x{self.message_presenter.height()})"
            )

        except Exception as e:
            self.logger.error(f"ArtifactNotifier 显示提示失败: {e}")

    def _hide_message(self):
        """隐藏神器提示。"""
        try:
            if self.message_presenter and self.message_presenter.isVisible():
                self.message_presenter.hide()
        except Exception:
            pass

    # ================== 以下是一些独立的颜色处理函数，方便后续维护 ==================

    def _ready_region_hit_ratio(self):
        """
        计算 ready 区域绿色命中率。
        当前版本保留，仅用于 MONITORING 阶段的对比调试。
        """
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
        """判断 ready 区域是否满足绿色命中率阈值。"""
        ratio = self._ready_region_hit_ratio()
        if ratio is None:
            return False
        return ratio >= self.ARTIFACT_READY_RATIO_THRESHOLD

    def _is_idle_color(self, color):
        """判断当前颜色是否接近紫蓝色 idle 状态。"""
        return self._is_similar_to_any(
            color,
            self.ARTIFACT_IDLE_COLORS_RGB,
            self.ARTIFACT_IDLE_TOLERANCE
        )

    def _is_ready_color(self, color):
        """
        判断当前颜色是否接近 ready 状态。
        当前版本保留，仅用于后续继续做 A/B 对比。
        """
        r, g, b = color

        if self._is_idle_color(color):
            return False

        if not (g >= 80 and g > r + 20 and g > b + 12):
            return False

        if self._is_similar_to_any(
            color,
            self.ARTIFACT_READY_COLORS_RGB,
            self.ARTIFACT_READY_TOLERANCE
        ):
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
