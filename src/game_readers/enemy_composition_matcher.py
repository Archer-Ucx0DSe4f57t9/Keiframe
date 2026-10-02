"""Pure race-restricted matching helpers for enemy-composition OCR.

The Phase C2 feasibility script originally contained these helpers locally.
Keeping them in ``src`` gives the runtime recognizer and the offline harness
one implementation of text normalization and RapidFuzz ranking.

This module has no screenshot, game-state, or Qt dependency. Its default
matcher loads the production Python catalog through the compatibility loader;
tests can still inject an in-memory candidate mapping.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union


@dataclass(frozen=True)
class Candidate:
    """One candidate spelling and its canonical English output."""

    display_name: str
    canonical_name: str
    normalized_name: str


@dataclass(frozen=True)
class MatchResult:
    """The best two distinct canonical candidates for one OCR query."""

    best: str = ""
    score: Optional[float] = None
    second: str = ""
    second_score: Optional[float] = None

    @property
    def margin(self) -> Optional[float]:
        if self.score is None or self.second_score is None:
            return None
        return self.score - self.second_score


CandidateValue = Union[Candidate, str, Tuple[str, str], List[str]]


def load_enemy_composition_candidates(
    resource_path: Optional[Union[str, Path]] = None,
) -> Dict[str, List[Candidate]]:
    """Build race-restricted matcher candidates from the production resource."""

    from src.game_readers.enemy_composition_database import load_enemy_compositions

    candidates_by_race: Dict[str, List[Candidate]] = {}
    for record in load_enemy_compositions(resource_path):
        candidates_by_race.setdefault(record.race, []).extend(
            make_candidate(alias, record.canonical) for alias in record.aliases
        )
    return candidates_by_race


def normalize_text(text: str) -> str:
    """Normalize OCR/candidate text without language-specific substitutions."""

    normalized = unicodedata.normalize("NFKC", str(text))
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    lines: List[str] = []
    for line in normalized.split("\n"):
        line = re.sub(r"\s+", " ", line).strip().casefold()
        line = re.sub(
            r"(?<=[\u3400-\u9fff]) +(?=[\u3400-\u9fff])",
            "",
            line,
        )
        if line:
            lines.append(line)
    return "\n".join(lines)


def normalized_lines(text: str) -> List[str]:
    """Return non-empty normalized OCR lines."""

    normalized = normalize_text(text)
    return normalized.splitlines() if normalized else []


def make_candidate(display_name: str, canonical_name: Optional[str] = None) -> Candidate:
    """Build a candidate while keeping the normalized form in one place."""

    display_name = str(display_name)
    canonical_name = canonical_name if canonical_name is not None else display_name
    return Candidate(
        display_name=display_name,
        canonical_name=str(canonical_name),
        normalized_name=normalize_text(display_name),
    )


def coerce_candidates(values: Iterable[Any]) -> List[Candidate]:
    """Accept existing candidates or simple strings for injected test data."""

    candidates: List[Candidate] = []
    for value in values:
        if isinstance(value, Candidate):
            candidates.append(value)
        elif isinstance(value, str):
            candidates.append(make_candidate(value))
        elif isinstance(value, (tuple, list)) and len(value) == 2:
            candidates.append(make_candidate(str(value[0]), str(value[1])))
        else:
            raise TypeError(f"Unsupported candidate value: {value!r}")
    return candidates


def fuzzy_match(query: str, candidates: Sequence[Candidate]) -> MatchResult:
    """Return the top two distinct canonical names using RapidFuzz ratio.

    RapidFuzz is imported lazily so a recognizer configured with an injected
    matcher remains importable in a minimal test environment.  The normal C2
    and runtime paths use the same RapidFuzz implementation.
    """

    normalized_query = normalize_text(query)
    if not normalized_query:
        return MatchResult()

    try:
        from rapidfuzz import fuzz, process
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "RapidFuzz is required for enemy-composition matching."
        ) from exc

    normalized_candidates = coerce_candidates(candidates)
    if not normalized_candidates:
        return MatchResult()

    choices = [candidate.normalized_name for candidate in normalized_candidates]
    extracted = process.extract(
        normalized_query,
        choices,
        scorer=fuzz.ratio,
        limit=len(choices),
    )

    best_by_canonical = {}
    for _choice, score, index in extracted:
        candidate = normalized_candidates[index]
        previous = best_by_canonical.get(candidate.canonical_name)
        if previous is None or score > previous:
            best_by_canonical[candidate.canonical_name] = float(score)

    ranked = sorted(
        best_by_canonical.items(),
        key=lambda item: (-item[1], item[0].casefold()),
    )
    if not ranked:
        return MatchResult()

    best_name, best_score = ranked[0]
    if len(ranked) == 1:
        return MatchResult(best=best_name, score=best_score)

    second_name, second_score = ranked[1]
    return MatchResult(
        best=best_name,
        score=best_score,
        second=second_name,
        second_score=second_score,
    )


class EnemyCompositionMatcher:
    """Race-restricted adapter around :func:`fuzzy_match`."""

    def __init__(
        self,
        candidates_by_race: Optional[Mapping[str, Sequence[CandidateValue]]] = None,
        resource_path: Optional[Union[str, Path]] = None,
    ) -> None:
        if candidates_by_race is not None and resource_path is not None:
            raise ValueError("pass candidates_by_race or resource_path, not both")
        if candidates_by_race is None:
            candidates_by_race = load_enemy_composition_candidates(resource_path)
        self._candidates_by_race: Dict[str, Tuple[Candidate, ...]] = {
            str(race): tuple(coerce_candidates(values))
            for race, values in candidates_by_race.items()
        }

    def match(self, query: str, enemy_race: str) -> MatchResult:
        candidates = self._candidates_by_race.get(enemy_race)
        if candidates is None:
            folded_race = str(enemy_race).casefold()
            candidates = next(
                (
                    values
                    for race, values in self._candidates_by_race.items()
                    if race.casefold() == folded_race
                ),
                (),
            )
        return fuzzy_match(query, candidates)


__all__ = [
    "Candidate",
    "EnemyCompositionMatcher",
    "MatchResult",
    "coerce_candidates",
    "fuzzy_match",
    "load_enemy_composition_candidates",
    "make_candidate",
    "normalize_text",
    "normalized_lines",
]
