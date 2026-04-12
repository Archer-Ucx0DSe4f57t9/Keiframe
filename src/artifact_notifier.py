import math
import os
from PyQt5.QtCore import Qt, QTimer

from src.game_state_service import state
from src.output.message_presenter import MessagePresenter
from src.utils.logging_util import get_logger
from src.utils.fileutil import get_resources_dir
from src.utils.window_utils import is_game_active, get_sc2_window_geometry


class ArtifactNotifier:
    """
    神器就绪提示模块

    规则：
    1. 10~39 秒为验证窗口：
       - 每秒检查一次目标区域颜色
       - 紫蓝色累计出现至少 2 次，才认为本局可启用
       - 超过 39 秒仍未达到 2 次，本局停用，直到下一局 reset()

    2. 验证通过后进入正式监控：
       - 每秒检查一次
       - 检测到绿色 -> 播报“神器已经就绪”，播放 Artifact.mp3，显示 10 秒
       - 然后进入 READY_DETECTED 状态

    3. READY_DETECTED：
       - 等待目标区域不再是绿色
       - 一旦离开绿色，记录当前游戏时间并进入 110 秒冷却

    4. COOLDOWN：
       - 冷却 110 秒内不再检测
       - 到时后恢复监控

    说明：
    - 坐标按 1920 基准，用 scale_factor 缩放
    - 颜色判断用 3x3 小区域平均色，提高稳定性
    """

    # ===== 状态定义 =====
    STATE_WAITING = "waiting_new_game"
    STATE_VALIDATING = "validating_idle_window"
    STATE_MONITORING = "monitoring"
    STATE_READY_DETECTED = "ready_detected"
    STATE_COOLDOWN = "cooldown"
    STATE_DISABLED = "disabled_until_new_game"

    # ===== 基础参数 =====
    BASE_X = 888
    BASE_Y = 40
    READY_X1 = 885
    READY_X2 = 895
    READY_Y1 = 94
    READY_Y2 = 96

    VALIDATE_MIN_START_SECOND = 10
    REQUIRED_IDLE_HITS = 3
    COOLDOWN_SECONDS = 110
    MESSAGE_SHOW_MS = 10_000

    # ===== 颜色参考 =====
    # 用户给出的紫蓝参考
    IDLE_COLORS_RGB = [
        (57, 55, 106),
        (42, 45, 80),
    ]

    # 按图片2/3估计的绿色参考，可后续微调
    READY_COLORS_RGB = [
        (61, 106, 95),
        (23, 149, 112),
        (46, 109, 89),
        (8, 160, 94),
        (19, 211, 127),
        (27, 112, 78),
    ]

    IDLE_TOLERANCE = 30
    READY_TOLERANCE = 38

    def __init__(self, parent=None):
        self.parent = parent
        self.logger = get_logger(__name__)

        icon_path = os.path.join(get_resources_dir(), 'icons', 'mutators', 'AggressiveDeployment.png')
        self.message_presenter = MessagePresenter(parent, icon_path=icon_path)
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
        self._validation_start_second = None
        self._validation_locked = False   # 一旦判定本局不启用，就锁死到下次 reset
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

        # 冷却阶段只看时间
        if self._state == self.STATE_COOLDOWN:
            if self._cooldown_start_time is not None:
                if current_second - self._cooldown_start_time >= self.COOLDOWN_SECONDS:
                    self.logger.info("ArtifactNotifier 冷却结束，恢复监控。")
                    self._state = self.STATE_MONITORING
                    self._cooldown_start_time = None
            return

        # 没有激活游戏窗口时，不采样
        if not is_game_active():
            return

        color_rgb = self._get_current_sample_color()
        if color_rgb is None:
            return

        is_idle = self._is_idle_color(color_rgb)
        is_ready = self._is_ready_by_region()

        self.logger.debug(
            f"[ArtifactNotifier] sec={current_second}, state={self._state}, "
            f"color={color_rgb}, idle={is_idle}, ready={is_ready}, idle_hits={self._idle_seen_count}"
        )

        # ===== 验证阶段 =====
        if self._state == self.STATE_VALIDATING:
            self._handle_validating_state(current_second, is_idle)
            return

        # ===== 正式监控阶段 =====
        if self._state == self.STATE_MONITORING:
            if is_ready:
                self.logger.warning("检测到神器就绪区域命中率达到阈值，触发提示。")
                self._show_ready_message()
                self._last_ready_notify_second = current_second
                self._state = self.STATE_READY_DETECTED
            return

        # ===== 已发现绿色，等待其消失 =====
        if self._state == self.STATE_READY_DETECTED:
            if not is_ready:
                self._hide_message()
                self._cooldown_start_time = current_second
                self._state = self.STATE_COOLDOWN
                self.logger.warning(
                    f"神器区域已离开绿色状态，开始冷却 {self.COOLDOWN_SECONDS} 秒，"
                    f"cooldown_start={self._cooldown_start_time}"
                )
            return
          
    def _init_validation_start_second_if_needed(self, current_second):
        if self._validation_start_second is not None:
            return

        if current_second <= self.VALIDATE_MIN_START_SECOND:
            self._validation_start_second = self.VALIDATE_MIN_START_SECOND
        else:
            self._validation_start_second = current_second

        self.logger.warning(
            f"ArtifactNotifier 验证起始秒已设定为 {self._validation_start_second} "
            f"(当前游戏时间={current_second})"
        )
        
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

        # 还没到验证起点，继续等
        if current_second < self._validation_start_second:
            return

        # 已经达到启用条件，直接进入监控
        if is_idle:
            self._idle_seen_count += 1
            self.logger.warning(
                f"ArtifactNotifier 验证阶段检测到紫蓝色，第 {self._idle_seen_count} 次。"
            )

            if self._idle_seen_count >= self.REQUIRED_IDLE_HITS:
                self._state = self.STATE_MONITORING
                self.logger.warning("ArtifactNotifier 验证通过，进入正式监控。")
            return

        # 一旦开始验证后，遇到非紫蓝色，且还没攒够 3 次，就直接锁死到 reset
        if self._idle_seen_count < self.REQUIRED_IDLE_HITS:
            self._validation_locked = True
            self._state = self.STATE_DISABLED
            self.logger.warning(
                "ArtifactNotifier 验证失败：未达到 3 次紫蓝色检测，本局在 reset 前不启用。"
            )

    def _get_current_sample_color(self):
        """
        取目标点附近 3x3 区域平均色。
        返回 RGB tuple。
        """
        with state.screenshot_lock:
            game_screen = state.latest_screenshot
            scale_factor = state.scale_factor

        if game_screen is None:
            return None

        h, w = game_screen.shape[:2]

        x = int(self.BASE_X * scale_factor)
        y = int(self.BASE_Y * scale_factor)

        if x < 0 or y < 0 or x >= w or y >= h:
            self.logger.debug(
                f"ArtifactNotifier 检测点越界: ({x}, {y}), screen=({w}, {h})"
            )
            return None

        # 3x3 平均
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
      sc2_rect = get_sc2_window_geometry()
      if not sc2_rect:
          self.logger.warning("ArtifactNotifier 无法获取游戏窗口位置，跳过提示。")
          return

      sc2_x, sc2_y, sc2_width, _ = sc2_rect

      msg_x = sc2_x + 20
      msg_y = sc2_y + 280
      msg_w = sc2_width
      msg_h = 36

      self.logger.warning(f"ArtifactNotifier 显示位置 x={msg_x}, y={msg_y}, w={msg_w}, h={msg_h}")

      try:
          self.message_presenter.setAttribute(Qt.WA_TransparentForMouseEvents, True)

          if (self.message_presenter.x() != msg_x or
                  self.message_presenter.y() != msg_y):
              self.message_presenter.move(msg_x, msg_y)

          self.message_presenter.resize(msg_w, msg_h)
          self.message_presenter.setFixedHeight(msg_h)

          self.message_presenter.update_message(
              "神器已经就绪",
              "rgb(80,255,120)",
              x=msg_x,
              y=msg_y,
              width=msg_w,
              height=msg_h,
              font_size=20,
              sound_filename="Artifact.mp3",
              vertical_offset=0
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
      try:
          if self.message_presenter and self.message_presenter.isVisible():
              self.message_presenter.hide()
      except Exception:
          pass
    # ================== 以下是一些独立的颜色处理函数，方便后续维护 ==================
    
    #区域绿色命中率函数
    def _ready_region_hit_ratio(self):
      with state.screenshot_lock:
          game_screen = state.latest_screenshot
          scale_factor = state.scale_factor

      if game_screen is None:
          return None

      h, w = game_screen.shape[:2]

      x1 = int(self.READY_X1 * scale_factor)
      x2 = int(self.READY_X2 * scale_factor)
      y1 = int(self.READY_Y1 * scale_factor)
      y2 = int(self.READY_Y2 * scale_factor)

      # 防止缩放后上下/左右反转或越界
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

      # OpenCV 是 BGR，需要转成 RGB 通道理解
      b = roi[:, :, 0]
      g = roi[:, :, 1]
      r = roi[:, :, 2]

      # ready 颜色范围：
      # 基准 (24,95,66)
      # r 允许更低，兼容 y=94 时个位数
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

    # 判断 ready 区域是否满足绿色命中率阈值
    def _is_ready_by_region(self):
      ratio = self._ready_region_hit_ratio()
      if ratio is None:
          return False
      return ratio >= 0.25
    
    def _is_idle_color(self, color):
        return self._is_similar_to_any(color, self.IDLE_COLORS_RGB, self.IDLE_TOLERANCE)

    def _is_ready_color(self, color):
      r, g, b = color

      # 1. 先排除明显的紫蓝背景
      if self._is_idle_color(color):
          return False

      # 2. 必须满足绿色主导，否则直接不是 ready
      #    这样 (51, 49, 95) 这类颜色会被直接排除
      if not (g >= 80 and g > r + 20 and g > b + 12):
          return False

      # 3. 最后再做参考色匹配
      if self._is_similar_to_any(color, self.READY_COLORS_RGB, self.READY_TOLERANCE):
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