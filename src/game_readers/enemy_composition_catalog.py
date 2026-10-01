"""The production Enemy Composition catalog.

This module is the single runtime source of truth for composition names.  The
Chinese names and aliases below are copied from the already-verified
``resources/enemy_compositions.json`` and the matching ``resources/enemy_comps``
CSV headers; they are not translations inferred at runtime.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Dict, Optional, Tuple


SUPPORTED_RACES = ("Terran", "Zerg", "Protoss")


def _normalized_key(value: str) -> str:
    return unicodedata.normalize("NFKC", str(value)).casefold()


@dataclass(frozen=True)
class EnemyCompositionEntry:
    """One verified production composition and its OCR aliases."""

    canonical_en: str
    display_zh: str
    race: str
    aliases: Tuple[str, ...]

    @property
    def canonical(self) -> str:
        """Compatibility name used by the existing benchmark helpers."""

        return self.canonical_en


# Keep this order stable so benchmark reports and diagnostic output remain
# reviewable.  Every alias is an existing verified spelling from the current
# production resource; the canonical English name is always included.
ENEMY_COMPOSITION_CATALOG: Tuple[EnemyCompositionEntry, ...] = (
    EnemyCompositionEntry(
        canonical_en="Machines of War",
        display_zh="战争机械团",
        race="Terran",
        aliases=("Machines of War", "战争机械团"),
    ),
    EnemyCompositionEntry(
        canonical_en="Shadow Tech",
        display_zh="暗影科技团",
        race="Terran",
        aliases=("Shadow Tech", "暗影科技团"),
    ),
    EnemyCompositionEntry(
        canonical_en="Classic Infantry",
        display_zh="旧世步兵团",
        race="Terran",
        aliases=("Classic Infantry", "旧世步兵团"),
    ),
    EnemyCompositionEntry(
        canonical_en="Classic Mech",
        display_zh="旧世机械团",
        race="Terran",
        aliases=("Classic Mech", "旧世机械团"),
    ),
    EnemyCompositionEntry(
        canonical_en="Dominion Battlegroup",
        display_zh="帝国战斗群",
        race="Terran",
        aliases=("Dominion Battlegroup", "帝国战斗群"),
    ),
    EnemyCompositionEntry(
        canonical_en="Raiding Party",
        display_zh="突击团",
        race="Terran",
        aliases=("Raiding Party", "突击团"),
    ),
    EnemyCompositionEntry(
        canonical_en="Devouring Scourge",
        display_zh="遮天蔽日",
        race="Zerg",
        aliases=("Devouring Scourge", "遮天蔽日"),
    ),
    EnemyCompositionEntry(
        canonical_en="Ravaging Infestation",
        display_zh="肆虐扩散",
        race="Zerg",
        aliases=("Ravaging Infestation", "肆虐扩散"),
    ),
    EnemyCompositionEntry(
        canonical_en="Invasionary Swarm",
        display_zh="侵略虫群",
        race="Zerg",
        aliases=("Invasionary Swarm", "侵略虫群"),
    ),
    EnemyCompositionEntry(
        canonical_en="Broodling Corruption",
        display_zh="滋生腐化",
        race="Zerg",
        aliases=("Broodling Corruption", "滋生腐化"),
    ),
    EnemyCompositionEntry(
        canonical_en="Explosive Threats",
        display_zh="爆炸威胁",
        race="Zerg",
        aliases=("Explosive Threats", "爆炸威胁"),
    ),
    EnemyCompositionEntry(
        canonical_en="Hope of the Khalai",
        display_zh="卡莱的希望",
        race="Protoss",
        aliases=("Hope of the Khalai", "卡莱的希望"),
    ),
    EnemyCompositionEntry(
        canonical_en="Shadow Disruption",
        display_zh="暗影袭扰",
        race="Protoss",
        aliases=("Shadow Disruption", "暗影袭扰"),
    ),
    EnemyCompositionEntry(
        canonical_en="Fleet of the Matriarch",
        display_zh="族长之军",
        race="Protoss",
        aliases=("Fleet of the Matriarch", "族长之军"),
    ),
    EnemyCompositionEntry(
        canonical_en="Vanguard of Aiur",
        display_zh="艾尔先锋",
        race="Protoss",
        aliases=("Vanguard of Aiur", "艾尔先锋"),
    ),
    EnemyCompositionEntry(
        canonical_en="Towering Walkers",
        display_zh="步战机甲",
        race="Protoss",
        aliases=("Towering Walkers", "步战机甲"),
    ),
    EnemyCompositionEntry(
        canonical_en="Masters and Machines",
        display_zh="大师机械",
        race="Protoss",
        aliases=("Masters and Machines", "大师机械"),
    ),
    EnemyCompositionEntry(
        canonical_en="Disruptive Artillery",
        display_zh="袭扰炮击",
        race="Protoss",
        aliases=("Disruptive Artillery", "袭扰炮击"),
    ),
    EnemyCompositionEntry(
        canonical_en="Siege of Storms",
        display_zh="风暴迫临",
        race="Protoss",
        aliases=("Siege of Storms", "风暴迫临"),
    ),
)


def _validate_catalog() -> None:
    seen_canonical = set()
    for entry in ENEMY_COMPOSITION_CATALOG:
        if not entry.canonical_en or not entry.canonical_en.isascii():
            raise ValueError("Enemy Composition canonical names must be non-empty ASCII")
        if not entry.display_zh:
            raise ValueError("Enemy Composition Chinese display names must be non-empty")
        if entry.race not in SUPPORTED_RACES:
            raise ValueError(f"Unsupported Enemy Composition race: {entry.race!r}")
        if not entry.aliases or entry.canonical_en not in entry.aliases:
            raise ValueError(
                f"Enemy Composition aliases must include {entry.canonical_en!r}"
            )
        canonical_key = _normalized_key(entry.canonical_en)
        if canonical_key in seen_canonical:
            raise ValueError(f"Duplicate Enemy Composition: {entry.canonical_en!r}")
        seen_canonical.add(canonical_key)


_validate_catalog()


_CATALOG_BY_CANONICAL: Dict[str, EnemyCompositionEntry] = {
    _normalized_key(entry.canonical_en): entry
    for entry in ENEMY_COMPOSITION_CATALOG
}


def get_enemy_composition_entry(
    canonical_en: str,
) -> Optional[EnemyCompositionEntry]:
    """Return a catalog entry by canonical English name."""

    return _CATALOG_BY_CANONICAL.get(_normalized_key(canonical_en))


def get_enemy_composition_display_name(canonical_en: str, language: str) -> str:
    """Resolve a user-facing name, falling back to canonical English."""

    entry = get_enemy_composition_entry(canonical_en)
    if entry is None:
        return str(canonical_en)
    if str(language).casefold() == "zh":
        return entry.display_zh
    return entry.canonical_en


__all__ = [
    "ENEMY_COMPOSITION_CATALOG",
    "EnemyCompositionEntry",
    "SUPPORTED_RACES",
    "get_enemy_composition_display_name",
    "get_enemy_composition_entry",
]
