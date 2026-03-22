"""Deadlock Assets API client with local file caching."""
from __future__ import annotations
import json
import os
import time
import logging
from typing import Optional
import requests

from models import (
    HeroData, ItemData, AbilityInfo, ItemCategory, ITEM_SLOT_MAP
)

logger = logging.getLogger(__name__)

HEROES_URL = "https://assets.deadlock-api.com/v2/heroes"
ITEMS_URL = "https://assets.deadlock-api.com/v2/items"
CACHE_DIR = ".cache"
CACHE_TTL = 3600 * 6  # 6 hours


def _fetch_with_cache(url: str, cache_key: str, ttl: int = CACHE_TTL) -> list[dict]:
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, f"{cache_key}.json")

    if os.path.exists(cache_path):
        age = time.time() - os.path.getmtime(cache_path)
        if age < ttl:
            logger.info(f"Using cached {cache_key} ({age:.0f}s old)")
            with open(cache_path) as f:
                return json.load(f)

    logger.info(f"Fetching {url}")
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    with open(cache_path, "w") as f:
        json.dump(data, f)

    logger.info(f"Cached {len(data)} entries for {cache_key}")
    return data


class DeadlockAPI:
    """Fetches and indexes hero/item data from the Deadlock Assets API."""

    def __init__(self):
        self.heroes_by_name: dict[str, HeroData] = {}
        self.items_by_name: dict[str, ItemData] = {}
        self.items_by_class: dict[str, ItemData] = {}
        # ability display name (lower) → (hero_name, slot)
        self.ability_lookup: dict[str, tuple[str, int]] = {}
        # All known hero names (lowercase) for matching
        self.hero_names: set[str] = set()
        # All known item display names (lowercase) for matching
        self.item_names: set[str] = set()

        self._raw_heroes: list[dict] = []
        self._raw_items: list[dict] = []

    def load(self):
        """Fetch both endpoints and build all lookup indexes."""
        self._raw_heroes = _fetch_with_cache(HEROES_URL, "heroes")
        self._raw_items = _fetch_with_cache(ITEMS_URL, "items")
        self._index_items()
        self._index_heroes()
        logger.info(
            f"Indexed {len(self.heroes_by_name)} heroes, "
            f"{len(self.items_by_name)} items, "
            f"{len(self.ability_lookup)} abilities"
        )

    def _index_items(self):
        # Try multiple possible field names for category
        CATEGORY_FIELDS = ["item_slot_type", "type", "shop_filter", "category", "item_type"]
        CATEGORY_VALUE_MAP = {
            # EItemSlotType enum style
            "EItemSlotType_Weapon": ItemCategory.WEAPON,
            "EItemSlotType_Armor": ItemCategory.VITALITY,
            "EItemSlotType_Tech": ItemCategory.SPIRIT,
            # Simple lowercase
            "weapon": ItemCategory.WEAPON,
            "armor": ItemCategory.VITALITY,
            "vitality": ItemCategory.VITALITY,
            "tech": ItemCategory.SPIRIT,
            "spirit": ItemCategory.SPIRIT,
            # Capitalized
            "Weapon": ItemCategory.WEAPON,
            "Armor": ItemCategory.VITALITY,
            "Vitality": ItemCategory.VITALITY,
            "Tech": ItemCategory.SPIRIT,
            "Spirit": ItemCategory.SPIRIT,
        }

        unknown_shop_items = []

        for raw in self._raw_items:
            name = raw.get("name", "")
            class_name = raw.get("class_name", "")
            if not name or not class_name:
                continue

            # Try each possible field name for category
            category = ItemCategory.UNKNOWN
            for field in CATEGORY_FIELDS:
                val = raw.get(field, "")
                if val and val in CATEGORY_VALUE_MAP:
                    category = CATEGORY_VALUE_MAP[val]
                    break

            # Item tier — try multiple structures
            tier = None
            tier_info = raw.get("item_tier")
            if isinstance(tier_info, dict):
                tier = tier_info.get("tier")
            elif isinstance(tier_info, (int, float)):
                tier = int(tier_info)

            is_shop_item = class_name.startswith("upgrade_")

            item = ItemData(
                name=name,
                class_name=class_name,
                category=category,
                image=raw.get("image"),
                tier=tier,
            )
            self.items_by_name[name.lower()] = item
            self.items_by_class[class_name.lower()] = item

            # Register as a matchable shop item if it's an upgrade
            if is_shop_item:
                self.item_names.add(name.lower())
                if category == ItemCategory.UNKNOWN:
                    unknown_shop_items.append((name, class_name))

        if unknown_shop_items:
            logger.warning(
                f"{len(unknown_shop_items)} shop items have no category. "
                f"Run 'python debug_items.py' to inspect API fields. "
                f"First 5: {[n for n, _ in unknown_shop_items[:5]]}"
            )
            # Dump the first item's raw keys for diagnosis
            if self._raw_items:
                for raw in self._raw_items:
                    if raw.get("class_name", "").startswith("upgrade_"):
                        keys = [k for k in sorted(raw.keys())
                                if k not in ("properties", "description", "upgrades")]
                        logger.warning(f"Sample shop item fields: {keys}")
                        break

    def _index_heroes(self):
        for raw in self._raw_heroes:
            name = raw.get("name", "")
            if not name:
                continue

            # Skip non-playable heroes
            if not raw.get("player_selectable", False):
                continue

            images = raw.get("images", {})
            hero = HeroData(
                name=name,
                image=images.get("icon_hero_card") or images.get("icon_image_small"),
            )

            # Resolve abilities (signature1-4)
            items_block = raw.get("items", {})
            for slot in range(1, 5):
                sig_key = f"signature{slot}"
                class_name = items_block.get(sig_key, "")
                if not class_name:
                    continue

                # Look up the ability in items data to get display name + image
                item = self.items_by_class.get(class_name.lower())
                if item:
                    ability = AbilityInfo(
                        name=item.name,
                        slot=slot,
                        class_name=class_name,
                        image=item.image,
                    )
                    hero.abilities[slot] = ability
                    # Register display name for ability matching
                    self.ability_lookup[item.name.lower()] = (name, slot)

            self.heroes_by_name[name.lower()] = hero
            self.hero_names.add(name.lower())

    def get_hero(self, name: str) -> Optional[HeroData]:
        return self.heroes_by_name.get(name.lower())

    def get_item(self, name: str) -> Optional[ItemData]:
        return self.items_by_name.get(name.lower())

    def find_ability(self, text: str, hero_name: str) -> Optional[tuple[AbilityInfo, int]]:
        """Find which ability a change line refers to for a given hero.

        Returns (AbilityInfo, tier) or None.
        Searches for the longest matching ability name in the text.
        """
        hero = self.get_hero(hero_name)
        if not hero:
            return None

        text_lower = text.lower()
        best_match: Optional[AbilityInfo] = None
        best_len = 0

        for slot, ability in hero.abilities.items():
            aname = ability.name.lower()
            if aname in text_lower and len(aname) > best_len:
                best_match = ability
                best_len = len(aname)

        if not best_match:
            return None

        # Detect tier
        tier = None
        import re
        tier_match = re.search(r'\bT([1-3])\b', text)
        if tier_match:
            tier = int(tier_match.group(1))

        return (best_match, tier)
