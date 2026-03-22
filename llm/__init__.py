"""LLM provider interface and factory.

Supports Claude (Anthropic), OpenAI, and Ollama out of the box.
Add new providers by subclassing LLMProvider and registering in PROVIDERS.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional
import json
import logging

from models import LLMRating, Change

logger = logging.getLogger(__name__)


# ── Prompt template ──────────────────────────────────────────────

RATING_PROMPT = """You are a Deadlock balance analyst rating patch note changes for **{entity_name}** ({entity_type}).

Changes:
{changes_text}

Pre-detected directions:
{directions_text}

Review the pre-detected directions above. If any are wrong, include corrections.
In Deadlock, "inverted stats" exist: for cooldown, cast time, deploy time, reload time, wind up time,
wait time, lockout, and stamina cooldown — INCREASES are NERFS and DECREASES are BUFFS.
"No longer grants" = nerf. "Now also grants" = buff. Reworks with clear tradeoffs = neutral.

Respond with JSON only. No markdown fences, no preamble.
{{
  "rating": <integer 1-5>,
  "explanation": "<2-4 sentences. Name the most impactful changes. Note tradeoffs. State how this affects the hero/item's role or build path.>",
  "direction_corrections": {{<change_number>: "<buff|nerf|neutral>"}}
}}
"direction_corrections" should ONLY include entries where the pre-detected direction is wrong. Omit it or use {{}} if all are correct.

RATING SCALE — read carefully, the difference between tiers matters:

★☆☆☆☆ 1 = HUGE NERF — the hero/item's core identity or primary build path is fundamentally weakened.
  What qualifies:
  - A signature ability's spirit scaling cut by 30%+ (scaling compounds with items all game)
  - Multiple abilities nerfed simultaneously with no compensating buffs
  - A core mechanic removed or reworked into something strictly worse
  - A systemic change (e.g. 30% lifesteal effectiveness penalty) that invalidates an entire build path
  - An ultimate's range/damage/cooldown ALL hit in the same patch
  What does NOT qualify: a single stat trim, one ability touched, or small number adjustments

★★☆☆☆ 2 = NERF — clearly weaker, but the hero/item still functions in its role.
  What qualifies:
  - One ability's scaling or core stat meaningfully reduced
  - A cooldown increase on a key ability (10-20s on a non-ult)
  - Losing a stat from an item (e.g. an item losing its ability range bonus entirely)
  - Range/radius reductions that make an ability noticeably harder to land
  - A single significant numerical downgrade (e.g. resist 15% → 12%)
  Most single-change nerfs land here unless the change is extreme.

★★★☆☆ 3 = MIXED / NEUTRAL — buffs and nerfs roughly cancel, or changes are lateral.
  What qualifies:
  - Ability reworked with clear tradeoffs (lost damage amp, gained damage reduction)
  - Bug fixes that correct unintended behavior (even if it was beneficial)
  - QoL improvements with no power change (minimap indicators, visual updates)
  - One buff and one nerf of similar magnitude on the same hero
  - Tier upgrade reshuffling that moves power around without clearly adding or removing it

★★★★☆ 4 = BUFF — clearly stronger, meaningful improvement to gameplay.
  What qualifies:
  - Damage, scaling, or core stat increased on a key ability
  - Cooldown reduction on important abilities
  - New functionality added to an ability ("can now target units", "now also grants X")
  - Base stat improvements (more ammo, faster reload, more stamina)
  - Usability improvements that make abilities easier to land (wider, faster, longer range)
  Most single-change buffs land here unless the change is extreme.

★★★★★ 5 = HUGE BUFF — the hero/item is substantially stronger across multiple dimensions.
  What qualifies:
  - 3+ abilities buffed with no compensating nerfs
  - A signature ability gains major new functionality AND numerical buffs
  - Multiple core stats improved (damage + scaling + cooldown + range)
  - An ultimate reworked to be dramatically more reliable or powerful
  What does NOT qualify: a single strong buff, or buffs to peripheral stats

KEY PRINCIPLES FOR DEADLOCK BALANCE:
- Spirit scaling is the highest-leverage stat. It multiplies with every spirit item purchased.
  A scaling change from 1.2 → 0.6 (halved) is catastrophic. From 0.42 → 0.56 (+33%) is very strong.
- Movement speed changes are disproportionately impactful — speed creates options that raw
  stats cannot compensate for. Gaining/losing even 1-2 m/s matters.
- Changes to a hero's SIGNATURE ability (what defines their playstyle) matter far more than
  changes to peripheral abilities. Mo & Krill's Combo IS their hero. Nerfing Combo is existential.
