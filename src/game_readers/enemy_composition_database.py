"""Validated access to the production enemy-composition catalog.

The catalog is a small runtime resource rather than test data. Keeping its
loading and validation here lets the matcher and offline tools share exactly
the same canonical names, races, and verified aliases.
"""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from src.utils.fileutil import get_resources_dir


SUPPORTED_RACES = ("Terran", "Zerg", "Protoss")
RESOURCE_FILENAME = "enemy_compositions.json"


@dataclass(frozen=True)
class EnemyCompositionRecord:
    """One production composition and its verified display aliases."""

    canonical: str
    race: str
    aliases: Tuple[str, ...]


def get_default_resource_path() -> Path:
    """Return the resource path in source and PyInstaller layouts."""

    resources_dir = get_resources_dir()
    if not resources_dir:
        raise FileNotFoundError("resources directory could not be resolved")
    return Path(resources_dir) / RESOURCE_FILENAME


def _normalized_key(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def _require_non_empty_string(value: Any, field_name: str, index: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"enemy composition entry {index} has an invalid {field_name}"
        )
    return value.strip()


def load_enemy_compositions(
    resource_path: Optional[Union[str, Path]] = None,
) -> Tuple[EnemyCompositionRecord, ...]:
    """Load and validate the complete production catalog.

    The JSON shape is intentionally simple and reviewable:

    ``[{"canonical": "...", "race": "...", "aliases": ["..."]}]``

    Every canonical name must be present in its aliases. This makes the
    English form and every verified localized form available to the matcher,
    while the result of a match always remains the canonical English name.
    """

    path = Path(resource_path) if resource_path is not None else get_default_resource_path()
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, list) or not payload:
        raise ValueError("enemy composition resource must be a non-empty JSON list")

    records: List[EnemyCompositionRecord] = []
    seen_canonical: Dict[str, int] = {}
    for index, entry in enumerate(payload):
        if not isinstance(entry, dict):
            raise ValueError(f"enemy composition entry {index} must be an object")

        canonical = _require_non_empty_string(entry.get("canonical"), "canonical", index)
        if not canonical.isascii():
            raise ValueError(
                f"enemy composition entry {index} canonical must be English ASCII"
            )

        race = _require_non_empty_string(entry.get("race"), "race", index)
        if race not in SUPPORTED_RACES:
            raise ValueError(
                f"enemy composition entry {index} has unsupported race {race!r}"
            )

        aliases = entry.get("aliases")
        if not isinstance(aliases, list) or not aliases:
            raise ValueError(f"enemy composition entry {index} aliases must be a list")

        clean_aliases: List[str] = []
        seen_aliases = set()
        for alias in aliases:
            clean_alias = _require_non_empty_string(alias, "alias", index)
            alias_key = _normalized_key(clean_alias)
            if alias_key in seen_aliases:
                raise ValueError(
                    f"enemy composition entry {index} contains duplicate aliases"
                )
            seen_aliases.add(alias_key)
            clean_aliases.append(clean_alias)

        if _normalized_key(canonical) not in seen_aliases:
            raise ValueError(
                f"enemy composition entry {index} aliases must include canonical"
            )

        canonical_key = _normalized_key(canonical)
        if canonical_key in seen_canonical:
            raise ValueError(
                f"duplicate canonical composition {canonical!r} at entry {index}"
            )
        seen_canonical[canonical_key] = index
        records.append(
            EnemyCompositionRecord(
                canonical=canonical,
                race=race,
                aliases=tuple(clean_aliases),
            )
        )

    return tuple(records)


def records_by_race(
    records: Sequence[EnemyCompositionRecord],
) -> Dict[str, Tuple[EnemyCompositionRecord, ...]]:
    """Group validated records by race without changing their order."""

    grouped: Dict[str, List[EnemyCompositionRecord]] = {
        race: [] for race in SUPPORTED_RACES
    }
    for record in records:
        grouped[record.race].append(record)
    return {race: tuple(values) for race, values in grouped.items()}


__all__ = [
    "EnemyCompositionRecord",
    "RESOURCE_FILENAME",
    "SUPPORTED_RACES",
    "get_default_resource_path",
    "load_enemy_compositions",
    "records_by_race",
]
