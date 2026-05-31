# src/map_handlers/map_variant_auto_resolver.py

from dataclasses import dataclass
from typing import Dict, Optional, Tuple, Set, Any

from src import game_state_service
from src.game_readers.minimap_red_dot_detector import (
    red_dot_detector,
    MinimapRedDotDetector,
)
from PyQt5.QtCore import Qt,QTimer
from src.presentation_modules.message_presenter import MessagePresenter
from src.utils.logging_util import get_logger
from src.utils.window_utils import get_sc2_window_geometry
Region = Tuple[int, int, int, int]


@dataclass(frozen=True)
class MapVariantRule:
    rule_id: str

    # 当前地图只要在这个集合内，就允许这条规则工作
    map_names: Tuple[str, ...]

    # 游戏时间窗口，单位：秒
    start_second: int
    end_second: int

    # red_dot_detector 使用现实时间作为 duration。
    # 所以这里故意比游戏窗口长，实际结束仍由游戏时间控制。
    monitor_duration_s: float

    # 小地图局部坐标，不是全屏坐标
    region: Region
    region_mode: str

    # 检测到红点时选择的地图
    present_map: str
    present_message: str

    # 检测窗口结束仍没检测到红点时选择的地图
    absent_map: str
    absent_message: str

    # detector 确认参数
    min_confirmed_frames: int = 2
    min_score: float = 0.58
    high_score: float = 0.82


RULES: Tuple[MapVariantRule, ...] = (
    MapVariantRule(
        rule_id="temple_of_the_past_red_dot_branch",
        map_names=("往日神庙-A", "往日神庙-B"),

        # 03:15 - 03:20
        start_second=3 * 60 + 15,
        end_second=3 * 60 + 20,
        monitor_duration_s=20.0,

        # 小地图尺寸是 264x259。
        # 以小地图中心为坐标轴，第三象限 = 左下区域。
        # center_x = 132, center_y ≈ 129.5
        region=(0, 130, 132, 259),
        region_mode=MinimapRedDotDetector.REGION_CENTER_IN,

        present_map="往日神庙-B",
        present_message="310波次检测到红点，保持：庙B",

        absent_map="往日神庙-A",
        absent_message="310波次未检测到红点，切换：庙A",
    ),

    MapVariantRule(
        rule_id="void_trashing_red_dot_branch",
        map_names=("虚空撕裂-左", "虚空撕裂-右"),

        # 03:00 - 03:10
        start_second=3 * 60,
        end_second=3 * 60 + 10,
        monitor_duration_s=20.0,

        # 原全屏 1920x1080 坐标：
        # 左上角 (183, 901)，尺寸 106x95
        #
        # detector 小地图基准：
        # 小地图左上角 (27, 807)，尺寸 264x259
        #
        # 换算：
        # x1 = 183 - 27 = 156
        # y1 = 901 - 807 = 94
        # x2 = 183 + 106 - 27 = 262
        # y2 = 901 + 95 - 807 = 189
        region=(156, 94, 262, 189),
        region_mode=MinimapRedDotDetector.REGION_CORE_BBOX_IN,

        present_map="虚空撕裂-左",
        present_message="3分钟检测到指定区域红点，保持：虚空撕裂A",

        absent_map="虚空撕裂-右",
        absent_message="3分钟未检测到指定区域红点，切换：虚空撕裂B",
    ),
)