- Ultimate changes weigh more than basic ability changes — longer cooldowns mean each cast matters more.
- Flat damage changes (±5 damage) matter in lane phase but fall off. Scaling changes compound all game.
- Build path disruption matters: if a change forces entirely new itemization (e.g. lifesteal
  effectiveness penalty), the true cost is higher than the number suggests.
- Ability range/radius changes affect consistency — a wider Kinetic Pulse means more reliable CC
  even if damage went down. Judge the net impact on actual gameplay, not just the numbers.
- For items: losing a secondary stat (e.g. ability range removed from Echo Shard) is a nerf to the
  item's slot efficiency, not just that stat. Players may drop the item entirely.
- Context from global changes matters: if ability range was nerfed across 12 items in the same patch,
  a hero who also lost range on their abilities is hit harder than the numbers alone suggest."""


def _build_prompt(entity_name: str, entity_type: str, changes: list[Change]) -> str:
    changes_lines = []
    directions_lines = []
    for i, c in enumerate(changes, 1):
        detail_parts = [c.text]
        if c.ability_name:
            detail_parts.append(f"[Ability {c.ability_slot}: {c.ability_name}]")
        if c.tier:
            detail_parts.append(f"[Tier {c.tier}]")
        if c.old_value and c.new_value:
            detail_parts.append(f"[{c.old_value} → {c.new_value}]")
        changes_lines.append(f"  {i}. {' '.join(detail_parts)}")
        directions_lines.append(f"  {i}. {c.direction.value}")

    return RATING_PROMPT.format(
        entity_name=entity_name,
        entity_type=entity_type,
        changes_text="\n".join(changes_lines),
        directions_text="\n".join(directions_lines),
    )


def _parse_rating_response(raw: str) -> tuple[LLMRating, dict[int, str]]:
    """Parse the JSON response from the LLM into an LLMRating and direction corrections.

    Returns:
        (LLMRating, corrections dict mapping 1-based change index to new direction string)
    """
    # Strip markdown fences if present
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = "\n".join(cleaned.split("\n")[1:])
    if cleaned.endswith("```"):
        cleaned = "\n".join(cleaned.split("\n")[:-1])
    cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse LLM response as JSON: {raw[:200]}")
        return LLMRating.from_score(3, "Unable to parse LLM response."), {}

    rating = int(data.get("rating", 3))
    explanation = data.get("explanation", "")

    # Parse direction corrections (keys are 1-based change indices)
    corrections = {}
    raw_corrections = data.get("direction_corrections", {})
    for key, val in raw_corrections.items():
        try:
            idx = int(key)
            if val in ("buff", "nerf", "neutral"):
                corrections[idx] = val
        except (ValueError, TypeError):
            continue

    return LLMRating.from_score(rating, explanation), corrections


# ── Abstract provider ────────────────────────────────────────────

class LLMProvider(ABC):
    """Abstract base class for LLM providers.

    Tracks call count and enforces safety limits for cloud providers.
    """

    # Safety defaults — override per-provider or via kwargs
    max_calls: int = 200         # max LLM calls per session
    max_prompt_chars: int = 8000  # sanity check per prompt
    warn_at_calls: int = 150      # log a warning at this count

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

    def __init__(self, **kwargs):
        self._call_count = 0
        self._skip_count = 0
        # Allow overriding limits via kwargs
        if "max_calls" in kwargs:
            self.max_calls = int(kwargs.pop("max_calls"))

    @property
    def calls_made(self) -> int:
        return self._call_count

    @property
    def calls_skipped(self) -> int:
        return self._skip_count

    @property
    def budget_remaining(self) -> int:
        return max(0, self.max_calls - self._call_count)

    @abstractmethod
    def complete(self, prompt: str, system: str = "") -> str:
        """Send a prompt and return the raw text response."""
        ...

    def _guarded_complete(self, prompt: str, system: str = "") -> str:
        """Call complete() with safety checks."""
        # Budget check
        if self._call_count >= self.max_calls:
            self._skip_count += 1
            raise BudgetExhaustedError(
                f"LLM call budget exhausted ({self.max_calls} calls). "
                f"Skipped {self._skip_count} call(s). "
                f"Increase with --max-llm-calls."
            )

        # Prompt size sanity check
        if len(prompt) > self.max_prompt_chars:
            logger.warning(
                f"Prompt too large ({len(prompt)} chars > {self.max_prompt_chars} limit). "
                f"Truncating to avoid runaway token usage."
            )
            prompt = prompt[:self.max_prompt_chars] + "\n\n[TRUNCATED]"

        # Warning at threshold
        if self._call_count == self.warn_at_calls:
            logger.warning(
                f"LLM call count at {self.warn_at_calls}/{self.max_calls}. "
                f"{self.budget_remaining} calls remaining."
            )

        self._call_count += 1
        return self.complete(prompt, system=system)

    def rate_changes(self, entity_name: str, entity_type: str, changes: list[Change]) -> LLMRating:
        """Rate a group of changes for a single entity. Returns LLMRating."""
        from models import ChangeDirection

        # Exclude Street Brawl changes from rating — they don't affect normal Deadlock
        rated_changes = [c for c in changes if not c.street_brawl]
        if not rated_changes:
            return LLMRating.from_score(3, "Street Brawl only — no impact on standard mode.")
        prompt = _build_prompt(entity_name, entity_type, rated_changes)
        system = (
            "You are a Deadlock balance analyst. Respond only with valid JSON. "
            "No markdown, no explanation outside the JSON."
        )
        try:
            raw = self._guarded_complete(prompt, system=system)
            rating, corrections = _parse_rating_response(raw)

            # Apply direction corrections from LLM back to the change objects
            if corrections:
                direction_map = {"buff": ChangeDirection.BUFF, "nerf": ChangeDirection.NERF, "neutral": ChangeDirection.NEUTRAL}
                for idx, new_dir in corrections.items():
                    if 1 <= idx <= len(rated_changes):
                        old_dir = rated_changes[idx - 1].direction
                        rated_changes[idx - 1].direction = direction_map[new_dir]
                        logger.info(f"  LLM corrected {entity_name} change #{idx}: {old_dir.value} → {new_dir}")

            return rating
        except BudgetExhaustedError:
            logger.warning(f"Budget exhausted — using heuristic for {entity_name}")
            return HeuristicProvider().rate_changes(entity_name, entity_type, changes)
        except Exception as e:
            logger.error(f"LLM call failed for {entity_name}: {e}")
            return LLMRating.from_score(3, f"LLM error: {e}")


    def summarize_patch(self, data) -> str:
        """Generate a 1-2 sentence summary of the overall patch."""
        from models import ParsedPatchNotes, ChangeDirection
        parsed: ParsedPatchNotes = data

        hero_count = len(parsed.hero_changes)
        item_count = len(parsed.item_changes)
        system_count = len(parsed.system_changes)

        # Gather all non-street-brawl ratings
        hero_ratings = [g.rating.rating for g in parsed.hero_changes.values() if g.rating and not all(c.street_brawl for c in g.changes)]
        item_ratings = [g.rating.rating for g in parsed.item_changes.values() if g.rating and not all(c.street_brawl for c in g.changes)]

        # Count buff/nerf directions across all non-street-brawl changes
        all_changes = []
        for g in parsed.hero_changes.values():
            all_changes.extend(c for c in g.changes if not c.street_brawl)
        for g in parsed.item_changes.values():
            all_changes.extend(c for c in g.changes if not c.street_brawl)
        all_changes.extend(c for c in parsed.system_changes if not c.street_brawl)

        buffs = sum(1 for c in all_changes if c.direction == ChangeDirection.BUFF)
        nerfs = sum(1 for c in all_changes if c.direction == ChangeDirection.NERF)

        summary_parts = []
        summary_parts.append(f"{hero_count} heroes, {item_count} items, and {system_count} system changes")

        prompt = (
            f"You are summarizing a Deadlock patch for a patch notes website. "
            f"Write 1-2 concise sentences capturing the overall theme.\n\n"
            f"Stats: {hero_count} heroes changed, {item_count} items changed, {system_count} system changes. "
            f"{buffs} buffs, {nerfs} nerfs across all changes.\n\n"
            f"Heroes changed: {', '.join(sorted(parsed.hero_changes.keys()))}\n"
            f"Items changed: {', '.join(sorted(parsed.item_changes.keys()))}\n\n"
            f"System changes:\n" + "\n".join(f"- {c.text}" for c in parsed.system_changes[:10]) + "\n\n"
            f"Hero rating breakdown (1=huge nerf, 5=big buff): "
            + ", ".join(f"{name}: {g.rating.rating}" for name, g in sorted(parsed.hero_changes.items()) if g.rating)
            + "\n\nRespond with ONLY the summary text, no quotes or formatting."
        )

        try:
            return self._guarded_complete(prompt, system="You are a concise Deadlock patch analyst.").strip()
        except Exception as e:
            logger.warning(f"Summary generation failed: {e}")
            return _heuristic_summary(parsed)


def _heuristic_summary(data) -> str:
    """Generate a simple heuristic summary without LLM."""
    from models import ChangeDirection

    hero_count = len(data.hero_changes)
    item_count = len(data.item_changes)
    system_count = len(data.system_changes)

    all_changes = []
    for g in data.hero_changes.values():
        all_changes.extend(c for c in g.changes if not c.street_brawl)
    for g in data.item_changes.values():
        all_changes.extend(c for c in g.changes if not c.street_brawl)
    all_changes.extend(c for c in data.system_changes if not c.street_brawl)

    buffs = sum(1 for c in all_changes if c.direction == ChangeDirection.BUFF)
    nerfs = sum(1 for c in all_changes if c.direction == ChangeDirection.NERF)
    total = len(all_changes)

    # Determine patch character
    parts = []
    if hero_count >= 15:
        parts.append(f"massive hero update touching {hero_count} heroes")
    elif hero_count >= 8:
        parts.append(f"broad hero balance pass across {hero_count} heroes")
    elif hero_count > 0:
        parts.append(f"{hero_count} hero changes")

    if item_count >= 20:
        parts.append(f"sweeping item adjustments to {item_count} items")
    elif item_count >= 10:
        parts.append(f"significant item rebalancing across {item_count} items")
    elif item_count > 0:
        parts.append(f"{item_count} item changes")

    size = "Large" if total >= 80 else "Mid-sized" if total >= 30 else "Focused"
    direction = ""
    if nerfs > buffs * 1.5:
        direction = ", leaning heavily toward nerfs"
    elif nerfs > buffs:
        direction = ", leaning toward nerfs"
    elif buffs > nerfs * 1.5:
        direction = ", leaning heavily toward buffs"
    elif buffs > nerfs:
        direction = ", leaning toward buffs"

    return f"{size} patch with {' and '.join(parts)}{direction}. {buffs} buffs, {nerfs} nerfs across {total} total changes."


class BudgetExhaustedError(Exception):
    """Raised when the LLM call budget is spent."""
    pass


# ── Heuristic fallback (no LLM needed) ──────────────────────────

class HeuristicProvider(LLMProvider):
    """Simple buff/nerf ratio heuristic. No API calls."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.max_calls = 999999  # no limit for heuristic

    def complete(self, prompt: str, system: str = "") -> str:
        return ""  # not used

    def rate_changes(self, entity_name: str, entity_type: str, changes: list[Change]) -> LLMRating:
        # Exclude Street Brawl changes from rating
        rated_changes = [c for c in changes if not c.street_brawl]
        if not rated_changes:
            return LLMRating.from_score(3, "Street Brawl only — no impact on standard mode.")
        buffs = sum(1 for c in rated_changes if c.direction.value == "buff")
        nerfs = sum(1 for c in rated_changes if c.direction.value == "nerf")
        neutrals = len(rated_changes) - buffs - nerfs
        total = buffs + nerfs

        if total == 0:
            return LLMRating.from_score(3, "Only neutral changes (fixes or QoL adjustments).")

        ratio = buffs / total

        # Base score from ratio
        if ratio >= 0.85:
            score = 5
        elif ratio >= 0.65:
            score = 4
        elif ratio >= 0.35:
            score = 3
        elif ratio >= 0.15:
            score = 2
        else:
            score = 1

        # Dampen extreme ratings (1 and 5) when there are few changes.
        # "Huge Nerf" and "Big Buff" require 3+ directional changes to earn.
        if total < 3 and score in (1, 5):
            score = 2 if score == 1 else 4

        label = LLMRating.LABELS[score]
        parts = []
        if buffs:
            parts.append(f"{buffs} buff(s)")
        if nerfs:
            parts.append(f"{nerfs} nerf(s)")
        if neutrals:
            parts.append(f"{neutrals} neutral")
        return LLMRating.from_score(
            score,
            f"{label}. {' and '.join(parts)} across {len(changes)} change(s)."
        )

    def summarize_patch(self, data) -> str:
        return _heuristic_summary(data)


