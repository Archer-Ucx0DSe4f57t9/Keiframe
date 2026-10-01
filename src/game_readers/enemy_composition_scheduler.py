"""Scheduling adapter for the passive enemy-composition recognizer.

The recognizer itself remains frame-driven and owns no screenshot or thread
lifecycle.  This adapter is called by an existing perception loop, copies the
latest shared frame while holding ``screenshot_lock``, and runs detection/OCR
after releasing that lock.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Optional

from src.game_readers.enemy_composition_recognizer import EnemyCompositionState
from src.utils.logging_util import get_logger


class EnemyCompositionScheduler:
    """Feed an enemy-composition recognizer from an existing visual loop."""

    def __init__(
        self,
        recognizer: Any,
        game_state: Any,
        logger: Optional[Any] = None,
        confirmation_callback: Optional[Callable[[str], None]] = None,
    ):
        self._recognizer = recognizer
        self._game_state = game_state
        self._logger = logger or get_logger(__name__)
        self._confirmation_callback = confirmation_callback
        self._confirmation_emitted = False
        self._recognizer_lock = threading.RLock()

    def update(self) -> bool:
        """Process the newest frame when composition recognition is eligible.

        Returns ``True`` only when a frame was actually passed to the
        recognizer.  The eligibility checks intentionally keep this adapter
        passive: no enemy race or an already confirmed composition means no
        recognizer call.
        """

        game_state = self._game_state
        if not getattr(game_state, "is_in_game", False):
            return False
        if getattr(game_state, "enemy_composition", None) is not None:
            return False

        enemy_race = getattr(game_state, "enemy_race", None)
        if enemy_race is None or not str(enemy_race).strip():
            return False

        # Copy the mutable screenshot only while holding the shared lock.
        # All panel detection, OCR, and matching happen after this block.
        with game_state.screenshot_lock:
            screenshot = (
                game_state.latest_screenshot.copy()
                if game_state.latest_screenshot is not None
                else None
            )
            screenshot_timestamp = game_state.screenshot_timestamp

        if screenshot is None:
            return False

        self._logger.debug(
            "[EnemyCompositionScheduler] update called timestamp=%s",
            screenshot_timestamp,
        )

        confirmed_composition = None
        with self._recognizer_lock:
            try:
                result = self._recognizer.update(
                    image_bgr=screenshot,
                    timestamp=screenshot_timestamp,
                    game_time_seconds=getattr(game_state, "game_time", None),
                    enemy_race=enemy_race,
                )
            except Exception:
                self._logger.exception(
                    "[EnemyCompositionScheduler] update failed timestamp=%s",
                    screenshot_timestamp,
                )
                return False

            if (
                getattr(result, "state", None) == EnemyCompositionState.CONFIRMED
                and getattr(result, "enemy_composition", None)
                and getattr(game_state, "enemy_composition", None) is None
                and not self._confirmation_emitted
            ):
                # GlobalState is a facts container, not a Qt object.  The
                # callback below is the only path that reaches presentation;
                # in production it is a Qt signal's ``emit`` method.
                game_state.enemy_composition = result.enemy_composition
                self._confirmation_emitted = True
                confirmed_composition = result.enemy_composition

        if confirmed_composition:
            self._logger.info(
                "Enemy composition confirmed: %s",
                confirmed_composition,
            )
            if self._confirmation_callback is not None:
                try:
                    self._confirmation_callback(confirmed_composition)
                except Exception:
                    self._logger.exception(
                        "[EnemyCompositionScheduler] confirmation callback failed"
                    )

        return True

    def reset(self) -> None:
        """Reset the recognizer without racing an in-flight perception call."""

        with self._recognizer_lock:
            self._recognizer.reset()
            self._confirmation_emitted = False

    def is_finished(self) -> bool:
        """Return whether this scheduler no longer needs perception frames."""

        if not getattr(self._game_state, "is_in_game", False):
            return True
        if getattr(self._game_state, "enemy_composition", None) is not None:
            return True
        if self._confirmation_emitted:
            return True
        return getattr(self._recognizer, "state", None) in {
            EnemyCompositionState.CONFIRMED,
            EnemyCompositionState.EXPIRED,
        }


__all__ = ["EnemyCompositionScheduler"]
