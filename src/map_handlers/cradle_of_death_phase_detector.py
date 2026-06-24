# -*- coding: utf-8 -*-
"""
Pure phase detector for Cradle of Death countdown extensions.

This module only consumes recognized countdown seconds and game time seconds.
It does not read screenshots, import Qt, start threads, or show notifications.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
from typing import Deque, Dict, List, Optional


@dataclass
class _CandidatePhase:
    phase: int
    phase_start_game_second: int
    detected_countdown_seconds: int
    extension_amount: int
    last_countdown_seconds: int
    last_game_seconds: int
    confirmations: int = 0

    def to_state(self) -> Dict[str, int]:
        return {
            "phase": self.phase,
            "phase_start_game_second": self.phase_start_game_second,
            "detected_countdown_seconds": self.detected_countdown_seconds,
            "extension_amount": self.extension_amount,
            "last_countdown_seconds": self.last_countdown_seconds,
            "last_game_seconds": self.last_game_seconds,
            "confirmations": self.confirmations,
        }


class CradleOfDeathPhaseDetector:
    """Detects Cradle of Death phase changes from countdown extensions."""

    EXTENSION_SECONDS = 450
    EXTENSION_TOLERANCE_SECONDS = 5
    MIN_BASELINE_GAME_SECONDS = 60
    REQUIRED_CONFIRMATIONS = 2
    CONFIRMATION_DRIFT_TOLERANCE_SECONDS = 2
    COOLDOWN_SECONDS = 5
    MAX_PHASE = 3

    def __init__(
        self,
        extension_seconds: int = EXTENSION_SECONDS,
        extension_tolerance_seconds: int = EXTENSION_TOLERANCE_SECONDS,
        min_baseline_game_seconds: int = MIN_BASELINE_GAME_SECONDS,
        required_confirmations: int = REQUIRED_CONFIRMATIONS,
        confirmation_drift_tolerance_seconds: int = CONFIRMATION_DRIFT_TOLERANCE_SECONDS,
        cooldown_seconds: int = COOLDOWN_SECONDS,
        max_phase: int = MAX_PHASE,
        min_confidence: Optional[float] = None,
    ):
        self.extension_seconds = int(extension_seconds)
        self.extension_tolerance_seconds = int(extension_tolerance_seconds)
        self.min_baseline_game_seconds = int(min_baseline_game_seconds)
        self.required_confirmations = int(required_confirmations)
        self.confirmation_drift_tolerance_seconds = int(confirmation_drift_tolerance_seconds)
        self.cooldown_seconds = int(cooldown_seconds)
        self.max_phase = int(max_phase)
        self.min_confidence = min_confidence
        self.reset()

    def reset(self) -> None:
        self.last_valid_countdown_seconds: Optional[int] = None
        self.last_valid_game_seconds: Optional[int] = None
        self.current_phase = 0
        self._candidate: Optional[_CandidatePhase] = None
        self._cooldown_until_game_second: Optional[int] = None
        self._events: Deque[Dict[str, int]] = deque()

    def update(
        self,
        countdown_seconds,
        game_time_seconds,
        confidence: Optional[float] = None,
    ) -> None:
        countdown = self._coerce_seconds(countdown_seconds)
        game_time = self._coerce_seconds(game_time_seconds)
        if countdown is None or game_time is None:
            return
        if self._confidence_is_too_low(confidence):
            return
        if game_time <= self.min_baseline_game_seconds:
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
            extension_amount = self._calculate_extension_amount(countdown, game_time)
            if self._is_extension_amount(extension_amount):
                phase = self.current_phase + 1
                self._candidate = _CandidatePhase(
                    phase=phase,
                    phase_start_game_second=game_time,
                    detected_countdown_seconds=countdown,
                    extension_amount=extension_amount,
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

    def _confidence_is_too_low(self, confidence: Optional[float]) -> bool:
        if self.min_confidence is None or confidence is None:
            return False
        try:
            confidence_value = float(confidence)
        except (TypeError, ValueError):
            return True
        return not math.isfinite(confidence_value) or confidence_value < self.min_confidence

    def _accept_reading(self, countdown: int, game_time: int) -> None:
        self.last_valid_countdown_seconds = countdown
        self.last_valid_game_seconds = game_time

    def _calculate_extension_amount(self, countdown: int, game_time: int) -> int:
        elapsed = game_time - self.last_valid_game_seconds
        expected_countdown = max(0, self.last_valid_countdown_seconds - elapsed)
        return countdown - expected_countdown

    def _is_extension_amount(self, extension_amount: int) -> bool:
        min_extension = self.extension_seconds - self.extension_tolerance_seconds
        max_extension = self.extension_seconds + self.extension_tolerance_seconds
        return min_extension <= extension_amount <= max_extension

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
                "phase_start_game_second": candidate.phase_start_game_second,
                "detected_countdown_seconds": candidate.detected_countdown_seconds,
                "extension_amount": candidate.extension_amount,
            }
        )
        self._cooldown_until_game_second = game_time + self.cooldown_seconds
        self._candidate = None
