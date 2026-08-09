# -*- coding: utf-8 -*-
"""
Pure phase detector for Cradle of Death countdown increases.

This module only consumes successful OCR readings: countdown seconds and game
time seconds. It does not read screenshots, import Qt, start threads, show
toasts, or manage wave schedules.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
from typing import Deque, Dict, List, Optional


@dataclass
class _PhaseCandidate:
    phase: int
    candidate_first_game_second: int
    candidate_countdown_seconds: int
    candidate_increase_amount: int
    last_countdown_seconds: int
    last_game_seconds: int
    confirmations: int = 0

    def to_state(self) -> Dict[str, int]:
        return {
            "phase": self.phase,
            "candidate_first_game_second": self.candidate_first_game_second,
            "candidate_countdown_seconds": self.candidate_countdown_seconds,
            "candidate_increase_amount": self.candidate_increase_amount,
            "last_countdown_seconds": self.last_countdown_seconds,
            "last_game_seconds": self.last_game_seconds,
            "confirmations": self.confirmations,
        }


class CradleOfDeathPhaseDetector:
    """Detects Cradle of Death phase changes from countdown growth."""

    MIN_INCREASE_SECONDS = 300
    MAX_INCREASE_SECONDS = 600
    REQUIRED_CONFIRMATIONS = 2
    CONFIRMATION_DRIFT_TOLERANCE_SECONDS = 2
    COOLDOWN_SECONDS = 5
    MAX_PHASE = 3

    def __init__(
        self,
        min_increase_seconds: int = MIN_INCREASE_SECONDS,
        max_increase_seconds: int = MAX_INCREASE_SECONDS,
        required_confirmations: int = REQUIRED_CONFIRMATIONS,
        confirmation_drift_tolerance_seconds: int = CONFIRMATION_DRIFT_TOLERANCE_SECONDS,
        cooldown_seconds: int = COOLDOWN_SECONDS,
        max_phase: int = MAX_PHASE,
    ):
        self.min_increase_seconds = int(min_increase_seconds)
        self.max_increase_seconds = int(max_increase_seconds)
        self.required_confirmations = int(required_confirmations)
        self.confirmation_drift_tolerance_seconds = int(confirmation_drift_tolerance_seconds)
        self.cooldown_seconds = int(cooldown_seconds)
        self.max_phase = int(max_phase)
        self.reset()

    def reset(self) -> None:
        self.last_valid_countdown_seconds: Optional[int] = None
        self.last_valid_game_seconds: Optional[int] = None
        self.current_phase = 0
        self._candidate: Optional[_PhaseCandidate] = None
        self._cooldown_until_game_second: Optional[int] = None
        self._events: Deque[Dict[str, int]] = deque()

    def update(self, countdown_seconds, game_time_seconds) -> None:
        countdown = self._coerce_seconds(countdown_seconds)
        game_time = self._coerce_seconds(game_time_seconds)
        if countdown is None or game_time is None:
            return

        if self.last_valid_countdown_seconds is None or self.last_valid_game_seconds is None:
            self._accept_reading(countdown, game_time)
            return

        if game_time <= self.last_valid_game_seconds:
            return

        if self._candidate is not None:
            self._process_candidate_reading(countdown, game_time)
            self._accept_reading(countdown, game_time)
            return

        if self._can_start_candidate(game_time):
            increase_amount = self._calculate_increase_amount(countdown, game_time)
            if self._is_phase_increase(increase_amount):
                self._candidate = _PhaseCandidate(
                    phase=self.current_phase + 1,
                    candidate_first_game_second=game_time,
                    candidate_countdown_seconds=countdown,
                    candidate_increase_amount=increase_amount,
                    last_countdown_seconds=countdown,
                    last_game_seconds=game_time,
                )

        self._accept_reading(countdown, game_time)

    def consume_events(self) -> List[Dict[str, int]]:
        events = list(self._events)
        self._events.clear()
        return events

    def get_state(self) -> Dict[str, object]:
        return {
            "last_valid_countdown_seconds": self.last_valid_countdown_seconds,
            "last_valid_game_seconds": self.last_valid_game_seconds,
            "current_phase": self.current_phase,
            "candidate": self._candidate.to_state() if self._candidate else None,
            "cooldown_until_game_second": self._cooldown_until_game_second,
            "pending_event_count": len(self._events),
        }

    @staticmethod
    def _coerce_seconds(value) -> Optional[int]:
        if value is None or isinstance(value, bool):
            return None
        try:
            seconds = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(seconds) or seconds < 0:
            return None
        return int(round(seconds))

    def _accept_reading(self, countdown: int, game_time: int) -> None:
        self.last_valid_countdown_seconds = countdown
        self.last_valid_game_seconds = game_time

    def _calculate_increase_amount(self, countdown: int, game_time: int) -> int:
        elapsed = game_time - self.last_valid_game_seconds
        expected_countdown = max(0, self.last_valid_countdown_seconds - elapsed)
        return countdown - expected_countdown

    def _is_phase_increase(self, increase_amount: int) -> bool:
        return self.min_increase_seconds <= increase_amount <= self.max_increase_seconds

    def _can_start_candidate(self, game_time: int) -> bool:
        if self.current_phase >= self.max_phase:
            return False
        if self._cooldown_until_game_second is None:
            return True
        return game_time >= self._cooldown_until_game_second

    def _process_candidate_reading(self, countdown: int, game_time: int) -> None:
        candidate = self._candidate
        elapsed = game_time - candidate.last_game_seconds
        expected_countdown = max(0, candidate.last_countdown_seconds - elapsed)
        drift = countdown - expected_countdown

        if abs(drift) > self.confirmation_drift_tolerance_seconds:
            self._candidate = None
            return

        candidate.confirmations += 1
        candidate.last_countdown_seconds = countdown
        candidate.last_game_seconds = game_time
        if candidate.confirmations < self.required_confirmations:
            return

        self.current_phase = candidate.phase
        self._events.append(
            {
                "phase": candidate.phase,
                "phase_start_game_second": candidate.candidate_first_game_second,
                "detected_countdown_seconds": candidate.candidate_countdown_seconds,
                "increase_amount": candidate.candidate_increase_amount,
            }
        )
        self._cooldown_until_game_second = game_time + self.cooldown_seconds
        self._candidate = None