class MapVariantAutoResolver:
    """
    根据小地图红点自动选择地图分支。

    只负责：
    1. 根据当前地图和游戏时间启动 monitor。
    2. 读取 red_dot_detector 的结果。
    3. 决定切换到哪个地图分支。
    4. 调用 message_presenter 提示最终选择结果。

    不负责：
    1. 红点图像识别。
    2. 表格刷新。
    3. 地图数据加载。
    """
    
    VARIANT_ALERT_OFFSET_X = 800
    VARIANT_ALERT_OFFSET_Y = 100
    VARIANT_ALERT_HEIGHT = 40
    VARIANT_ALERT_FONT_SIZE = 20
    VARIANT_ALERT_VERTICAL_OFFSET = -7
    VARIANT_ALERT_COLOR = "rgb(255,255,255)"
    VARIANT_ALERT_AUTO_HIDE_MS = 10_000

    def __init__(self, parent=None, logger=None):
        self.parent = parent
        self.window = parent
        self.logger = logger or get_logger(__name__)

        # 不在启动阶段创建 MessagePresenter，避免透明分层窗口影响主界面初始化。
        self.message_presenter = None

        self._current_overlay_kind = None
        self._variant_message_token = 0

        self.monitor_ids: Dict[str, str] = {}
        self.last_results: Dict[str, Dict[str, Any]] = {}

        self.resolved_rule_ids: Set[str] = set()

        self.disabled_by_manual: bool = False
        self.manual_disable_reason: Optional[str] = None

    def reset(self) -> None:
        """
        新游戏、离开游戏、reset_game_info 时调用。
        """
        self.stop_all_monitors()
        self.monitor_ids.clear()
        self.last_results.clear()
        self.resolved_rule_ids.clear()
        self.disabled_by_manual = False
        self.manual_disable_reason = None
        self._hide_variant_message()
        self.logger.info("[MapVariantAutoResolver] reset completed")
        
    def disable_by_manual(self, reason: str = "manual_selection") -> None:
        """
        用户手动选择 A/B 或左/右后，本局不要再自动改分支。
        """
        self.disabled_by_manual = True
        self.manual_disable_reason = reason
        self.stop_all_monitors()
        self._hide_variant_message()
        self.logger.info(
            "[MapVariantAutoResolver] disabled by manual action: %s",
            reason,
        )

    def update(self, current_seconds: int, is_in_game: bool) -> bool:
        """
        每个游戏秒调用一次。

        Returns:
            True: 本次发生了自动切图，调用方应跳过本轮 map_event_manager.update_events()
            False: 没有切图，可以继续原逻辑
        """
        if not is_in_game:
            self.stop_all_monitors()
            self._hide_variant_message()
            return False

        if self.disabled_by_manual:
            return False

        current_map = self._get_current_map_name()
        if not current_map:
            return False

        rule = self._find_rule(current_map)

        if rule is None:
            # 当前地图不是这类自动分支地图，清掉可能残留的 monitor
            self.stop_all_monitors()
            self._hide_variant_message()
            return False

        if rule.rule_id in self.resolved_rule_ids:
            return False

        # 还没到窗口
        if current_seconds < rule.start_second:
            return False

        # 超过窗口太多但还没 monitor，说明错过了，不要强行判定
        if current_seconds > rule.end_second and rule.rule_id not in self.monitor_ids:
            self.logger.debug(
                "[MapVariantAutoResolver] rule=%s skipped because window already passed",
                rule.rule_id,
            )
            self.resolved_rule_ids.add(rule.rule_id)
            return False

        # 进入窗口后启动 monitor
        if rule.rule_id not in self.monitor_ids:
            self._start_monitor(rule)

        # 先检查是否已经检测到红点。检测到红点可以提前确定。
        switched = self._try_decide_present(rule)
        if switched:
            return True

        # 窗口尚未结束，继续观察
        if current_seconds <= rule.end_second:
            return False

        # 窗口结束后仍没有红点，才判断 absent。
        return self._decide_after_window_end(rule)

    def stop_all_monitors(self) -> None:
        for rule_id, monitor_id in list(self.monitor_ids.items()):
            try:
                red_dot_detector.stop_monitor(monitor_id)
                self.logger.debug(
                    "[MapVariantAutoResolver] stopped monitor: rule=%s monitor=%s",
                    rule_id,
                    monitor_id,
                )
            except Exception:
                self.logger.exception(
                    "[MapVariantAutoResolver] failed to stop monitor: rule=%s monitor=%s",
                    rule_id,
                    monitor_id,
                )

        self.monitor_ids.clear()

    def _find_rule(self, current_map: str) -> Optional[MapVariantRule]:
        for rule in RULES:
            if current_map in rule.map_names:
                return rule
        return None

    def _get_current_map_name(self) -> Optional[str]:
        # 优先用 UI 当前值，因为自动切图最终也是 combo_box 驱动
        try:
            if hasattr(self.window, "combo_box"):
                text = self.window.combo_box.currentText()
                if text:
                    return text
        except Exception:
            pass

        return game_state_service.state.current_selected_map

    def _start_monitor(self, rule: MapVariantRule) -> None:
        monitor_id = red_dot_detector.start_monitor(
            duration_s=rule.monitor_duration_s,
            region=rule.region,
            region_mode=rule.region_mode,
            min_confirmed_frames=rule.min_confirmed_frames,
            min_score=rule.min_score,
            high_score=rule.high_score,
        )

        self.monitor_ids[rule.rule_id] = monitor_id

        self.logger.warning(
            "[MapVariantAutoResolver] monitor started: "
            "rule=%s monitor=%s window=%s-%s region=%s mode=%s",
            rule.rule_id,
            monitor_id,
            rule.start_second,
            rule.end_second,
            rule.region,
            rule.region_mode,
        )

    def _get_result(self, rule: MapVariantRule) -> Optional[Dict[str, Any]]:
        monitor_id = self.monitor_ids.get(rule.rule_id)
        if not monitor_id:
            return None

        result = red_dot_detector.get_result(monitor_id)

        if result.get("valid"):
            self.last_results[rule.rule_id] = result
        else:
            self.logger.debug(
                "[MapVariantAutoResolver] invalid detector result: "
                "rule=%s reason=%s result=%s",
                rule.rule_id,
                result.get("reason"),
                result,
            )

        return result

    def _try_decide_present(self, rule: MapVariantRule) -> bool:
        result = self._get_result(rule)
        if not result:
            return False

        if result.get("valid") and result.get("count", 0) > 0:
            return self._apply_decision(
                rule=rule,
                target_map=rule.present_map,
                message=rule.present_message,
                decision="red_dot_present",
                result=result,
            )

        return False

    def _decide_after_window_end(self, rule: MapVariantRule) -> bool:
        result = self._get_result(rule)

        # 如果当前这一秒无效，但窗口内曾经有过有效结果，用最后一次有效结果判断。
        if not result or not result.get("valid"):
            result = self.last_results.get(rule.rule_id)

        if result and result.get("valid"):
            if result.get("count", 0) > 0:
                return self._apply_decision(
                    rule=rule,
                    target_map=rule.present_map,
                    message=rule.present_message,
                    decision="red_dot_present_after_window",
                    result=result,
                )

            return self._apply_decision(
                rule=rule,
                target_map=rule.absent_map,
                message=rule.absent_message,
                decision="red_dot_absent",
                result=result,
            )

        # 整个窗口都没有有效截图，不要切图。
        self._finish_rule_without_switch(
            rule=rule,
            reason="no_valid_detector_result",
            result=result,
        )
        return False

    def _apply_decision(
        self,
        rule: MapVariantRule,
        target_map: str,
        message: str,
        decision: str,
        result: Optional[Dict[str, Any]],
    ) -> bool:
        self.resolved_rule_ids.add(rule.rule_id)
        self._stop_monitor_for_rule(rule.rule_id)

        self.logger.info(
            "[MapVariantAutoResolver] decision=%s rule=%s target=%s "
            "count=%s current_count=%s detections=%s",
            decision,
            rule.rule_id,
            target_map,
            result.get("count") if result else None,
            result.get("current_count") if result else None,
            result.get("detections") if result else None,
        )

        switched = self._switch_map(target_map)
        self._show_variant_message(message)

        return switched

    def _finish_rule_without_switch(
        self,
        rule: MapVariantRule,
        reason: str,
        result: Optional[Dict[str, Any]],
    ) -> None:
        self.resolved_rule_ids.add(rule.rule_id)
        self._stop_monitor_for_rule(rule.rule_id)

        self.logger.warning(
            "[MapVariantAutoResolver] rule finished without switch: "
            "rule=%s reason=%s result=%s",
            rule.rule_id,
            reason,
            result,
        )

        # 这里不强制 message_presenter 提示，因为没有得出选择结果。
        # 如果你希望玩家知道失败，也可以打开下面这行：
        # self._present_message("自动分支判断失败，保留当前地图配置")

    def _stop_monitor_for_rule(self, rule_id: str) -> None:
        monitor_id = self.monitor_ids.pop(rule_id, None)
        if not monitor_id:
            return

        try:
            red_dot_detector.stop_monitor(monitor_id)
        except Exception:
            self.logger.exception(
                "[MapVariantAutoResolver] failed to stop monitor: rule=%s monitor=%s",
                rule_id,
                monitor_id,
            )

    def _switch_map(self, target_map: str) -> bool:
        current_map = self._get_current_map_name()

        if current_map == target_map:
            self.logger.info(
                "[MapVariantAutoResolver] target map already selected: %s",
                target_map,
            )
            return False

        index = self.window.combo_box.findText(target_map)
        if index < 0:
            self.logger.warning(
                "[MapVariantAutoResolver] target map not found in combo_box: %s",
                target_map,
            )
            return False

        self.logger.info(
            "[MapVariantAutoResolver] switching map: %s -> %s",
            current_map,
            target_map,
        )

        # 防止 handle_map_selection 把这次自动切图误判成用户手动选择
        self.window.auto_map_variant_switching = True
        try:
            self.window.combo_box.setCurrentIndex(index)
        finally:
            self.window.auto_map_variant_switching = False

        return True

    #创建或返回 MessagePresenter 实例，确保它存在但不重复创建。
    def _ensure_message_presenter(self):
        if self.message_presenter is not None:
            return self.message_presenter

        # 先用 parent=None 更稳，避免它作为主窗口子控件参与主 UI 布局/绘制。
        self.message_presenter = MessagePresenter(None)
        self.message_presenter.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.message_presenter.hide()
        return self.message_presenter
      
    # 这个函数专门负责显示提示信息，和切图逻辑分开，方便以后调整提示时机和内容。
    def _show_variant_message(self, text, kind="map_variant"):
        sc2_rect = get_sc2_window_geometry()
        if not sc2_rect:
            self.logger.error("MapVariantAutoResolver 无法获取游戏窗口位置，跳过提示。")
            return

        presenter = self._ensure_message_presenter()

        sc2_x, sc2_y, sc2_width, _ = sc2_rect

        msg_x = sc2_x + int(self.VARIANT_ALERT_OFFSET_X)
        msg_y = sc2_y + int(self.VARIANT_ALERT_OFFSET_Y)
        msg_w = sc2_width
        msg_h = int(self.VARIANT_ALERT_HEIGHT)

        try:
            presenter.setAttribute(Qt.WA_TransparentForMouseEvents, True)

            refresh_show = self._current_overlay_kind != kind
            if refresh_show and presenter.isVisible():
                presenter.hide()

            if presenter.x() != msg_x or presenter.y() != msg_y:
                presenter.move(msg_x, msg_y)

            presenter.resize(msg_w, msg_h)
            presenter.setFixedHeight(msg_h)

            presenter.update_message(
                text,
                self.VARIANT_ALERT_COLOR,
                x=msg_x,
                y=msg_y,
                width=msg_w,
                height=msg_h,
                font_size=int(self.VARIANT_ALERT_FONT_SIZE),
                sound_filename="",
                vertical_offset=int(self.VARIANT_ALERT_VERTICAL_OFFSET),
            )

            presenter.show()
            presenter.raise_()
            self._current_overlay_kind = kind

            self._variant_message_token += 1
            token = self._variant_message_token
            QTimer.singleShot(
                int(self.VARIANT_ALERT_AUTO_HIDE_MS),
                lambda: self._hide_variant_message_if_token(token),
            )

            game_state_service.state.message_presenter_triggered = True

        except Exception as e:
            self.logger.error(f"MapVariantAutoResolver 显示分支提示失败: {e}")
            
    # 这个函数专门负责隐藏提示信息，和切图逻辑分开，方便以后调整提示时机和内容。
    def _hide_variant_message_if_token(self, token: int):
        if token != self._variant_message_token:
            return
        self._hide_variant_message()


    def _hide_variant_message(self):
        try:
            self._variant_message_token += 1
            if self.message_presenter is not None and self.message_presenter.isVisible():
                self.message_presenter.hide()
        except Exception:
            pass
        finally:
            self._current_overlay_kind = None