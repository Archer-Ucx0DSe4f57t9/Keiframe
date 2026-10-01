"""Pure, frame-driven enemy-composition recognizer.

The recognizer owns only the tooltip lifecycle and OCR/matching vote.  It does
not capture screenshots, start workers, read ``game_state_service`` or write
to ``GlobalState``.  A caller supplies one normalized BGR frame at a time and
can consume the structured state returned by :meth:`update`.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple, Union

import numpy as np

from src.game_readers.enemy_composition_matcher import (
    Candidate,
    MatchResult,
    coerce_candidates,
    fuzzy_match,
    normalized_lines,
)
from src.game_readers.enemy_composition_panel_detector import (
    crop_enemy_composition_title,
    detect_enemy_composition_panel,
)
from src.game_readers.ocr_provider import OCRProvider
from src.utils.logging_util import get_logger


logger = get_logger(__name__)

BBox = Tuple[int, int, int, int]
CandidateValue = Union[Candidate, str, Tuple[str, str], List[str]]


class EnemyCompositionState(str, Enum):
    """Lifecycle states for one game."""

    SEARCHING = "SEARCHING"
    COLLECTING = "COLLECTING"
    CONFIRMING = "CONFIRMING"
    CONFIRMED = "CONFIRMED"
    EXPIRED = "EXPIRED"


# ``RecognizerState`` is a small compatibility-friendly alias for callers
# that prefer the shorter name.
RecognizerState = EnemyCompositionState


@dataclass(frozen=True)
class EnemyCompositionConfig:
    """All temporal, vote, and matching thresholds used by the recognizer."""

    panel_found_streak_required: int = 3
    max_crops: int = 6
    minimum_valid_results: int = 3
    minimum_votes: int = 3
    minimum_vote_lead: int = 1
    match_score_threshold: float = 70.0
    match_margin_threshold: float = 30.0
    game_time_expiry_seconds: float = 300.0

    def __post_init__(self) -> None:
        if self.panel_found_streak_required < 1:
            raise ValueError("panel_found_streak_required must be positive")
        if self.max_crops < 1:
            raise ValueError("max_crops must be positive")
        if self.minimum_valid_results < 1:
            raise ValueError("minimum_valid_results must be positive")
        if self.minimum_votes < 1:
            raise ValueError("minimum_votes must be positive")
        if self.minimum_vote_lead < 1:
            raise ValueError("minimum_vote_lead must be positive")
        if self.match_score_threshold < 0:
            raise ValueError("match_score_threshold cannot be negative")
        if self.match_margin_threshold < 0:
            raise ValueError("match_margin_threshold cannot be negative")
        if self.game_time_expiry_seconds < 0:
            raise ValueError("game_time_expiry_seconds cannot be negative")

    # These aliases keep the configuration readable at call sites that use
    # the wording from the Phase D1 design note.
    @property
    def max_game_time_seconds(self) -> float:
        return self.game_time_expiry_seconds

    @property
    def required_panel_streak(self) -> int:
        return self.panel_found_streak_required


@dataclass(frozen=True)
class EnemyCompositionRecognition:
    """Immutable result returned by every :meth:`EnemyCompositionRecognizer.update`."""

    state: EnemyCompositionState
    enemy_composition: Optional[str]
    panel_found_streak: int
    collected_crops: int
    ocr_results: int
    valid_results: int

    @property
    def confirmed(self) -> bool:
        return self.state == EnemyCompositionState.CONFIRMED


class _DefaultPanelDetector:
    """Adapter that gives the existing detector function an object interface."""

    @staticmethod
    def detect(image_bgr: np.ndarray) -> Any:
        return detect_enemy_composition_panel(image_bgr)


class EnemyCompositionRecognizer:
    """Collect title crops and confirm a canonical enemy composition.

    ``ocr_provider`` is intentionally injected.  The production contract is
    an object exposing ``recognize(crop)`` and returning raw OCR lines; a
    callable remains accepted for the existing deterministic D1 test doubles.
    The full two-line text is accepted and the second line is selected
    automatically.  ``candidates_by_race`` contains
    :class:`Candidate` objects or simple strings.  Alternatively, ``matcher``
    may be injected with ``matcher(composition_text, enemy_race)`` returning a
    :class:`MatchResult` or canonical string.  ``ocr_matcher`` is an alias for
    object-style matchers exposing ``match(composition_text, enemy_race)``.
    """

    def __init__(
        self,
        panel_detector: Optional[Any] = None,
        ocr_provider: Optional[Union[OCRProvider, Callable[[np.ndarray], Any]]] = None,
        candidates_by_race: Optional[
            Mapping[str, Sequence[CandidateValue]]
        ] = None,
        matcher: Optional[Callable[[str, str], Any]] = None,
        config: Optional[EnemyCompositionConfig] = None,
        title_crop_extractor: Optional[
            Callable[[np.ndarray, Optional[Sequence[int]]], Any]
        ] = None,
        ocr_matcher: Optional[Any] = None,
    ) -> None:
        if matcher is not None and ocr_matcher is not None:
            raise ValueError("pass matcher or ocr_matcher, not both")
        self.config = config or EnemyCompositionConfig()
        self._panel_detector = panel_detector or _DefaultPanelDetector()
        self._ocr_provider = ocr_provider
        self._matcher = matcher if matcher is not None else ocr_matcher
        self._title_crop_extractor = title_crop_extractor
        self._candidates_by_race = self._normalize_candidates(candidates_by_race)

        self._state = EnemyCompositionState.SEARCHING
        self._enemy_composition: Optional[str] = None
        self._panel_found_streak = 0
        self._panel_confirmed = False
        self._collected_crops: List[np.ndarray] = []
        self._ocr_results: List[str] = []
        self._valid_match_results: List[str] = []
        self._match_results: List[MatchResult] = []
        self._votes: Counter[str] = Counter()
        self._ocr_processed_count = 0
        self._processed_timestamps: List[Any] = []
        self._state_history: List[EnemyCompositionState] = [self._state]

    @property
    def state(self) -> EnemyCompositionState:
        return self._state

    @property
    def enemy_composition(self) -> Optional[str]:
        return self._enemy_composition

    @property
    def panel_found_streak(self) -> int:
        return self._panel_found_streak

    @property
    def collected_crops(self) -> Tuple[np.ndarray, ...]:
        return tuple(self._collected_crops)

    @property
    def ocr_results(self) -> Tuple[str, ...]:
        return tuple(self._ocr_results)

    @property
    def valid_results(self) -> Tuple[str, ...]:
        return tuple(self._valid_match_results)

    @property
    def votes(self) -> Dict[str, int]:
        return dict(self._votes)

    @property
    def match_results(self) -> Tuple[MatchResult, ...]:
        return tuple(self._match_results)

    @property
    def state_transitions(self) -> Tuple[str, ...]:
        """State values in transition order, useful for manual diagnostics."""

        return tuple(state.value for state in self._state_history)

    @property
    def is_confirmed(self) -> bool:
        return self._state == EnemyCompositionState.CONFIRMED

    def reset(self) -> None:
        """Reset all per-game state and return to ``SEARCHING``."""

        self._state = EnemyCompositionState.SEARCHING
        self._enemy_composition = None
        self._panel_found_streak = 0
        self._panel_confirmed = False
        self._collected_crops.clear()
        self._ocr_results.clear()
        self._valid_match_results.clear()
        self._match_results.clear()
        self._votes.clear()
        self._ocr_processed_count = 0
        self._processed_timestamps.clear()
        self._state_history = [self._state]

    def update(
        self,
        image_bgr: Optional[np.ndarray],
        timestamp: Any,
        game_time_seconds: Optional[Union[int, float]],
        enemy_race: Optional[str],
    ) -> EnemyCompositionRecognition:
        """Process one frame and return the current recognition snapshot.

        Repeated calls with the same timestamp are ignored.  The timestamp is
        recorded only after a non-empty race is supplied, so a caller can
        provide the race slightly after a frame without losing that frame.
        """

        if self._state in {
            EnemyCompositionState.CONFIRMED,
            EnemyCompositionState.EXPIRED,
        }:
            return self._snapshot()

        if self._is_expired(game_time_seconds):
            self._set_state(EnemyCompositionState.EXPIRED)
            return self._snapshot()

        if enemy_race is None or not str(enemy_race).strip():
            return self._snapshot()

        if self._timestamp_was_processed(timestamp):
            return self._snapshot()
        self._processed_timestamps.append(timestamp)

        detection = self._detect(image_bgr)
        if not self._detection_found(detection):
            if (
                self._state == EnemyCompositionState.COLLECTING
                and not self._panel_confirmed
            ):
                # A missing frame breaks the consecutive-found requirement.
                # Discarding the incomplete tooltip also prevents crops from
                # one hover from being mixed into the next hover.
                self._discard_incomplete_collection()
            return self._snapshot()

        if self._state == EnemyCompositionState.SEARCHING:
            self._set_state(EnemyCompositionState.COLLECTING)

        self._panel_found_streak += 1
        self._append_crop(image_bgr, detection)

        if (
            self._state == EnemyCompositionState.COLLECTING
            and self._panel_found_streak
            >= self.config.panel_found_streak_required
        ):
            self._panel_confirmed = True
            self._set_state(EnemyCompositionState.CONFIRMING)
            self._process_pending_ocr(enemy_race)
        elif self._state == EnemyCompositionState.CONFIRMING:
            # The initial three samples are normally enough.  If OCR produced
            # too few confident votes, consume only newly collected crops as
            # a bounded fallback; SEARCHING/COLLECTING never OCRs per frame.
            self._process_pending_ocr(enemy_race)

        return self._snapshot()

    def _snapshot(self) -> EnemyCompositionRecognition:
        return EnemyCompositionRecognition(
            state=self._state,
            enemy_composition=self._enemy_composition,
            panel_found_streak=self._panel_found_streak,
            collected_crops=len(self._collected_crops),
            ocr_results=len(self._ocr_results),
            valid_results=len(self._valid_match_results),
        )

    def _set_state(self, state: EnemyCompositionState) -> None:
        if state == self._state:
            return
        self._state = state
        self._state_history.append(state)

    def _is_expired(self, game_time_seconds: Optional[Union[int, float]]) -> bool:
        if game_time_seconds is None:
            return False
        try:
            return float(game_time_seconds) > self.config.game_time_expiry_seconds
        except (TypeError, ValueError):
            return False

    def _timestamp_was_processed(self, timestamp: Any) -> bool:
        for previous in self._processed_timestamps:
            try:
                same = timestamp == previous
                if isinstance(same, bool) and same:
                    return True
                if not isinstance(same, bool) and bool(same):
                    return True
            except (TypeError, ValueError):
                continue
        return False

    def _detect(self, image_bgr: Optional[np.ndarray]) -> Any:
        detector = self._panel_detector
        detect_method = getattr(detector, "detect", None)
        if callable(detect_method):
            return detect_method(image_bgr)
        if callable(detector):
            return detector(image_bgr)
        raise TypeError("panel_detector must be callable or provide detect()")

    @staticmethod
    def _detection_found(detection: Any) -> bool:
        if isinstance(detection, Mapping):
            return bool(detection.get("found", False))
        if isinstance(detection, (tuple, list)) and detection:
            return bool(detection[0])
        return bool(getattr(detection, "found", detection))

    @staticmethod
    def _detection_bbox(detection: Any) -> Optional[Sequence[int]]:
        if isinstance(detection, Mapping):
            return detection.get("bbox")
        if isinstance(detection, (tuple, list)) and len(detection) > 1:
            return detection[1]
        return getattr(detection, "bbox", None)

    @staticmethod
    def _detection_title_crop(detection: Any) -> Optional[np.ndarray]:
        if isinstance(detection, Mapping):
            crop = detection.get("title_crop")
        else:
            crop = getattr(detection, "title_crop", None)
        return crop if isinstance(crop, np.ndarray) else None

    def _append_crop(self, image_bgr: Optional[np.ndarray], detection: Any) -> None:
        if len(self._collected_crops) >= self.config.max_crops:
            return

        crop = self._detection_title_crop(detection)
        if crop is None and self._title_crop_extractor is not None:
            crop_result = self._title_crop_extractor(
                image_bgr,
                self._detection_bbox(detection),
            )
            crop = crop_result[0] if isinstance(crop_result, tuple) else crop_result
        if crop is None:
            crop_result = crop_enemy_composition_title(
                image_bgr,
                self._detection_bbox(detection),
            )
            crop = crop_result[0] if crop_result is not None else None

        if isinstance(crop, np.ndarray) and crop.size:
            self._collected_crops.append(crop.copy())

    def _process_pending_ocr(self, enemy_race: str) -> None:
        if self._ocr_provider is None:
            return

        while self._ocr_processed_count < len(self._collected_crops):
            crop = self._collected_crops[self._ocr_processed_count]
            self._ocr_processed_count += 1
            try:
                raw_result = self._call_ocr_provider(crop)
                composition_text = self._extract_composition_text(raw_result)
                self._ocr_results.append(composition_text)
                match = self._match_composition(composition_text, enemy_race)
            except Exception as exc:  # OCR is an optional failure point.
                logger.debug("Enemy-composition OCR/matching failed: %s", exc)
                self._ocr_results.append("")
                match = MatchResult()

            self._match_results.append(match)
            if self._is_confident_match(match):
                self._valid_match_results.append(match.best)
                self._votes[match.best] += 1
            self._try_confirm()
            if self._state == EnemyCompositionState.CONFIRMED:
                return

    def _call_ocr_provider(self, crop: np.ndarray) -> Any:
        provider = self._ocr_provider
        recognize_method = getattr(provider, "recognize", None)
        if callable(recognize_method):
            return recognize_method(crop)
        if callable(provider):
            return provider(crop)
        raise TypeError("ocr_provider must be callable or provide recognize()")

    @staticmethod
    def _extract_composition_text(raw_result: Any) -> str:
        if isinstance(raw_result, MatchResult):
            return raw_result.best
        if isinstance(raw_result, Mapping):
            raw_result = raw_result.get(
                "composition",
                raw_result.get("composition_name", raw_result.get("text", "")),
            )
        if isinstance(raw_result, (tuple, list)):
            raw_result = "\n".join(str(item) for item in raw_result)
        lines = normalized_lines("" if raw_result is None else str(raw_result))
        if len(lines) > 1:
            return lines[1]
        return lines[0] if lines else ""

    def _match_composition(self, query: str, enemy_race: str) -> MatchResult:
        if not query:
            return MatchResult()

        if self._matcher is not None:
            match_method = getattr(self._matcher, "match", None)
            if callable(match_method):
                result = match_method(query, enemy_race)
            elif callable(self._matcher):
                result = self._matcher(query, enemy_race)
            else:
                raise TypeError("matcher must be callable or provide match()")
            return self._coerce_match_result(result)

        candidates = self._candidates_for_race(enemy_race)
        if not candidates:
            return MatchResult()
        return fuzzy_match(query, candidates)

    @staticmethod
    def _coerce_match_result(result: Any) -> MatchResult:
        if isinstance(result, MatchResult):
            return result
        if isinstance(result, str) and result.strip():
            # An injected matcher is already responsible for choosing the
            # canonical result; retain the configured confidence contract.
            return MatchResult(best=result.strip(), score=100.0, second_score=0.0)
        if isinstance(result, Mapping):
            return MatchResult(
                best=str(result.get("best", "")),
                score=result.get("score"),
                second=str(result.get("second", "")),
                second_score=result.get("second_score"),
            )
        return MatchResult()

    def _is_confident_match(self, match: MatchResult) -> bool:
        if not match.best or match.score is None:
            return False
        if float(match.score) < self.config.match_score_threshold:
            return False
        if match.second_score is None:
            # A single candidate has no competitor; its score still must pass
            # the absolute threshold.
            return True
        margin = float(match.score) - float(match.second_score)
        return margin >= self.config.match_margin_threshold

    def _try_confirm(self) -> None:
        if self._state == EnemyCompositionState.CONFIRMED:
            return
        if len(self._valid_match_results) < self.config.minimum_valid_results:
            return

        ranked = self._votes.most_common()
        if not ranked:
            return
        winner, winner_votes = ranked[0]
        second_votes = ranked[1][1] if len(ranked) > 1 else 0
        if winner_votes < self.config.minimum_votes:
            return
        if winner_votes - second_votes < self.config.minimum_vote_lead:
            return

        self._enemy_composition = winner
        self._set_state(EnemyCompositionState.CONFIRMED)

    def _candidates_for_race(self, enemy_race: str) -> Sequence[Candidate]:
        if enemy_race in self._candidates_by_race:
            return self._candidates_by_race[enemy_race]
        folded_race = str(enemy_race).casefold()
        for race, candidates in self._candidates_by_race.items():
            if race.casefold() == folded_race:
                return candidates
        return ()

    @staticmethod
    def _normalize_candidates(
        candidates_by_race: Optional[Mapping[str, Sequence[CandidateValue]]],
    ) -> Dict[str, Tuple[Candidate, ...]]:
        if not candidates_by_race:
            return {}
        return {
            str(race): tuple(coerce_candidates(values))
            for race, values in candidates_by_race.items()
        }

    def _discard_incomplete_collection(self) -> None:
        self._panel_found_streak = 0
        self._collected_crops.clear()
        self._ocr_processed_count = 0
        self._set_state(EnemyCompositionState.SEARCHING)


__all__ = [
    "EnemyCompositionConfig",
    "EnemyCompositionRecognition",
    "EnemyCompositionRecognizer",
    "EnemyCompositionState",
    "RecognizerState",
]
