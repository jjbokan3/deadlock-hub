"""Main patch notes parser — tokenizes raw text into structured data."""
from __future__ import annotations
import re
import logging
from typing import Optional

from models import (
    Change, ChangeType, ParsedPatchNotes,
    HeroChangeGroup, ItemChangeGroup, ChangeDirection,
)
from api import DeadlockAPI
from parser import detect_direction, extract_values

logger = logging.getLogger(__name__)

# Hero name aliases: display text in patch notes → API name
HERO_ALIASES = {
    "doorman": "the doorman",
    # Add any future aliases here
}


def _normalize_name(name: str) -> str:
    """Normalize a name for matching (lowercase, strip whitespace)."""
    n = name.strip().lower()
    return HERO_ALIASES.get(n, n)


def _split_entity_line(line: str) -> tuple[Optional[str], str]:
    """Split a patch note line into (entity_name, change_text).

    Returns (None, full_line) if no colon-separated entity found.
    Handles entity names that may contain colons (unlikely but safe).
    """
    # Find the first colon
    idx = line.find(":")
    if idx == -1:
        return None, line.strip()

    prefix = line[:idx].strip()
    rest = line[idx + 1:].strip()

    # Sanity check: entity names shouldn't be too long
    if len(prefix) > 50:
        return None, line.strip()

    return prefix, rest


def parse(raw_text: str, api: DeadlockAPI) -> ParsedPatchNotes:
    """Parse raw patch notes text into structured data.

    Args:
        raw_text: The full patch notes as plain text (dash-prefixed lines).
        api: Loaded DeadlockAPI instance with hero/item indexes.

    Returns:
        ParsedPatchNotes with all changes categorized and enriched.
    """
    result = ParsedPatchNotes()
    lines = raw_text.strip().splitlines()
    in_street_brawl = False

    for raw_line in lines:
        line = raw_line.strip()

        # Skip empty lines and non-change lines
        if not line:
            continue

        # Detect section markers like [ Street Brawl ]
        section_match = re.match(r'^\[?\s*\[([^\]]+)\]\s*\]?$', line)
        if section_match:
            section_name = section_match.group(1).strip().lower()
            in_street_brawl = "street brawl" in section_name
            continue

        if line.startswith("-"):
            line = line[1:].strip()
        elif not any(c.isalpha() for c in line):
            continue

        # Try to split into entity: change
        entity_name, change_text = _split_entity_line(line)

        if entity_name:
            normalized = _normalize_name(entity_name)

            # Check for "Brawl <HeroName>" prefix (Street Brawl hero changes)
            brawl_match = re.match(r'^brawl\s+(.+)$', normalized, re.IGNORECASE)
            if brawl_match:
                brawl_hero = _normalize_name(brawl_match.group(1))
                if brawl_hero in api.hero_names:
                    _process_hero_change(result, api, brawl_match.group(1).strip(), brawl_hero, change_text, raw_line, street_brawl=True)
                    continue

            # Check if it's a hero
            if normalized in api.hero_names:
                _process_hero_change(result, api, entity_name, normalized, change_text, raw_line, in_street_brawl)
                continue

            # Check if it's an item (by display name)
            if normalized in api.item_names:
                _process_item_change(result, api, entity_name, normalized, change_text, raw_line, in_street_brawl)
                continue

            # Could be an item not in our known set, or a system change with a colon
            # Try fuzzy matching on items
            item = _fuzzy_match_item(api, entity_name)
            if item:
                _process_item_change(result, api, item.name, item.name.lower(), change_text, raw_line, in_street_brawl)
                continue

        # System change (no matching entity)
        direction = detect_direction(change_text if entity_name else line)
        old_val, new_val = extract_values(change_text if entity_name else line)
        result.system_changes.append(Change(
            text=line,
            direction=direction,
            change_type=ChangeType.BASE_STAT,
            old_value=old_val,
            new_value=new_val,
            raw_line=raw_line,
            street_brawl=in_street_brawl,
        ))

    # Log summary
    logger.info(
        f"Parsed: {len(result.system_changes)} system, "
        f"{len(result.item_changes)} items, "
        f"{len(result.hero_changes)} heroes"
    )

    return result


def _process_hero_change(
    result: ParsedPatchNotes,
    api: DeadlockAPI,
    display_name: str,
    normalized: str,
    change_text: str,
    raw_line: str,
    street_brawl: bool = False,
):
    """Process a single hero change line."""
    hero_data = api.get_hero(normalized) or api.get_hero(display_name)
    if not hero_data:
        logger.warning(f"Hero '{display_name}' not found in API data")
        return

    # Create group if needed
    key = hero_data.name
    if key not in result.hero_changes:
        result.hero_changes[key] = HeroChangeGroup(hero=hero_data)

    group = result.hero_changes[key]

    # Detect direction
    direction = detect_direction(change_text)
    old_val, new_val = extract_values(change_text)

    # Try to match an ability
    ability_match = api.find_ability(change_text, hero_data.name)

    # Determine change type
    is_fix = "fixed" in change_text.lower()

    if is_fix:
        change_type = ChangeType.BUG_FIX
        ability_slot = ability_match[0].slot if ability_match else None
        ability_name = ability_match[0].name if ability_match else None
        tier = ability_match[1] if ability_match else None
    elif ability_match:
        ability_info, tier = ability_match
        ability_slot = ability_info.slot
        ability_name = ability_info.name
        change_type = ChangeType.ABILITY_TIER if tier else ChangeType.ABILITY
    else:
        ability_slot = None
        ability_name = None
        tier = None
        change_type = ChangeType.BASE_STAT

    group.changes.append(Change(
        text=change_text,
        direction=direction,
        ability_slot=ability_slot,
        ability_name=ability_name,
        tier=tier,
        change_type=change_type,
        old_value=old_val,
        new_value=new_val,
        raw_line=raw_line,
        street_brawl=street_brawl,
    ))


def _process_item_change(
    result: ParsedPatchNotes,
    api: DeadlockAPI,
    display_name: str,
    normalized: str,
    change_text: str,
    raw_line: str,
    street_brawl: bool = False,
):
    """Process a single item change line."""
    item_data = api.get_item(normalized) or api.get_item(display_name)
    if not item_data:
        logger.warning(f"Item '{display_name}' not found in API data")
        return

    key = item_data.name
    if key not in result.item_changes:
        result.item_changes[key] = ItemChangeGroup(item=item_data)

    group = result.item_changes[key]

    direction = detect_direction(change_text)
    old_val, new_val = extract_values(change_text)

    group.changes.append(Change(
        text=change_text,
        direction=direction,
        change_type=ChangeType.BASE_STAT,
        old_value=old_val,
        new_value=new_val,
        raw_line=raw_line,
        street_brawl=street_brawl,
    ))


def _fuzzy_match_item(api: DeadlockAPI, name: str):
    """Try to match an item name with minor variations."""
    normalized = name.strip().lower()

    # Direct match already failed, try common variations
    # e.g., "Golden Goose Egg" might be stored differently
    for item_name, item_data in api.items_by_name.items():
        # Check if the patch note name is a substring or vice versa
        if normalized in item_name or item_name in normalized:
            return item_data

    return None
