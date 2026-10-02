"""Main-thread presentation for confirmed Enemy Composition results."""

from __future__ import annotations

from PyQt5.QtCore import Qt, QTimer, pyqtSlot

from src import config
from src.game_readers.enemy_composition_catalog import (
    get_enemy_composition_display_name,
)
from src.presentation_modules.message_presenter import MessagePresenter
from src.utils.logging_util import get_logger
from src.utils.window_utils import get_sc2_window_geometry


class EnemyCompositionNotifier:
    """Show one silent, five-second composition message per game.

    ``show`` is intentionally a Qt-main-thread operation.  The perception
    worker only emits the Qt signal that reaches this notifier through
    ``TimerWindow.handle_enemy_composition_confirmed``.
    """

    DISPLAY_DURATION_MS = 5_000
    ALERT_COLOR = "rgb(255,255,255)"

    def __init__(self, parent=None) -> None:
        self.parent = parent
        self.logger = get_logger(__name__)
        # This presenter is a separate top-level layered window.  Do not give
        # it TimerWindow as a QWidget parent: MessagePresenter applies
        # Qt.Tool/native layered-window attributes during construction, and
        # doing that before TimerWindow.init_ui() corrupts the main window's
        # layered composition on Windows.
        self.message_presenter = MessagePresenter(None, icon_path=None)
        self.message_presenter.setAttribute(Qt.WA_TransparentForMouseEvents, True)

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
    def shown_this_game(self) -> bool:
        """Expose the per-game guard for diagnostics and focused tests."""

        return self._shown_this_game

    def show(self, canonical_composition: str) -> bool:
        """Display the canonical result and schedule its main-thread hide.

        Returns ``True`` when a message was displayed.  Missing game-window
        geometry does not consume the per-game notification, allowing the
        caller to retry safely.
        """

        if self._shutdown or self._shown_this_game:
            return False

        canonical_composition = str(canonical_composition or "").strip()
        if not canonical_composition:
            return False

        sc2_rect = get_sc2_window_geometry()
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
        message = get_enemy_composition_display_name(
            canonical_composition,
            getattr(config, "current_game_language", "en"),
        )

        self._timer_generation += 1
        generation = self._timer_generation

        try:
            # Keep the same geometry contract as ArtifactNotifier while using
            # an independent, icon-free MessagePresenter instance.
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
            self._timer_generation += 1
            self._hide_message()
            self.logger.exception("Enemy Composition notifier display failed")
            return False

        self._shown_this_game = True
        self.logger.debug(
            "Enemy Composition displayed: %s (%s)",
            message,
            getattr(config, "current_game_language", "en"),
        )

        # The generation captured by this callback prevents a timer from a
        # previous game/reset from hiding a newly displayed message.
        QTimer.singleShot(
            self.DISPLAY_DURATION_MS,
            lambda: self._hide_for_generation(generation),
        )
        return True

    @pyqtSlot(int)
    def _hide_for_generation(self, generation: int) -> None:
        if self._shutdown or generation != self._timer_generation:
            return
        self._hide_message()

    def _hide_message(self) -> None:
        try:
            self.message_presenter.hide_alert()
        except Exception:
            self.logger.exception("Enemy Composition notifier hide failed")

    def reset(self) -> None:
        """Hide the current message and permit one notification next game."""

        self._timer_generation += 1
        self._shown_this_game = False
        self._hide_message()

    def shutdown(self) -> None:
        """Invalidate pending timer callbacks and hide the presenter."""

        if self._shutdown:
            return
        self._shutdown = True
        self._timer_generation += 1
        self._hide_message()


__all__ = ["EnemyCompositionNotifier"]