# ── Provider registry ────────────────────────────────────────────

PROVIDERS: dict[str, type[LLMProvider]] = {
    "heuristic": HeuristicProvider,
}


def _register_optional_providers():
    """Register providers whose dependencies might not be installed."""
    try:
        from llm.claude_provider import ClaudeProvider
        PROVIDERS["claude"] = ClaudeProvider
    except ImportError:
        pass

    try:
        from llm.openai_provider import OpenAIProvider
        PROVIDERS["openai"] = OpenAIProvider
    except ImportError:
        pass

    try:
        from llm.ollama_provider import OllamaProvider
        PROVIDERS["ollama"] = OllamaProvider
    except ImportError:
        pass


_register_optional_providers()


def get_provider(name: str, **kwargs) -> LLMProvider:
    """Factory function to get an LLM provider by name.

    Args:
        name: One of 'claude', 'openai', 'ollama', 'heuristic'
        **kwargs: Provider-specific config (model, api_key, base_url, etc.)

    Returns:
        Configured LLMProvider instance.
    """
    # Re-register in case imports became available
    _register_optional_providers()

    if name not in PROVIDERS:
        available = ", ".join(sorted(PROVIDERS.keys()))
        raise ValueError(f"Unknown provider '{name}'. Available: {available}")

    return PROVIDERS[name](**kwargs)
