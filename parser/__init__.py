"""Buff/nerf/neutral direction detection for patch note changes."""
from __future__ import annotations
import re
from models import ChangeDirection

# Stats where "increased" means NERF and "reduced" means BUFF
INVERTED_STATS = {
    "cooldown",
    "cast time",
    "deploy time",
    "reload time",
    "wind up time",
    "wind-up time",
    "windup time",
    "wait time",
    "lockout",
    "channel time",
    "stamina cooldown",
    "interrupt cooldown",
    "displacement duration",  # less knockback = less CC for the enemy, debatable
}

# Patterns that always indicate a specific direction regardless of context
ALWAYS_BUFF = [
    "now grants",
    "now also grants",
    "now also increases",
    "now also reduces cooldown",
    "now also deals",
    "now also replenishes",
    "can now",
    "now benefits from",
    "now has a ",
    "now continuously",
    "now summons",
    "now continues forward",
]

ALWAYS_NERF = [
    "no longer grants",
    "no longer increases",
    "no longer does",
    "no longer applies",
    "no longer gets",
    "removed",
]

ALWAYS_NEUTRAL = [
    "fixed",
    "reworked",
    "now uses",
    "now shows",
    "now has a break-off",  # QoL, not power
    "visuals improved",
    "now randomly pulls",
]


def detect_direction(text: str) -> ChangeDirection:
    """Determine if a change line is a buff, nerf, or neutral.

    Uses keyword matching with context-aware stat inversion for
    stats like cooldown where "reduced" is a buff.
    """
    t = text.lower().strip()

    # Check neutral patterns first (fixes, visual changes)
    for pattern in ALWAYS_NEUTRAL:
        if pattern in t:
            return ChangeDirection.NEUTRAL

    # Check always-buff patterns
    for pattern in ALWAYS_BUFF:
        if pattern in t:
            return ChangeDirection.BUFF

    # Check always-nerf patterns
    for pattern in ALWAYS_NERF:
        if pattern in t:
            return ChangeDirection.NERF

    # Context-dependent: determine if the stat is "inverted"
    is_inverted = any(stat in t for stat in INVERTED_STATS)

    # Check for increase/decrease verbs
    has_increase = any(w in t for w in ["increased", "improved", "faster"])
    has_decrease = any(w in t for w in ["reduced", "decreased", "worsened", "less effective"])

    if has_increase and has_decrease:
        # Both present (e.g., "duration increased, cooldown increased") — mixed
        return ChangeDirection.NEUTRAL

    if has_increase:
        return ChangeDirection.NERF if is_inverted else ChangeDirection.BUFF

    if has_decrease:
        return ChangeDirection.BUFF if is_inverted else ChangeDirection.NERF

    # "changed from X to Y" without clear direction
    if "changed from" in t:
        return ChangeDirection.NEUTRAL

    # "rescaled" — could go either way
    if "rescaled" in t:
        return ChangeDirection.NEUTRAL

    return ChangeDirection.NEUTRAL


def extract_values(text: str) -> tuple[str | None, str | None]:
    """Extract old and new values from 'from X to Y' patterns.

    Returns (old_value, new_value) or (None, None).
    """
    match = re.search(
        r'from\s+(["\']?[\d.+\-/%]+\w*["\']?(?:\s*(?:within|and)\s*[\d.+\-/%]+\w*)?)'
        r'\s+to\s+'
        r'(["\']?[\d.+\-/%]+\w*["\']?(?:\s*(?:within|and)\s*[\d.+\-/%]+\w*)?)',
        text,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip(), match.group(2).strip()

    # "by X%" pattern
    match = re.search(r'by\s+([\d.+\-]+%?)', text, re.IGNORECASE)
    if match:
        return None, match.group(1).strip()

    return None, None
