"""Data models for parsed patch notes."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ChangeDirection(str, Enum):
    BUFF = "buff"
    NERF = "nerf"
    NEUTRAL = "neutral"


class ChangeType(str, Enum):
    BASE_STAT = "base_stat"
    ABILITY = "ability"
    ABILITY_TIER = "ability_tier"
    BUG_FIX = "bug_fix"
    REWORK = "rework"


class ItemCategory(str, Enum):
    WEAPON = "weapon"
    VITALITY = "vitality"
    SPIRIT = "spirit"
    UNKNOWN = "unknown"


ITEM_SLOT_MAP = {
    "EItemSlotType_Weapon": ItemCategory.WEAPON,
    "EItemSlotType_Armor": ItemCategory.VITALITY,
    "EItemSlotType_Tech": ItemCategory.SPIRIT,
}


@dataclass
class AbilityInfo:
    name: str
    slot: int  # 1-4
    class_name: str
    image: Optional[str] = None


@dataclass
class HeroData:
    name: str
    image: Optional[str] = None
    abilities: dict[int, AbilityInfo] = field(default_factory=dict)  # slot -> AbilityInfo


@dataclass
class ItemData:
    name: str
    class_name: str
    category: ItemCategory = ItemCategory.UNKNOWN
    image: Optional[str] = None
    tier: Optional[int] = None


@dataclass
class Change:
    """A single parsed change line."""
    text: str
    direction: ChangeDirection = ChangeDirection.NEUTRAL
    ability_slot: Optional[int] = None
    ability_name: Optional[str] = None
    tier: Optional[int] = None
    change_type: ChangeType = ChangeType.BASE_STAT
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    raw_line: str = ""
    street_brawl: bool = False
    date: Optional[str] = None  # e.g. "03-07-2026" — the date this change was posted


@dataclass
class LLMRating:
    rating: int  # 1-5
    label: str  # "Huge Nerf", "Nerf", "Mixed", "Buff", "Big Buff"
    explanation: str

    LABELS = {1: "Huge Nerf", 2: "Nerf", 3: "Mixed", 4: "Buff", 5: "Big Buff"}

    @classmethod
    def from_score(cls, rating: int, explanation: str) -> LLMRating:
        return cls(
            rating=max(1, min(5, rating)),
            label=cls.LABELS.get(rating, "Mixed"),
            explanation=explanation,
        )


@dataclass
class HeroChangeGroup:
    hero: HeroData
    changes: list[Change] = field(default_factory=list)
    rating: Optional[LLMRating] = None


@dataclass
class ItemChangeGroup:
    item: ItemData
    changes: list[Change] = field(default_factory=list)
    rating: Optional[LLMRating] = None


@dataclass
class ParsedPatchNotes:
    system_changes: list[Change] = field(default_factory=list)
    item_changes: dict[str, ItemChangeGroup] = field(default_factory=dict)
    hero_changes: dict[str, HeroChangeGroup] = field(default_factory=dict)
    title: str = ""
    summary: str = ""
