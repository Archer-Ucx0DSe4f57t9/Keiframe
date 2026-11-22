"""Main-thread presentation state for Enemy Composition recognition."""

from __future__ import annotations

from enum import Enum
from typing import Callable, Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSlot

from src import config
from src.game_readers.enemy_composition_catalog import (
    get_enemy_composition_display_name,
)
from src.presentation_modules.message_presenter import MessagePresenter
from src.utils.logging_util import get_logger
from src.utils.window_utils import get_sc2_window_geometry


class EnemyCompositionNotificationState(str, Enum):
    """Presentation-only lifecycle for one game."""

    IDLE = "IDLE"
    RECOGNIZING = "RECOGNIZING"
    FAILED = "FAILED"
    CONFIRMED = "CONFIRMED"
    EXPIRED = "EXPIRED"


class EnemyCompositionNotifier:
    """Present recognition progress, failure recovery, and final success.

    Every public transition is called on the Qt main thread.  The perception
    worker reaches this object only through queued ``TimerWindow`` signals.
    """

    DISPLAY_DURATION_MS = 5_000
    FAILURE_DISPLAY_DURATION_MS = 5_000
    ALERT_COLOR = "rgb(255,255,255)"
    RECOGNIZING_TEXT = "正在识别中"
    FAILED_TEXT = "识别失败，请将鼠标悬停到敌方位置重试"

    def __init__(
        self,
        parent=None,
        message_presenter=None,
        geometry_provider: Optional[Callable[[], object]] = None,
        single_shot: Optional[Callable[[int, Callable[[], None]], None]] = None,
    ) -> None:
        self.parent = parent
        self.logger = get_logger(__name__)
        # This presenter is a separate top-level layered window.  Do not give
        # it TimerWindow as a QWidget parent: MessagePresenter applies
        # Qt.Tool/native layered-window attributes during construction, and
        # doing that before TimerWindow.init_ui() corrupts the main window's
        # layered composition on Windows.
        self.message_presenter = message_presenter or MessagePresenter(
            None,
            icon_path=None,
        )
        self.message_presenter.setAttribute(
            Qt.WA_TransparentForMouseEvents,
            True,
        )

        self._geometry_provider = geometry_provider or get_sc2_window_geometry
        self._single_shot = single_shot or QTimer.singleShot
        self._state = EnemyCompositionNotificationState.IDLE
        self._shown_this_game = False
        self._timer_generation = 0
        self._shutdown = False
        self._refresh_runtime_config()

    def _refresh_runtime_config(self) -> None:
        """Use the same position and typography settings as ArtifactNotifier."""

        self.alert_offset_x = int(getattr(config, "ARTIFACT_ALERT_OFFSET_X", 800))
        self.alert_offset_y = int(getattr(config, "ARTIFACT_ALERT_OFFSET_Y", 120))
        self.alert_height = int(getattr(config, "ARTIFACT_ALERT_HEIGHT", 40))
        self.alert_font_size = int(getattr(config, "ARTIFACT_ALERT_FONT_SIZE", 30))
        self.alert_vertical_offset = int(
            getattr(config, "ARTIFACT_ALERT_VERTICAL_OFFSET", -10)
        )

    @property
    def state(self) -> EnemyCompositionNotificationState:
        return self._state

    @property
    def shown_this_game(self) -> bool:
        """Expose the per-game success guard for diagnostics and tests."""

        return self._shown_this_game

    def handle_panel_found(self) -> bool:
        """Start one UI attempt after a real panel detection."""

        if self._shutdown or self._shown_this_game:
            return False
        if self._state in {
            EnemyCompositionNotificationState.RECOGNIZING,
            EnemyCompositionNotificationState.CONFIRMED,
            EnemyCompositionNotificationState.EXPIRED,
        }:
            return False
        if self._current_confirmed_composition():
            return False

        self._timer_generation += 1
        generation = self._timer_generation
        if not self._display_message(self.RECOGNIZING_TEXT):
            self._timer_generation += 1
            self._state = EnemyCompositionNotificationState.IDLE
            self._hide_message()
            return False

        self._state = EnemyCompositionNotificationState.RECOGNIZING
        self._single_shot(
            self._recognition_timeout_ms(),
            lambda: self._handle_timeout_for_generation(generation),
        )
        return True

    @pyqtSlot(int)
    def _handle_timeout_for_generation(self, generation: int) -> None:
        if self._shutdown or generation != self._timer_generation:
            return
        if self._state != EnemyCompositionNotificationState.RECOGNIZING:
            return

        confirmed_composition = self._current_confirmed_composition()
        if confirmed_composition:
            self.show(confirmed_composition)
            return
        if self._recognition_has_expired():
            self.handle_expired()
            return

        self._timer_generation += 1
        failure_generation = self._timer_generation
        if not self._display_message(self.FAILED_TEXT):
            self._state = EnemyCompositionNotificationState.IDLE
            self._hide_message()
            return

        self._state = EnemyCompositionNotificationState.FAILED
        self._single_shot(
            self.FAILURE_DISPLAY_DURATION_MS,
            lambda: self._hide_failure_for_generation(failure_generation),
        )

    @pyqtSlot(int)
    def _hide_failure_for_generation(self, generation: int) -> None:
        if self._shutdown or generation != self._timer_generation:
            return
        if self._state != EnemyCompositionNotificationState.FAILED:
            return
        self._state = EnemyCompositionNotificationState.IDLE
        self._hide_message()

    def handle_expired(self) -> None:
        """End an in-progress status silently when recognition expires."""

        if (
            self._shutdown
            or self._state == EnemyCompositionNotificationState.CONFIRMED
        ):
            return
        self._timer_generation += 1
        self._state = EnemyCompositionNotificationState.EXPIRED
        self._hide_message()

    def show(self, canonical_composition: str) -> bool:
        """Replace any active status with the confirmed composition name."""

        if self._shutdown or self._shown_this_game:
            return False
        if self._state == EnemyCompositionNotificationState.CONFIRMED:
            return False

        canonical_composition = str(canonical_composition or "").strip()
        if not canonical_composition:
            return False

        message = get_enemy_composition_display_name(
            canonical_composition,
            getattr(config, "current_game_language", "en"),
        )
        self._timer_generation += 1
        generation = self._timer_generation
        self._state = EnemyCompositionNotificationState.CONFIRMED

        if not self._display_message(message):
            # Confirmation is terminal even if the game window vanished before
            # the queued UI event arrived.  In particular, an old attempt timer
            # must never replace a confirmed result with a failure message.
            self._hide_message()
            return False

        self._shown_this_game = True
        self.logger.debug(
            "Enemy Composition displayed: %s (%s)",
            message,
            getattr(config, "current_game_language", "en"),
        )
        self._single_shot(
            self.DISPLAY_DURATION_MS,
            lambda: self._hide_for_generation(generation),
        )
        return True

    @pyqtSlot(int)
    def _hide_for_generation(self, generation: int) -> None:
        if self._shutdown or generation != self._timer_generation:
            return
        self._hide_message()

    def _display_message(self, message: str) -> bool:
        sc2_rect = self._geometry_provider()
        if not sc2_rect:
            self.logger.debug(
                "Enemy Composition notifier skipped: SC2 window geometry unavailable"
            )
            return False

        self._refresh_runtime_config()
        sc2_x, sc2_y, sc2_width, _sc2_height = sc2_rect
        message_x = int(sc2_x) + self.alert_offset_x
        message_y = int(sc2_y) + self.alert_offset_y
        message_width = int(sc2_width)
        message_height = self.alert_height

        try:
            self.message_presenter.move(message_x, message_y)
            self.message_presenter.resize(message_width, message_height)
            self.message_presenter.setFixedHeight(message_height)
            self.message_presenter.update_message(
                message,
                self.ALERT_COLOR,
                x=message_x,
                y=message_y,
                width=message_width,
                height=message_height,
                font_size=self.alert_font_size,
                sound_filename=None,
                vertical_offset=self.alert_vertical_offset,
            )
            self.message_presenter.show()
            self.message_presenter.raise_()
        except Exception:
            self.logger.exception("Enemy Composition notifier display failed")
            return False
        return True

    def _current_confirmed_composition(self) -> str:
        game_state = getattr(self.parent, "game_state", None)
        return str(getattr(game_state, "enemy_composition", None) or "").strip()

    def _recognition_has_expired(self) -> bool:
        recognizer = getattr(self.parent, "enemy_composition_recognizer", None)
        state = getattr(recognizer, "state", None)
        return getattr(state, "value", state) == "EXPIRED"

    @staticmethod
    def _recognition_timeout_ms() -> int:
        try:
            timeout_seconds = float(
                getattr(
                    config,
                    "ENEMY_COMPOSITION_RECOGNITION_TIMEOUT_SECONDS",
                    8,
                )
            )
        except (TypeError, ValueError):
            timeout_seconds = 8.0
        return max(0, int(timeout_seconds * 1000))

    def _hide_message(self) -> None:
        try:
            self.message_presenter.hide_alert()
        except Exception:
            self.logger.exception("Enemy Composition notifier hide failed")

    def reset(self) -> None:
        """Cancel all status timers and return to a silent IDLE state."""

        self._timer_generation += 1
        self._state = EnemyCompositionNotificationState.IDLE
        self._shown_this_game = False
        self._hide_message()

    def shutdown(self) -> None:
        """Invalidate pending timer callbacks and hide the presenter."""

        if self._shutdown:
            return
        self._shutdown = True
        self._timer_generation += 1
        self._hide_message()


__all__ = [
    "EnemyCompositionNotificationState",
    "EnemyCompositionNotifier",
]
