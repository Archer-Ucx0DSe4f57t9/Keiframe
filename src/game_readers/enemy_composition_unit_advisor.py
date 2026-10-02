"""Enemy Composition unit advice loaded from the static CSV resources.

This module is deliberately separate from the Enemy Composition OCR pipeline.
It only consumes the confirmed ``GlobalState.enemy_composition`` value and
provides optional reminder text to business-layer callers.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping, Optional, Union

from src.utils.fileutil import get_resources_dir
from src.utils.logging_util import get_logger


SUPPORTED_TIERS = tuple(f"t{index}" for index in range(1, 8))
_TIER_PATTERN = re.compile(r"(?P<tier>[tT][1-7])(?!\d)")


def _normalize_composition_key(value: str) -> str:
    """Normalize a composition name without changing its display value."""

    return unicodedata.normalize("NFKC", value).strip().casefold()


def extract_tier(text: object) -> Optional[str]:
    """Return the only valid tier in *text*, or ``None`` if it is invalid.

    A tier is valid when it is ``t1`` through ``t7`` (case-insensitive).  The
    numeric suffix must end there, so ``t10`` and ``t20`` do not match.  Any
    message containing zero or more than one valid tier is intentionally
    rejected as a whole.
    """

    if not isinstance(text, str):
        return None

    matches = _TIER_PATTERN.findall(text)
    if len(matches) != 1:
        return None

    return matches[0].lower()


@dataclass(frozen=True)
class EnemyCompositionUnitEntry:
    """One logical composition and its per-tier attention-unit text."""

    english: str
    chinese: str
    tiers: Mapping[str, str]


class EnemyCompositionUnitAdvisor:
    """Load and query the static enemy-composition unit advice.

    CSV files are read exactly once during construction.  A malformed file is
    isolated to that file so the rest of the application can keep its normal
    reminder behavior.
    """

    def __init__(
        self,
        resource_dir: Optional[Union[str, Path]] = None,
        logger=None,
    ):
        self.logger = logger or get_logger(__name__)
        self._entries_by_name: Dict[str, EnemyCompositionUnitEntry] = {}
        self._unknown_compositions_logged = set()
        self._advisor_error_logged = False
        self._loaded_file_count = 0

        try:
            resolved_resource_dir = (
                Path(resource_dir)
                if resource_dir is not None
                else self._resolve_default_resource_dir()
            )
        except Exception as exc:
            self.logger.error(
                "Failed to resolve enemy composition unit resources: %s",
                exc,
            )
            resolved_resource_dir = None

        self.resource_dir = resolved_resource_dir
        self._load_csv_resources()

    def _resolve_default_resource_dir(self) -> Optional[Path]:
        resources_dir = get_resources_dir("enemy_comps")
        return Path(resources_dir) if resources_dir else None

    @property
    def loaded_file_count(self) -> int:
        """Number of valid CSV files loaded during initialization."""

        return self._loaded_file_count

    @property
    def composition_count(self) -> int:
        """Number of unique logical compositions currently available."""

        return len(
            {
                (entry.english, entry.chinese)
                for entry in self._entries_by_name.values()
            }
        )

    @staticmethod
    def extract_tier(text: object) -> Optional[str]:
        """Expose the tier parser through the advisor instance API."""

        return extract_tier(text)

    def _load_csv_resources(self) -> None:
        if self.resource_dir is None or not self.resource_dir.is_dir():
            self.logger.warning(
                "Enemy composition unit resource directory is unavailable; "
                "unit advice is disabled."
            )
            return

        try:
            csv_paths = sorted(
                (
                    path
                    for path in self.resource_dir.iterdir()
                    if path.is_file() and path.suffix.casefold() == ".csv"
                ),
                key=lambda path: path.name.casefold(),
            )
        except Exception as exc:
            self.logger.error(
                "Failed to scan enemy composition unit resources: %s",
                exc,
            )
            return

        for csv_path in csv_paths:
            self._load_csv_file(csv_path)

        self.logger.info(
            "Loaded %d enemy composition unit CSV files (%d compositions).",
            self._loaded_file_count,
            self.composition_count,
        )

    def _load_csv_file(self, csv_path: Path) -> None:
        try:
            with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.reader(handle)
                header = None
                tiers: Dict[str, str] = {}

                for row in reader:
                    cells = [cell.strip() for cell in row]
                    if not cells or not any(cells):
                        continue

                    if header is None:
                        if len(cells) < 2 or not cells[0] or not cells[1]:
                            raise ValueError(
                                "the first non-empty row must contain English "
                                "and Chinese names"
                            )
                        header = (cells[0], cells[1])
                        continue

                    tier_name = cells[0].casefold()
                    if tier_name not in SUPPORTED_TIERS:
                        continue

                    # A missing second cell is equivalent to an empty advice
                    # cell.  No unit text is inferred or filled in.
                    tiers[tier_name] = cells[1] if len(cells) > 1 else ""

                if header is None:
                    raise ValueError("the file has no non-empty rows")

            entry = EnemyCompositionUnitEntry(
                english=header[0],
                chinese=header[1],
                tiers=tiers,
            )
            for display_name in (entry.english, entry.chinese):
                lookup_key = _normalize_composition_key(display_name)
                previous = self._entries_by_name.get(lookup_key)
                if previous is not None and previous != entry:
                    self.logger.warning(
                        "Skipping duplicate enemy composition key %r from %s.",
                        display_name,
                        csv_path.name,
                    )
                    continue
                self._entries_by_name[lookup_key] = entry

            self._loaded_file_count += 1
        except Exception as exc:
            self.logger.warning(
                "Skipping enemy composition unit CSV %s: %s",
                csv_path.name,
                exc,
            )

    def get_attention_units(
        self,
        composition: Optional[str],
        text: object,
    ) -> Optional[str]:
        """Return attention units for ``composition`` and its unique tier.

        Lookup failures are non-fatal by design.  Callers can therefore keep
        their original reminder text when the optional enrichment is absent.
        """

        try:
            if composition is None:
                return None

            composition_text = str(composition).strip()
            if not composition_text:
                return None

            entry = self._entries_by_name.get(
                _normalize_composition_key(composition_text)
            )
            if entry is None:
                if composition_text not in self._unknown_compositions_logged:
                    self._unknown_compositions_logged.add(composition_text)
                    self.logger.debug(
                        "No enemy composition unit advice for %r.",
                        composition_text,
                    )
                return None

            tier_name = extract_tier(text)
            if tier_name is None:
                return None

            attention_units = entry.tiers.get(tier_name, "")
            attention_units = attention_units.strip()
            return attention_units or None
        except Exception as exc:
            if not self._advisor_error_logged:
                self.logger.error(
                    "Enemy composition unit lookup failed: %s",
                    exc,
                )
                self._advisor_error_logged = True
            return None


_default_advisor: Optional[EnemyCompositionUnitAdvisor] = None


def get_enemy_composition_unit_advisor() -> EnemyCompositionUnitAdvisor:
    """Return the process-local advisor shared by reminder managers."""

    global _default_advisor
    if _default_advisor is None:
        _default_advisor = EnemyCompositionUnitAdvisor()
    return _default_advisor


__all__ = [
    "EnemyCompositionUnitAdvisor",
    "EnemyCompositionUnitEntry",
    "SUPPORTED_TIERS",
    "extract_tier",
    "get_enemy_composition_unit_advisor",
]
