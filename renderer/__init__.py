"""HTML renderer — generates a split-pane patch notes page from structured data."""
from __future__ import annotations
import html as html_lib
import re
from models import (
    ParsedPatchNotes, HeroChangeGroup, ItemChangeGroup,
    Change, ChangeDirection, ItemCategory, LLMRating,
)

# ── Mapping helpers ──────────────────────────────────────────────

SLOT_COLORS = {1: "1", 2: "2", 3: "3", 4: "4"}
DIRECTION_SYMBOLS = {
    ChangeDirection.BUFF: ("▲", "buff"),
    ChangeDirection.NERF: ("▼", "nerf"),
    ChangeDirection.NEUTRAL: ("●", "neutral"),
}
RATING_LABELS = {1: "Huge Nerf", 2: "Nerf", 3: "Mixed", 4: "Buff", 5: "Big Buff"}
CATEGORY_META = {
    ItemCategory.WEAPON: ("Weapon Items", "weapon", "⚔"),
    ItemCategory.VITALITY: ("Vitality Items", "vitality", "♥"),
    ItemCategory.SPIRIT: ("Spirit Items", "spirit", "✦"),
    ItemCategory.UNKNOWN: ("Other Items", "spirit", "?"),
}


def _e(text: str) -> str:
    return html_lib.escape(text)


def _safe_id(name: str) -> str:
    """Convert a name to a URL-safe HTML id."""
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')


def _wiki_url(name: str) -> str:
    slug = name.replace(" ", "_").replace("&", "%26")
    return f"https://deadlock.wiki/{slug}"


# ── Change line rendering ────────────────────────────────────────

def _ability_wiki_url(hero_name: str, ability_slot: int, ability_name: str) -> str:
    hero_slug = hero_name.replace(" ", "_").replace("&", "%26")
    ability_slug = ability_name.replace(" ", "_")
    return f"https://deadlock.wiki/{hero_slug}#({ability_slot})_{ability_slug}"


def _render_change(c: Change, show_ability: bool = True, hero_name: str = "") -> str:
    sym, cls = DIRECTION_SYMBOLS.get(c.direction, ("●", "neutral"))

    if c.ability_slot and show_ability:
        slot_str = SLOT_COLORS.get(c.ability_slot, "general")
        tag_cls = f"tag-{slot_str}"
        bg_cls = f"bg-{slot_str}"
        tag_text = _e(c.ability_name or f"ABILITY {c.ability_slot}")
        if len(tag_text) > 18:
            tag_text = tag_text[:16] + "."
        if hero_name and c.ability_name:
            wiki_url = _ability_wiki_url(hero_name, c.ability_slot, c.ability_name)
            tag_html = (
                f'<a href="{wiki_url}" target="_blank" rel="noopener" '
                f'class="ability-tag {tag_cls}" data-wiki-url="{wiki_url}" '
                f'data-hero-name="{_e(hero_name)}" data-ability-slot="{c.ability_slot}" '
                f'data-ability-name="{_e(c.ability_name or "")}" '
                f'onclick="event.stopPropagation()">{tag_text}</a>'
            )
        else:
            tag_html = f'<span class="ability-tag {tag_cls}">{tag_text}</span>'
    else:
        tag_cls = "tag-general"
        bg_cls = "bg-general"
        tag_text = "BASE" if show_ability else "STAT"
        tag_html = f'<span class="ability-tag {tag_cls}">{tag_text}</span>'

    sb_tag = '<span class="street-brawl-tag">Street Brawl</span>' if c.street_brawl else ''
    date_attr = f' data-date="{_e(c.date)}"' if c.date else ''
    return (
        f'<div class="change-item {bg_cls}"{date_attr}>'
        f'<span class="change-direction {cls}">{sym}</span>'
        f'{tag_html}'
        f'{_e(c.text)}'
        f'{sb_tag}'
        f'</div>'
    )


# ── Rating badge ─────────────────────────────────────────────────

def _render_rating_badge(rating: LLMRating, small: bool = False) -> str:
    sm = " sm" if small else ""
    return (
        f'<div class="rating-badge rating-{rating.rating}{sm}">'
        f'<div class="stars"></div>'
        f'{_e(rating.label)}'
        f'</div>'
    )


# ── Sort changes ─────────────────────────────────────────────────

_DIRECTION_SORT = {ChangeDirection.BUFF: 0, ChangeDirection.NERF: 1, ChangeDirection.NEUTRAL: 2}

def _sort_changes(changes: list[Change]) -> list[Change]:
    def sort_key(c: Change):
        has_ability = 0 if c.ability_slot is None and not c.ability_name else 1
        slot = c.ability_slot or 0
        tier = c.tier or 0
        return (has_ability, slot, c.ability_name or "", tier)
    return sorted(changes, key=sort_key)


# ── Sidebar rendering ────────────────────────────────────────────

def _entity_dates(changes: list[Change]) -> str:
    """Comma-separated list of unique dates for an entity's changes."""
    dates = sorted({c.date for c in changes if c.date})
    return ",".join(dates)


def _render_sidebar_item(entity_id: str, name: str, rating: LLMRating | None,
                         entity_type: str, category: str = "", change_count: int = 0,
                         dates: str = "") -> str:
    r = rating or LLMRating.from_score(3, "")
    badge = _render_rating_badge(r, small=True)
    # Count buffs/nerfs for a quick visual indicator
    return (
        f'<div class="sidebar-item" data-entity-id="{entity_id}" '
        f'data-entity-type="{entity_type}" data-entity-name="{_e(name.lower())}" '
        f'data-category="{category}" data-dates="{dates}" '
        f'onclick="selectEntity(\'{entity_id}\')">'
        f'<div class="si-portrait" data-name="{_e(name)}"></div>'
        f'<div class="si-info">'
        f'<div class="si-name">{_e(name)}</div>'
        f'<div class="si-meta">{change_count} change{"s" if change_count != 1 else ""}</div>'
        f'</div>'
        f'{badge}'
        f'</div>'
    )


def _render_sidebar(data: ParsedPatchNotes) -> str:
    dates = _collect_dates(data)
    date_filter = _render_date_filter(dates)

    sections = []

    # System changes entry
    if data.system_changes:
        sys_dates = _entity_dates(data.system_changes)
        sys_item = (
            f'<div class="sidebar-item sidebar-item-system" data-entity-id="system" '
            f'data-entity-type="system" data-entity-name="system changes" '
            f'data-dates="{sys_dates}" onclick="selectEntity(\'system\')">'
            f'<div class="si-portrait si-portrait-system">⚙</div>'
            f'<div class="si-info">'
            f'<div class="si-name">System Changes</div>'
            f'<div class="si-meta">{len(data.system_changes)} changes</div>'
            f'</div>'
            f'</div>'
        )
        sections.append(f'<div class="sidebar-section" data-section="system">{sys_item}</div>')

    # Heroes
    if data.hero_changes:
        hero_items = []
        for g in sorted(data.hero_changes.values(), key=lambda g: g.hero.name.lower()):
            eid = f"hero-{_safe_id(g.hero.name)}"
            dates_str = _entity_dates(g.changes)
            hero_items.append(_render_sidebar_item(
                eid, g.hero.name, g.rating, "hero",
                change_count=len(g.changes), dates=dates_str,
            ))
        sections.append(
            f'<div class="sidebar-section" data-section="heroes">'
            f'<div class="sidebar-section-header">'
            f'<span class="ssh-label">Heroes</span>'
            f'<span class="ssh-count">{len(data.hero_changes)}</span>'
            f'</div>'
            f'{"".join(hero_items)}'
            f'</div>'
        )

    # Items by category
    item_groups: dict[ItemCategory, list[ItemChangeGroup]] = {}
    for group in data.item_changes.values():
        cat = group.item.category
        item_groups.setdefault(cat, []).append(group)

    for cat in [ItemCategory.WEAPON, ItemCategory.VITALITY, ItemCategory.SPIRIT, ItemCategory.UNKNOWN]:
        items = item_groups.get(cat, [])
        if not items:
            continue
        title, icon_cls, icon_char = CATEGORY_META[cat]
        item_rows = []
        for g in sorted(items, key=lambda g: g.item.name.lower()):
            eid = f"item-{_safe_id(g.item.name)}"
            dates_str = _entity_dates(g.changes)
            item_rows.append(_render_sidebar_item(
                eid, g.item.name, g.rating, "item", category=cat.value,
                change_count=len(g.changes), dates=dates_str,
            ))
        sections.append(
            f'<div class="sidebar-section" data-section="{cat.value}">'
            f'<div class="sidebar-section-header">'
            f'<div class="ssh-icon {icon_cls}">{icon_char}</div>'
            f'<span class="ssh-label">{title}</span>'
            f'<span class="ssh-count">{len(items)}</span>'
            f'</div>'
            f'{"".join(item_rows)}'
            f'</div>'
        )

    return (
        f'<aside class="sidebar">'
        f'<div class="sidebar-header">'
        f'<input type="text" class="sidebar-search" placeholder="Search heroes &amp; items..." '
        f'oninput="filterSidebar(this.value)">'
        f'{date_filter}'
        f'</div>'
        f'<div class="sidebar-list">{"".join(sections)}</div>'
        f'</aside>'
    )


# ── Detail panel rendering ────────────────────────────────────────

def _render_system_detail(changes: list[Change]) -> str:
    if not changes:
        return ""
    sorted_changes = sorted(changes, key=lambda c: _DIRECTION_SORT.get(c.direction, 2))
    lines = "\n".join(_render_change(c, show_ability=False) for c in sorted_changes)
    return (
        f'<div class="detail-section" id="detail-system" style="display:none">'
        f'<div class="detail-header">'
        f'<div class="detail-portrait-system">⚙</div>'
        f'<div class="detail-title-area">'
        f'<h2 class="detail-name">System Changes</h2>'
        f'<div class="detail-meta">{len(changes)} changes</div>'
        f'</div>'
        f'</div>'
        f'<div class="changes-list">{lines}</div>'
        f'</div>'
    )


def _render_hero_detail(group: HeroChangeGroup) -> str:
    eid = f"hero-{_safe_id(group.hero.name)}"
    rating = group.rating or LLMRating.from_score(3, "")
    badge = _render_rating_badge(rating)
    sorted_changes = _sort_changes(group.changes)
    changes_html = "\n".join(_render_change(c, hero_name=group.hero.name) for c in sorted_changes)
    explanation = ""
    if rating.explanation:
        explanation = (
            f'<div class="rating-explanation">'
            f'<strong>Rating: {rating.rating} — {_e(rating.label)}.</strong> '
            f'{_e(rating.explanation)}'
            f'</div>'
        )
    wiki = _wiki_url(group.hero.name)
    # Count buffs/nerfs
    buffs = sum(1 for c in group.changes if c.direction == ChangeDirection.BUFF)
    nerfs = sum(1 for c in group.changes if c.direction == ChangeDirection.NERF)
    neutral = len(group.changes) - buffs - nerfs
    stats_html = (
        f'<div class="detail-stats">'
        f'<span class="ds buff">▲ {buffs} buff{"s" if buffs != 1 else ""}</span>'
        f'<span class="ds nerf">▼ {nerfs} nerf{"s" if nerfs != 1 else ""}</span>'
        f'{"<span class=&quot;ds neutral&quot;>● " + str(neutral) + " other</span>" if neutral else ""}'
        f'</div>'
    )
    # Fix the neutral HTML with proper escaping
    stats_parts = [
        f'<span class="ds buff">▲ {buffs} buff{"s" if buffs != 1 else ""}</span>',
        f'<span class="ds nerf">▼ {nerfs} nerf{"s" if nerfs != 1 else ""}</span>',
    ]
    if neutral:
        stats_parts.append(f'<span class="ds neutral">● {neutral} other</span>')
    stats_html = f'<div class="detail-stats">{"".join(stats_parts)}</div>'

    return (
        f'<div class="detail-section" id="detail-{eid}" style="display:none">'
        f'<div class="detail-header">'
        f'<div class="detail-portrait" data-hero-name="{_e(group.hero.name)}"></div>'
        f'<div class="detail-title-area">'
        f'<h2 class="detail-name">{_e(group.hero.name)}</h2>'
        f'{stats_html}'
        f'</div>'
        f'<div class="detail-rating">{badge}</div>'
        f'</div>'
        f'{explanation}'
        f'<div class="changes-list">{changes_html}</div>'
        f'<a href="{wiki}" target="_blank" rel="noopener" class="wiki-link">View on Wiki ↗</a>'
        f'</div>'
    )


def _render_item_detail(group: ItemChangeGroup) -> str:
    eid = f"item-{_safe_id(group.item.name)}"
    rating = group.rating or LLMRating.from_score(3, "")
    badge = _render_rating_badge(rating)
    sorted_changes = _sort_changes(group.changes)
    changes_html = "\n".join(_render_change(c, show_ability=False) for c in sorted_changes)
    explanation = ""
    if rating.explanation:
        explanation = (
            f'<div class="rating-explanation">'
            f'<strong>Rating: {rating.rating} — {_e(rating.label)}.</strong> '
            f'{_e(rating.explanation)}'
            f'</div>'
        )
    wiki = _wiki_url(group.item.name)
    buffs = sum(1 for c in group.changes if c.direction == ChangeDirection.BUFF)
    nerfs = sum(1 for c in group.changes if c.direction == ChangeDirection.NERF)
    neutral = len(group.changes) - buffs - nerfs
    stats_parts = [
        f'<span class="ds buff">▲ {buffs} buff{"s" if buffs != 1 else ""}</span>',
        f'<span class="ds nerf">▼ {nerfs} nerf{"s" if nerfs != 1 else ""}</span>',
    ]
    if neutral:
        stats_parts.append(f'<span class="ds neutral">● {neutral} other</span>')
    stats_html = f'<div class="detail-stats">{"".join(stats_parts)}</div>'

    cat_title, cat_cls, cat_icon = CATEGORY_META.get(group.item.category, CATEGORY_META[ItemCategory.UNKNOWN])

    return (
        f'<div class="detail-section" id="detail-{eid}" style="display:none">'
        f'<div class="detail-header">'
        f'<div class="detail-portrait detail-portrait-item" data-item-name="{_e(group.item.name)}"></div>'
        f'<div class="detail-title-area">'
        f'<h2 class="detail-name">{_e(group.item.name)}</h2>'
        f'<div class="detail-category {cat_cls}">{cat_icon} {cat_title}</div>'
        f'{stats_html}'
        f'</div>'
        f'<div class="detail-rating">{badge}</div>'
        f'</div>'
        f'{explanation}'
        f'<div class="changes-list">{changes_html}</div>'
        f'<a href="{wiki}" target="_blank" rel="noopener" class="wiki-link">View on Wiki ↗</a>'
        f'</div>'
    )


def _render_all_details(data: ParsedPatchNotes) -> str:
    parts = []
    parts.append(_render_system_detail(data.system_changes))
    for g in sorted(data.hero_changes.values(), key=lambda g: g.hero.name.lower()):
        parts.append(_render_hero_detail(g))
    # Items by category then name
    for cat in [ItemCategory.WEAPON, ItemCategory.VITALITY, ItemCategory.SPIRIT, ItemCategory.UNKNOWN]:
        for g in sorted(data.item_changes.values(), key=lambda g: g.item.name.lower()):
            if g.item.category == cat:
                parts.append(_render_item_detail(g))
    return "\n".join(p for p in parts if p)


def _render_empty_state(data: ParsedPatchNotes) -> str:
    total_heroes = len(data.hero_changes)
    total_items = len(data.item_changes)
    total_system = len(data.system_changes)
    return (
        f'<div class="detail-empty" id="detail-empty">'
        f'<div class="empty-icon">📋</div>'
        f'<div class="empty-title">Select a hero or item</div>'
        f'<div class="empty-subtitle">Choose from the sidebar to view detailed changes</div>'
        f'<div class="empty-stats">'
        f'<span>{total_heroes} heroes</span>'
        f'<span>{total_items} items</span>'
        f'<span>{total_system} system changes</span>'
        f'</div>'
        f'</div>'
    )


# ── Date helpers ─────────────────────────────────────────────────

def _collect_dates(data: ParsedPatchNotes) -> list[str]:
    dates = set()
    for c in data.system_changes:
        if c.date:
            dates.add(c.date)
    for g in data.item_changes.values():
        for c in g.changes:
            if c.date:
                dates.add(c.date)
    for g in data.hero_changes.values():
        for c in g.changes:
            if c.date:
                dates.add(c.date)
    def date_sort_key(d: str) -> str:
        parts = d.split("-")
        if len(parts) == 3:
            return f"{parts[2]}{parts[0]}{parts[1]}"
        return d
    return sorted(dates, key=date_sort_key)


def _render_date_filter(dates: list[str]) -> str:
    if len(dates) <= 1:
        return ""
    options = ''.join(f'<option value="{d}">{d}</option>' for d in dates)
    return (
        f'<select class="sidebar-date-filter" id="dateFilter" onchange="filterByDate(this.value)">'
        f'<option value="all">All Dates ({len(dates)})</option>'
        f'{options}'
        f'</select>'
    )


# ── Full page ────────────────────────────────────────────────────

def render(data: ParsedPatchNotes) -> str:
    sidebar_html = _render_sidebar(data)
    details_html = _render_all_details(data)
    empty_html = _render_empty_state(data)
    title = _e(data.title) if data.title else "Deadlock Patch Notes"
    summary_html = f'<p class="patch-summary">{_e(data.summary)}</p>' if data.summary else ''

    return PAGE_TEMPLATE.format(
        page_title=title,
        patch_summary=summary_html,
        sidebar=sidebar_html,
        detail_panels=details_html,
        empty_state=empty_html,
    )


# ── Page template ────────────────────────────────────────────────

PAGE_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{page_title}</title>
<link rel="icon" href="/deadlock/deadlock_icon.ico" type="image/x-icon">
<link href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;500;600;700&family=Chakra+Petch:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg-deep: #0a0b0f; --bg-card: #12141c; --bg-card-hover: #181b26;
    --bg-ability: #1a1d28; --border: #252a38; --border-hover: #3a4158;
    --text-primary: #e8eaf0; --text-secondary: #8b90a5; --text-dim: #565b72;
    --accent-orange: #ff6b2c; --accent-orange-dim: #ff6b2c33;
    --ability-1: #3ecfff; --ability-2: #5dff7e; --ability-3: #d98fff;
    --ability-4: #ffcf3e; --ability-innate: #ff6b8a; --ability-general: #8b90a5;
    --ability-1-bg: #3ecfff12; --ability-2-bg: #5dff7e12; --ability-3-bg: #d98fff12;
    --ability-4-bg: #ffcf3e12; --ability-innate-bg: #ff6b8a12; --ability-general-bg: #8b90a512;
    --rating-1: #ff3b3b; --rating-2: #ff8c42; --rating-3: #a0a5b8;
    --rating-4: #5dff7e; --rating-5: #3ecfff;
    --star-filled: #ff6b2c; --star-empty: #2a2e3e;
    --sidebar-w: 360px;
  }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:var(--bg-deep); color:var(--text-primary); font-family:'Chakra Petch',sans-serif; height:100vh; overflow:hidden; line-height:1.6; }}
  body::before {{ content:''; position:fixed; inset:0; background:radial-gradient(ellipse at 20% 0%,#ff6b2c08 0%,transparent 50%),radial-gradient(ellipse at 80% 100%,#3ecfff06 0%,transparent 50%); pointer-events:none; z-index:0; }}

  /* ── App layout ── */
  .app-header {{
    padding:20px 28px 16px; border-bottom:1px solid var(--border); position:relative; z-index:2;
    display:flex; align-items:center; gap:20px; background:var(--bg-deep);
  }}
  .app-header .tag {{ display:inline-block; font-family:'JetBrains Mono',monospace; font-size:10px; letter-spacing:3px; text-transform:uppercase; color:var(--accent-orange); background:var(--accent-orange-dim); padding:4px 12px; border-radius:4px; white-space:nowrap; }}
  .app-header h1 {{ font-family:'Rajdhani',sans-serif; font-size:clamp(22px,3vw,32px); font-weight:700; letter-spacing:2px; text-transform:uppercase; line-height:1.1; background:linear-gradient(135deg,#e8eaf0 40%,var(--accent-orange) 100%); -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
  .app-header .legend {{ display:flex; gap:12px; align-items:center; flex-shrink:0; }}
  .app-header .legend-item {{ display:flex; align-items:center; gap:5px; font-size:11px; color:var(--text-dim); white-space:nowrap; }}
  .app-header .legend-dot {{ width:8px; height:8px; border-radius:50%; flex-shrink:0; }}
  .mobile-toggle {{ display:none; background:none; border:1px solid var(--border); color:var(--text-secondary); padding:8px; border-radius:6px; cursor:pointer; font-size:18px; }}

  .app-layout {{ display:flex; height:calc(100vh - 70px); position:relative; z-index:1; }}

  /* ── Sidebar ── */
  .sidebar {{ width:var(--sidebar-w); flex-shrink:0; border-right:1px solid var(--border); display:flex; flex-direction:column; background:var(--bg-deep); }}
  .sidebar-header {{ padding:12px 14px; border-bottom:1px solid var(--border); display:flex; flex-direction:column; gap:8px; flex-shrink:0; }}
  .sidebar-search {{ width:100%; font-family:'Chakra Petch',sans-serif; font-size:13px; color:var(--text-primary); background:var(--bg-card); border:1px solid var(--border); padding:10px 14px; border-radius:8px; outline:none; transition:border-color 0.2s; }}
  .sidebar-search:focus {{ border-color:var(--accent-orange); }}
  .sidebar-search::placeholder {{ color:var(--text-dim); }}
  .sidebar-date-filter {{ width:100%; font-family:'JetBrains Mono',monospace; font-size:12px; color:var(--accent-orange); background:var(--bg-card); border:1px solid #ff6b2c40; padding:8px 30px 8px 12px; border-radius:6px; cursor:pointer; appearance:none; -webkit-appearance:none; outline:none;
    background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%23ff6b2c' d='M6 8L1 3h10z'/%3E%3C/svg%3E"); background-repeat:no-repeat; background-position:right 10px center; }}
  .sidebar-date-filter option {{ background:var(--bg-card); color:var(--text-primary); }}

  .sidebar-list {{ flex:1; overflow-y:auto; padding:8px 0; }}
  .sidebar-list::-webkit-scrollbar {{ width:6px; }}
  .sidebar-list::-webkit-scrollbar-track {{ background:transparent; }}
  .sidebar-list::-webkit-scrollbar-thumb {{ background:var(--border); border-radius:3px; }}
  .sidebar-list::-webkit-scrollbar-thumb:hover {{ background:var(--border-hover); }}

  .sidebar-section {{ margin-bottom:4px; }}
  .sidebar-section-header {{ display:flex; align-items:center; gap:8px; padding:12px 16px 6px; }}
  .ssh-icon {{ width:22px; height:22px; border-radius:5px; display:flex; align-items:center; justify-content:center; font-size:12px; flex-shrink:0; }}
  .ssh-icon.weapon {{ background:#ff6b2c20; color:var(--accent-orange); border:1px solid #ff6b2c35; }}
  .ssh-icon.vitality {{ background:#5dff7e20; color:var(--ability-2); border:1px solid #5dff7e35; }}
  .ssh-icon.spirit {{ background:#d98fff20; color:var(--ability-3); border:1px solid #d98fff35; }}
  .ssh-label {{ font-family:'Rajdhani',sans-serif; font-size:14px; font-weight:700; letter-spacing:1px; text-transform:uppercase; color:var(--text-dim); }}
  .ssh-count {{ font-family:'JetBrains Mono',monospace; font-size:11px; color:var(--text-dim); background:var(--bg-card); padding:2px 7px; border-radius:4px; margin-left:auto; }}

  .sidebar-item {{ display:flex; align-items:center; gap:10px; padding:8px 16px; cursor:pointer; transition:all 0.15s; border-left:3px solid transparent; }}
  .sidebar-item:hover {{ background:var(--bg-card-hover); }}
  .sidebar-item.kb-focus {{ background:var(--bg-card-hover); outline:1px solid var(--border-hover); outline-offset:-1px; }}
  .sidebar-item.active {{ background:var(--bg-card); border-left-color:var(--accent-orange); }}
  .si-portrait {{ width:32px; height:32px; border-radius:6px; background:var(--bg-card); border:1px solid var(--border); flex-shrink:0; display:flex; align-items:center; justify-content:center; overflow:hidden; }}
  .si-portrait img {{ width:100%; height:100%; object-fit:cover; }}
  .si-portrait-system {{ font-size:16px; color:var(--text-dim); background:var(--bg-ability); }}
  .si-info {{ flex:1; min-width:0; }}
  .si-name {{ font-family:'Rajdhani',sans-serif; font-size:15px; font-weight:600; letter-spacing:0.5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
  .si-meta {{ font-family:'JetBrains Mono',monospace; font-size:10px; color:var(--text-dim); }}
  .sidebar-item .rating-badge {{ font-size:10px; padding:3px 8px; flex-shrink:0; }}
  .sidebar-item .rating-badge .stars {{ display:none; }}

  /* ── Detail panel ── */
  .detail-panel {{ flex:1; overflow-y:auto; padding:0; background:var(--bg-deep); }}
  .detail-panel::-webkit-scrollbar {{ width:8px; }}
  .detail-panel::-webkit-scrollbar-track {{ background:transparent; }}
  .detail-panel::-webkit-scrollbar-thumb {{ background:var(--border); border-radius:4px; }}
  .detail-panel::-webkit-scrollbar-thumb:hover {{ background:var(--border-hover); }}

  .detail-section {{ padding:28px 32px; }}
  .detail-section.entering {{ animation:detailIn 0.25s ease both; }}
  @keyframes detailIn {{ from {{ opacity:0; transform:translateY(12px); }} to {{ opacity:1; transform:translateY(0); }} }}
  .detail-section.exiting {{ animation:detailOut 0.15s ease both; }}
  @keyframes detailOut {{ from {{ opacity:1; transform:translateY(0); }} to {{ opacity:0; transform:translateY(-8px); }} }}

  .detail-header {{ display:flex; align-items:center; gap:20px; margin-bottom:24px; padding-bottom:20px; border-bottom:1px solid var(--border); }}
  .detail-portrait {{ width:72px; height:72px; border-radius:12px; background:var(--bg-card); border:1px solid var(--border); flex-shrink:0; display:flex; align-items:center; justify-content:center; overflow:hidden; }}
  .detail-portrait img {{ width:100%; height:100%; object-fit:cover; }}
  .detail-portrait-system {{ width:56px; height:56px; border-radius:12px; background:var(--bg-ability); border:1px solid var(--border); flex-shrink:0; display:flex; align-items:center; justify-content:center; font-size:28px; color:var(--text-dim); }}
  .detail-portrait-item {{ width:56px; height:56px; border-radius:10px; }}
  .detail-portrait-item img {{ object-fit:contain; padding:4px; }}
  .detail-title-area {{ flex:1; min-width:0; }}
  .detail-name {{ font-family:'Rajdhani',sans-serif; font-size:clamp(28px,4vw,40px); font-weight:700; letter-spacing:2px; text-transform:uppercase; line-height:1.1; }}
  .detail-category {{ font-family:'JetBrains Mono',monospace; font-size:12px; letter-spacing:0.5px; margin-top:4px; }}
  .detail-category.weapon {{ color:var(--accent-orange); }}
  .detail-category.vitality {{ color:var(--ability-2); }}
  .detail-category.spirit {{ color:var(--ability-3); }}
  .detail-stats {{ display:flex; gap:12px; margin-top:6px; }}
  .ds {{ font-family:'JetBrains Mono',monospace; font-size:12px; }}
  .ds.buff {{ color:var(--ability-2); }} .ds.nerf {{ color:#ff5c5c; }} .ds.neutral {{ color:var(--text-dim); }}
  .detail-rating {{ flex-shrink:0; }}
  .detail-meta {{ font-family:'JetBrains Mono',monospace; font-size:12px; color:var(--text-dim); margin-top:4px; }}

  /* ── Changes list (shared) ── */
  .changes-list {{ display:flex; flex-direction:column; gap:6px; margin-bottom:20px; }}
  .change-item {{ display:flex; align-items:flex-start; gap:10px; padding:8px 12px; border-radius:6px; font-size:14px; line-height:1.5; }}
  .change-item .ability-tag {{ font-family:'JetBrains Mono',monospace; font-size:11px; font-weight:500; padding:2px 8px; border-radius:4px; white-space:nowrap; flex-shrink:0; margin-top:2px; letter-spacing:0.5px; text-decoration:none; }}
  a.ability-tag:hover {{ filter:brightness(1.3); }}
  .tag-1 {{ color:var(--ability-1); background:var(--ability-1-bg); border:1px solid #3ecfff25; }}
  .tag-2 {{ color:var(--ability-2); background:var(--ability-2-bg); border:1px solid #5dff7e25; }}
  .tag-3 {{ color:var(--ability-3); background:var(--ability-3-bg); border:1px solid #d98fff25; }}
  .tag-4 {{ color:var(--ability-4); background:var(--ability-4-bg); border:1px solid #ffcf3e25; }}
  .tag-innate {{ color:var(--ability-innate); background:var(--ability-innate-bg); border:1px solid #ff6b8a25; }}
  .tag-general {{ color:var(--ability-general); background:var(--ability-general-bg); border:1px solid #8b90a525; }}
  .bg-1 {{ background:var(--ability-1-bg); }} .bg-2 {{ background:var(--ability-2-bg); }}
  .bg-3 {{ background:var(--ability-3-bg); }} .bg-4 {{ background:var(--ability-4-bg); }}
  .bg-innate {{ background:var(--ability-innate-bg); }} .bg-general {{ background:var(--ability-general-bg); }}
  .change-direction {{ font-size:14px; flex-shrink:0; margin-top:1px; width:16px; text-align:center; }}
  .buff {{ color:#5dff7e; }} .nerf {{ color:#ff5c5c; }} .neutral {{ color:#a0a5b8; }}
  .street-brawl-tag {{ font-family:'JetBrains Mono',monospace; font-size:10px; font-weight:600; padding:2px 6px; border-radius:3px; color:#ffb347; background:#ffb34715; border:1px solid #ffb34730; white-space:nowrap; flex-shrink:0; margin-top:2px; letter-spacing:0.5px; text-transform:uppercase; }}

  /* ── Rating ── */
  .rating-badge {{ display:flex; align-items:center; gap:8px; padding:6px 14px; border-radius:6px; font-family:'JetBrains Mono',monospace; font-size:12px; font-weight:600; letter-spacing:1px; text-transform:uppercase; white-space:nowrap; }}
  .rating-badge.sm {{ font-size:11px; padding:4px 10px; }}
  .rating-badge.sm .stars {{ gap:2px; }} .rating-badge.sm .star {{ width:11px; height:11px; }}
  .rating-1 {{ background:#ff3b3b18; color:var(--rating-1); border:1px solid #ff3b3b30; }}
  .rating-2 {{ background:#ff8c4218; color:var(--rating-2); border:1px solid #ff8c4230; }}
  .rating-3 {{ background:#a0a5b818; color:var(--rating-3); border:1px solid #a0a5b830; }}
  .rating-4 {{ background:#5dff7e18; color:var(--rating-4); border:1px solid #5dff7e30; }}
  .rating-5 {{ background:#3ecfff18; color:var(--rating-5); border:1px solid #3ecfff30; }}
  .stars {{ display:flex; gap:3px; }} .star {{ width:14px; height:14px; display:inline-block; }} .star svg {{ width:100%; height:100%; }}
  .rating-explanation {{ padding:16px 18px; background:#ffffff06; border-left:3px solid var(--accent-orange); border-radius:0 8px 8px 0; font-size:14px; color:var(--text-secondary); line-height:1.65; margin-bottom:20px; }}
  .rating-explanation strong {{ color:var(--text-primary); font-weight:600; }}

  .wiki-link {{ display:inline-block; margin-top:12px; font-family:'JetBrains Mono',monospace; font-size:11px; letter-spacing:0.5px; color:var(--text-dim); background:#ffffff08; border:1px solid var(--border); padding:5px 12px; border-radius:5px; text-decoration:none; transition:all 0.2s; }}
  .wiki-link:hover {{ color:var(--accent-orange); border-color:var(--accent-orange); background:var(--accent-orange-dim); }}

  .ability-icon {{ width:18px; height:18px; border-radius:4px; object-fit:contain; vertical-align:middle; margin-right:2px; opacity:0; transition:opacity 0.3s; flex-shrink:0; margin-top:1px; }}
  .ability-icon.loaded {{ opacity:1; }}

  /* ── Empty state ── */
  .detail-empty {{ display:flex; flex-direction:column; align-items:center; justify-content:center; height:100%; color:var(--text-dim); text-align:center; padding:40px; }}
  .empty-icon {{ font-size:48px; margin-bottom:16px; opacity:0.5; }}
  .empty-title {{ font-family:'Rajdhani',sans-serif; font-size:24px; font-weight:700; color:var(--text-secondary); letter-spacing:1px; }}
  .empty-subtitle {{ font-size:14px; margin-top:6px; }}
  .empty-stats {{ display:flex; gap:20px; margin-top:24px; font-family:'JetBrains Mono',monospace; font-size:12px; color:var(--text-dim); }}
  .empty-stats span {{ background:var(--bg-card); padding:6px 14px; border-radius:6px; border:1px solid var(--border); }}

  /* ── Ability popup ── */
  .ability-popup {{ position:fixed; z-index:9999; width:min(380px, calc(100vw - 32px)); border:1px solid #583D6F; border-radius:12px; overflow:hidden; box-shadow:0 8px 32px rgba(0,0,0,0.7); pointer-events:none; opacity:0; transition:opacity 0.2s; background:#121013; font-family:'Chakra Petch',sans-serif; color:#FFEFD7; }}
  .ability-popup.visible {{ opacity:1; pointer-events:auto; }}
  .ability-popup-header {{ display:flex; align-items:center; gap:12px; padding:16px 18px 12px; background:linear-gradient(135deg,#1a1520,#25193a); }}
  .ability-popup-icon {{ width:42px; height:42px; border-radius:6px; object-fit:contain; }}
  .ability-popup-title {{ font-family:'Rajdhani',sans-serif; font-size:22px; font-weight:700; letter-spacing:1px; text-transform:uppercase; }}
  .ability-popup-slot {{ font-family:'JetBrains Mono',monospace; font-size:11px; color:#bc8ee8; margin-top:2px; }}
  .ability-popup-stats {{ display:flex; flex-wrap:wrap; gap:8px; padding:8px 18px; }}
  .ability-popup-stat {{ display:flex; align-items:center; gap:5px; background:#2C2C2C; padding:5px 10px; border-radius:4px; font-size:13px; }}
  .ability-popup-stat img {{ width:16px; height:16px; opacity:0.7; }}
  .ability-popup-stat .stat-val {{ font-weight:700; }}
  .ability-popup-stat .stat-unit {{ font-size:11px; color:#B2B2B2; }}
  .ability-popup-desc {{ padding:10px 18px 14px; font-size:13px; line-height:1.5; color:#ccc; border-top:1px solid #2a2a2a; }}
  .ability-popup-props {{ display:flex; flex-wrap:wrap; gap:6px; padding:0 18px 12px; }}
  .ability-popup-prop {{ display:flex; flex-direction:column; align-items:center; text-align:center; background:radial-gradient(circle,#2a292b,#3b3145); border:2px solid #583D6F; border-radius:4px; padding:8px 12px 6px; min-width:80px; flex:1; position:relative; }}
  .ability-popup-prop .prop-val {{ font-weight:700; font-size:15px; }}
  .ability-popup-prop .prop-unit {{ font-size:11px; color:#B2B2B2; }}
  .ability-popup-prop .prop-label {{ font-size:11px; color:#9C9C9C; margin-top:2px; }}
  .ability-popup-prop .prop-scale {{ position:absolute; top:-8px; right:-4px; font-size:10px; color:#E3BDFA; background:#533669; padding:1px 5px; border-radius:4px; font-weight:700; font-style:italic; }}
  .ability-popup-upgrades {{ display:flex; gap:6px; padding:0 18px 14px; }}
  .ability-popup-upgrade {{ flex:1; background:#131211; border-radius:6px; overflow:hidden; text-align:center; border:1px solid #2a2a2a; }}
  .ability-popup-upgrade-hdr {{ background:#402f4c; padding:3px 0; font-family:'JetBrains Mono',monospace; font-size:12px; font-weight:700; color:#bc8ee8; }}
  .ability-popup-upgrade-body {{ padding:8px 6px; font-size:12px; line-height:1.4; color:#ccc; }}

  /* ── GitHub link ── */
  .github-link {{ position:fixed; top:16px; right:16px; z-index:100; display:flex; align-items:center; gap:8px; font-family:'JetBrains Mono',monospace; font-size:12px; color:var(--text-dim); background:var(--bg-card); border:1px solid var(--border); padding:8px 14px; border-radius:8px; text-decoration:none; transition:all 0.2s; }}
  .github-link:hover {{ color:var(--text-primary); border-color:var(--border-hover); background:var(--bg-card-hover); }}
  .github-link svg {{ width:18px; height:18px; fill:currentColor; }}

  /* ── Mobile ── */
  @media (max-width:768px) {{
    .app-header {{ padding:14px 16px 12px; gap:12px; }}
    .app-header .legend {{ display:none; }}
    .mobile-toggle {{ display:block; }}
    .app-layout {{ flex-direction:column; height:calc(100vh - 56px); }}
    .sidebar {{ position:fixed; left:0; top:56px; bottom:0; width:85vw; max-width:360px; z-index:50; transform:translateX(-100%); transition:transform 0.3s ease; box-shadow:4px 0 24px rgba(0,0,0,0.5); }}
    .sidebar.open {{ transform:translateX(0); }}
    .sidebar-overlay {{ display:none; position:fixed; inset:0; top:56px; background:rgba(0,0,0,0.5); z-index:49; }}
    .sidebar-overlay.open {{ display:block; }}
    .detail-panel {{ width:100%; }}
    .detail-section {{ padding:20px 16px; }}
    .detail-header {{ flex-wrap:wrap; gap:12px; }}
    .detail-name {{ font-size:24px; }}
    .detail-portrait {{ width:56px; height:56px; }}
    .change-item {{ font-size:13px; }}
    .github-link span {{ display:none; }} .github-link {{ padding:8px; }}
    .ability-popup-prop {{ min-width:70px; padding:6px 8px 4px; }}
  }}
</style>
</head>
<body>

<a href="https://github.com/jjbokan3/deadlock-hub" target="_blank" rel="noopener" class="github-link"><svg viewBox="0 0 16 16"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/></svg><span>GitHub</span></a>

<div class="app-header">
  <button class="mobile-toggle" onclick="toggleSidebar()" aria-label="Menu">☰</button>
  <div class="tag">Patch Notes</div>
  <h1>{page_title}</h1>
  <div class="legend">
    <div class="legend-item"><div class="legend-dot" style="background:var(--ability-general)"></div> Base</div>
    <div class="legend-item"><div class="legend-dot" style="background:var(--ability-1)"></div> 1</div>
    <div class="legend-item"><div class="legend-dot" style="background:var(--ability-2)"></div> 2</div>
    <div class="legend-item"><div class="legend-dot" style="background:var(--ability-3)"></div> 3</div>
    <div class="legend-item"><div class="legend-dot" style="background:var(--ability-4)"></div> 4/Ult</div>
    <div class="legend-item"><div class="legend-dot" style="background:var(--rating-1)"></div> Nerf</div>
    <div class="legend-item"><div class="legend-dot" style="background:var(--rating-5)"></div> Buff</div>
  </div>
</div>

<div class="sidebar-overlay" onclick="toggleSidebar()"></div>

<div class="app-layout">
  {sidebar}
  <main class="detail-panel">
    {empty_state}
    {detail_panels}
  </main>
</div>

<script>
  /* ── Sidebar toggle (mobile) ── */
  function toggleSidebar() {{
    document.querySelector('.sidebar').classList.toggle('open');
    document.querySelector('.sidebar-overlay').classList.toggle('open');
  }}

  /* ── Entity selection with crossfade ── */
  let currentEntity = null;
  function selectEntity(id, skipAnimation) {{
    if (currentEntity === id) return;

    // Deselect sidebar
    document.querySelectorAll('.sidebar-item.active').forEach(el => el.classList.remove('active'));
    const emptyEl = document.getElementById('detail-empty');

    // Animate out current detail
    const oldDetail = currentEntity ? document.getElementById('detail-' + currentEntity) : emptyEl;
    const newDetail = document.getElementById('detail-' + id);
    if (!newDetail) return;

    function showNew() {{
      document.querySelectorAll('.detail-section').forEach(el => {{
        el.style.display = 'none';
        el.classList.remove('entering', 'exiting');
      }});
      if (emptyEl) emptyEl.style.display = 'none';
      newDetail.style.display = '';
      newDetail.classList.remove('exiting');
      newDetail.classList.add('entering');
      newDetail.addEventListener('animationend', function handler() {{
        newDetail.classList.remove('entering');
        newDetail.removeEventListener('animationend', handler);
      }});
    }}

    if (oldDetail && oldDetail !== newDetail && !skipAnimation) {{
      oldDetail.classList.add('exiting');
      oldDetail.addEventListener('animationend', function handler() {{
        oldDetail.classList.remove('exiting');
        oldDetail.style.display = 'none';
        oldDetail.removeEventListener('animationend', handler);
        showNew();
      }});
    }} else {{
      showNew();
    }}

    // Select sidebar item
    const item = document.querySelector(`.sidebar-item[data-entity-id="${{id}}"]`);
    if (item) item.classList.add('active');
    currentEntity = id;

    // Mobile: close sidebar
    document.querySelector('.sidebar').classList.remove('open');
    document.querySelector('.sidebar-overlay').classList.remove('open');

    // Scroll detail to top
    document.querySelector('.detail-panel').scrollTop = 0;

    // Update URL hash
    history.replaceState(null, '', '#' + id);

    // Update detail counts for active date filter
    updateDetailCounts();
  }}

  /* ── Search filter ── */
  function filterSidebar(query) {{
    const q = query.toLowerCase().trim();
    document.querySelectorAll('.sidebar-item').forEach(item => {{
      const name = item.dataset.entityName || '';
      const dateHidden = item.classList.contains('date-hidden');
      item.style.display = (!dateHidden && (!q || name.includes(q))) ? '' : 'none';
    }});
    updateSectionCounts();
  }}

  /* ── Date filter ── */
  let activeDate = 'all';
  function filterByDate(date) {{
    activeDate = date;
    const showAll = date === 'all';
    // Filter change items in ALL detail panels
    document.querySelectorAll('.change-item').forEach(el => {{
      const d = el.dataset.date;
      el.style.display = (showAll || !d || d === date) ? '' : 'none';
    }});
    // Mark sidebar items by date
    document.querySelectorAll('.sidebar-item').forEach(item => {{
      if (showAll) {{
        item.classList.remove('date-hidden');
      }} else {{
        const dates = (item.dataset.dates || '').split(',');
        if (dates.includes(date)) {{
          item.classList.remove('date-hidden');
        }} else {{
          item.classList.add('date-hidden');
        }}
      }}
    }});
    // Re-apply search filter (handles visibility + section counts)
    const q = document.querySelector('.sidebar-search');
    filterSidebar(q ? q.value : '');
    // Update detail panel counts
    updateDetailCounts();
  }}

  /* ── Update section counts in sidebar ── */
  function updateSectionCounts() {{
    document.querySelectorAll('.sidebar-section').forEach(sec => {{
      const items = sec.querySelectorAll('.sidebar-item');
      const visible = [...items].filter(i => i.style.display !== 'none');
      const anyVisible = visible.length > 0;
      sec.style.display = anyVisible ? '' : 'none';
      const countEl = sec.querySelector('.ssh-count');
      if (countEl) {{
        const total = items.length;
        countEl.textContent = anyVisible && visible.length < total
          ? `${{visible.length}} / ${{total}}`
          : `${{total}}`;
      }}
    }});
  }}

  /* ── Update detail panel buff/nerf counts for active date ── */
  function updateDetailCounts() {{
    document.querySelectorAll('.detail-section').forEach(section => {{
      const statsEl = section.querySelector('.detail-stats');
      if (!statsEl) return;
      const changes = section.querySelectorAll('.change-item');
      let buffs = 0, nerfs = 0, neutral = 0;
      changes.forEach(c => {{
        if (c.style.display === 'none') return;
        const dir = c.querySelector('.change-direction');
        if (!dir) return;
        if (dir.classList.contains('buff')) buffs++;
        else if (dir.classList.contains('nerf')) nerfs++;
        else neutral++;
      }});
      let html = `<span class="ds buff">▲ ${{buffs}} buff${{buffs !== 1 ? 's' : ''}}</span>`;
      html += `<span class="ds nerf">▼ ${{nerfs}} nerf${{nerfs !== 1 ? 's' : ''}}</span>`;
      if (neutral) html += `<span class="ds neutral">● ${{neutral}} other</span>`;
      statsEl.innerHTML = html;
    }});
    // Also update system detail meta
    const sysMeta = document.querySelector('#detail-system .detail-meta');
    if (sysMeta) {{
      const visible = document.querySelectorAll('#detail-system .change-item:not([style*="display: none"])').length;
      const total = document.querySelectorAll('#detail-system .change-item').length;
      sysMeta.textContent = activeDate === 'all'
        ? `${{total}} changes`
        : `${{visible}} / ${{total}} changes`;
    }}
  }}

  /* ── Stars ── */
  function renderStars() {{
    document.querySelectorAll('.stars').forEach(el => {{
      const b = el.closest('.rating-badge'); let n = 3;
      if (b.classList.contains('rating-1')) n = 1;
      else if (b.classList.contains('rating-2')) n = 2;
      else if (b.classList.contains('rating-3')) n = 3;
      else if (b.classList.contains('rating-4')) n = 4;
      else if (b.classList.contains('rating-5')) n = 5;
      let h = '';
      for (let i = 0; i < 5; i++) {{
        const f = i < n;
        h += `<span class="star"><svg viewBox="0 0 20 20" fill="${{f ? 'var(--star-filled)' : 'var(--star-empty)'}}"><path d="M10 1.5l2.47 5.01 5.53.8-4 3.9.94 5.49L10 14.26 5.06 16.7 6 11.21l-4-3.9 5.53-.8z"/></svg></span>`;
      }}
      el.innerHTML = h;
    }});
  }}
  renderStars();

  /* ── Runtime image injection ── */
  const HEROES_URL = 'https://assets.deadlock-api.com/v2/heroes';
  const ITEMS_URL = 'https://assets.deadlock-api.com/v2/items';
  const HERO_ALIASES = {{'Doorman': 'The Doorman'}};
  const abilityDataStore = {{}};

  function createImg(src, cls) {{
    const img = document.createElement('img');
    img.src = src; img.className = cls; img.loading = 'lazy';
    img.onload = () => img.classList.add('loaded');
    img.onerror = () => img.style.display = 'none';
    return img;
  }}

  async function loadImages() {{
    let heroes, items;
    try {{
      const [hr, ir] = await Promise.all([fetch(HEROES_URL), fetch(ITEMS_URL)]);
      heroes = await hr.json(); items = await ir.json();
    }} catch (e) {{ return; }}

    const hm = {{}};
    heroes.forEach(h => {{ if (h.name) hm[h.name.toLowerCase()] = h; }});
    const im = {{}};
    const ic = {{}};
    items.forEach(i => {{ if (i.name) im[i.name.toLowerCase()] = i; if (i.class_name) ic[i.class_name.toLowerCase()] = i; }});

    // Build ability data store
    heroes.forEach(h => {{
      if (!h.name || !h.items) return;
      ['signature1','signature2','signature3','signature4'].forEach((k, i) => {{
        const cn = h.items[k];
        if (!cn) return;
        const item = ic[cn.toLowerCase()];
        if (item) abilityDataStore[h.name.toLowerCase() + '_' + (i+1)] = {{...item, slot: i+1, heroName: h.name}};
      }});
    }});

    // Sidebar hero portraits
    document.querySelectorAll('.sidebar-item[data-entity-type="hero"] .si-portrait').forEach(el => {{
      const name = el.dataset.name;
      if (!name) return;
      const an = HERO_ALIASES[name] || name;
      const h = hm[an.toLowerCase()];
      if (!h || !h.images) return;
      const url = h.images.icon_hero_card || h.images.icon_image_small;
      if (url) el.appendChild(createImg(url, 'loaded'));
    }});

    // Sidebar item icons
    document.querySelectorAll('.sidebar-item[data-entity-type="item"] .si-portrait').forEach(el => {{
      const name = el.dataset.name;
      if (!name) return;
      const i = im[name.toLowerCase()];
      if (i && i.image) el.appendChild(createImg(i.image, 'loaded'));
    }});

    // Detail panel hero portraits
    document.querySelectorAll('.detail-portrait[data-hero-name]').forEach(el => {{
      const name = el.dataset.heroName;
      const an = HERO_ALIASES[name] || name;
      const h = hm[an.toLowerCase()];
      if (!h || !h.images) return;
      const url = h.images.icon_hero_card || h.images.icon_image_small;
      if (url) el.appendChild(createImg(url, 'loaded'));
    }});

    // Detail panel item icons
    document.querySelectorAll('.detail-portrait-item[data-item-name]').forEach(el => {{
      const name = el.dataset.itemName;
      const i = im[name.toLowerCase()];
      if (i && i.image) el.appendChild(createImg(i.image, 'loaded'));
    }});

    // Ability icons in change lists
    document.querySelectorAll('.detail-section').forEach(section => {{
      const heroNameEl = section.querySelector('.detail-name');
      if (!heroNameEl) return;
      const heroName = heroNameEl.textContent.trim();
      const an = HERO_ALIASES[heroName] || heroName;
      const h = hm[an.toLowerCase()];
      if (!h || !h.items) return;
      const sigs = ['signature1','signature2','signature3','signature4'];
      const am = {{}};
      sigs.forEach((k, i) => {{ if (h.items[k]) am[i+1] = h.items[k].toLowerCase(); }});
      section.querySelectorAll('.ability-tag').forEach(tag => {{
        let s = null;
        if (tag.classList.contains('tag-1')) s = 1;
        else if (tag.classList.contains('tag-2')) s = 2;
        else if (tag.classList.contains('tag-3')) s = 3;
        else if (tag.classList.contains('tag-4')) s = 4;
        if (s && am[s]) {{
          const ai = ic[am[s]];
          if (ai && ai.image) {{
            if (tag.previousElementSibling && tag.previousElementSibling.classList.contains('ability-icon')) return;
            tag.parentNode.insertBefore(createImg(ai.image, 'ability-icon'), tag);
          }}
        }}
      }});
    }});
  }}
  loadImages();

  /* ── Ability popup on hover ── */
  (function() {{
    const popup = document.createElement('div');
    popup.className = 'ability-popup';
    document.body.appendChild(popup);
    let hoverTimer = null;
    let currentKey = '';

    function buildPopup(data) {{
      const props = data.properties || {{}};
      const rawDesc = data.description || {{}};
      const upgrades = data.upgrades || [];
      const slotLabels = {{1:'Ability 1', 2:'Ability 2', 3:'Ability 3', 4:'Ultimate'}};

      let html = '<div class="ability-popup-header">';
      if (data.image) html += `<img class="ability-popup-icon" src="${{data.image}}" alt="">`;
      html += `<div><div class="ability-popup-title">${{data.name||''}}</div>`;
      html += `<div class="ability-popup-slot">${{slotLabels[data.slot]||'Ability'}}</div></div></div>`;

      const headerStats = ['AbilityCooldown','AbilityDuration','AbilityCastRange','AbilityChannelTime'];
      let statsHtml = '';
      for (const key of headerStats) {{
        const p = props[key];
        if (!p || typeof p !== 'object') continue;
        const val = p.value;
        if (val === undefined || val === null || val === '' || val === '0' || val === 0) continue;
        const icon = p.icon ? `<img src="${{p.icon}}" alt="">` : '';
        const postfix = p.postfix || '';
        statsHtml += `<div class="ability-popup-stat">${{icon}}<span class="stat-val">${{val}}</span><span class="stat-unit">${{postfix}}</span></div>`;
      }}
      if (statsHtml) html += `<div class="ability-popup-stats">${{statsHtml}}</div>`;

      const descText = typeof rawDesc === 'object' ? (rawDesc.desc || '') : String(rawDesc);
      if (descText) {{
        const cleanDesc = descText.replace(/<svg[\\s\\S]*?<\\/svg>/gi, '🔮').replace(/<[^>]*>/g, '').replace(/\\n/g, ' ').trim();
        if (cleanDesc) html += `<div class="ability-popup-desc">${{cleanDesc}}</div>`;
      }}

      const skipKeys = new Set([...headerStats,
        'AbilityCastDelay','AbilityUnitTargetLimit','AbilityUnitTargetType','AbilityCastAnimation',
        'TickRate','AbilityCooldownBetweenCharge','ChannelMoveSpeed',
        'DashSpeed','DashRange','DashRadius','SideMoveSpeed','TurnRateMax',
        'CounterattackAntiMashDelay','SlashConeAngle','SlashRadius','SlashHalfWidth',
        'DampingFactor','LiftHeight','DamageThreshold','ParryWindow',
        'AbilityResourceCost','AbilityCharges','AbilityMaxCharges',
        'ProjectileSpeed','BulletSpeed','TravelSpeed',
        'MaxJumpHeight','MinJumpHeight','LaunchAngle','VerticalLaunchSpeed',
      ]);
      let propBoxes = '';
      for (const [k, v] of Object.entries(props)) {{
        if (skipKeys.has(k)) continue;
        if (!v || typeof v !== 'object') continue;
        const val = v.value;
        if (val === undefined || val === null || val === '' || val === '0' || val === 0) continue;
        if (!v.label || !v.icon) continue;
        if (typeof val === 'number' && val < 0) continue;
        const postfix = v.postfix || '';
        const sf = v.scale_function;
        const hasScale = sf && sf.specific_stat_scale_type === 'ETechPower';
        const scaleVal = hasScale && sf.stat_scale ? sf.stat_scale : null;
        propBoxes += `<div class="ability-popup-prop">`;
        if (scaleVal) propBoxes += `<span class="prop-scale">x${{scaleVal}}</span>`;
        else if (hasScale) propBoxes += `<span class="prop-scale">✦</span>`;
        propBoxes += `<span class="prop-val">${{val}}<span class="prop-unit">${{postfix}}</span></span>`;
        propBoxes += `<span class="prop-label">${{v.label}}</span></div>`;
      }}
      if (propBoxes) html += `<div class="ability-popup-props">${{propBoxes}}</div>`;

      let upgradeHtml = '';
      const apCosts = [1, 2, 5];
      for (let i = 0; i < Math.min(upgrades.length, 3); i++) {{
        const u = upgrades[i];
        if (!u || !u.property_upgrades || !u.property_upgrades.length) continue;
        let parts = [];
        for (const pu of u.property_upgrades) {{
          const propDef = props[pu.name];
          const label = propDef && propDef.label ? propDef.label : pu.name.replace(/([A-Z])/g, ' $1').trim();
          const postfix = propDef && propDef.postfix ? propDef.postfix : '';
          const bonus = pu.bonus;
          const isScale = pu.upgrade_type === 'EAddToScale';
          if (isScale) {{ parts.push(`+${{bonus}} Spirit Scaling`); }}
          else {{ const sign = typeof bonus === 'number' && bonus > 0 ? '+' : ''; parts.push(`${{sign}}${{bonus}}${{postfix}} ${{label}}`); }}
        }}
        upgradeHtml += `<div class="ability-popup-upgrade"><div class="ability-popup-upgrade-hdr">◆ ${{apCosts[i]}}</div><div class="ability-popup-upgrade-body">${{parts.join('<br>')}}</div></div>`;
      }}
      if (upgradeHtml) html += `<div class="ability-popup-upgrades">${{upgradeHtml}}</div>`;

      return html;
    }}

    function show(tag) {{
      const heroName = tag.dataset.heroName;
      const slot = tag.dataset.abilitySlot;
      if (!heroName || !slot) return;
      const key = heroName.toLowerCase() + '_' + slot;
      if (currentKey === key && popup.classList.contains('visible')) return;
      const data = abilityDataStore[key];
      if (!data) return;
      currentKey = key;
      popup.innerHTML = buildPopup(data);
      const rect = tag.getBoundingClientRect();
      let left = rect.right + 12;
      let top = rect.top - 60;
      const pw = 380;
      if (left + pw > window.innerWidth) left = rect.left - pw - 12;
      if (left < 8) left = 8;
      const ph = popup.offsetHeight || 350;
      if (top + ph > window.innerHeight) top = window.innerHeight - ph - 8;
      if (top < 8) top = 8;
      popup.style.left = left + 'px';
      popup.style.top = top + 'px';
      popup.classList.add('visible');
    }}

    function hide() {{
      clearTimeout(hoverTimer); hoverTimer = null;
      popup.classList.remove('visible'); currentKey = '';
    }}

    const isTouch = 'ontouchstart' in window;
    if (isTouch) {{
      document.addEventListener('click', function(e) {{
        const tag = e.target.closest('a.ability-tag[data-hero-name]');
        if (tag) {{
          e.preventDefault(); e.stopPropagation();
          if (currentKey === tag.dataset.heroName.toLowerCase() + '_' + tag.dataset.abilitySlot && popup.classList.contains('visible')) hide();
          else show(tag);
          return;
        }}
        if (!popup.contains(e.target)) hide();
      }});
    }} else {{
      document.addEventListener('mouseover', function(e) {{
        const tag = e.target.closest('a.ability-tag[data-hero-name]');
        if (!tag) return;
        clearTimeout(hoverTimer);
        hoverTimer = setTimeout(() => show(tag), 800);
      }});
      document.addEventListener('mouseout', function(e) {{
        const tag = e.target.closest('a.ability-tag[data-hero-name]');
        if (!tag) return;
        const related = e.relatedTarget;
        if (related && (popup.contains(related) || popup === related)) return;
        hide();
      }});
      popup.addEventListener('mouseenter', function() {{ clearTimeout(hoverTimer); }});
      popup.addEventListener('mouseleave', function() {{ hide(); }});
    }}
  }})();

  /* ── Keyboard navigation ── */
  (function() {{
    let kbIndex = -1;

    function getVisibleItems() {{
      return [...document.querySelectorAll('.sidebar-item')].filter(i => i.style.display !== 'none');
    }}

    function clearKbFocus() {{
      document.querySelectorAll('.sidebar-item.kb-focus').forEach(el => el.classList.remove('kb-focus'));
    }}

    function setKbFocus(idx, items) {{
      clearKbFocus();
      if (idx < 0 || idx >= items.length) return;
      kbIndex = idx;
      const item = items[idx];
      item.classList.add('kb-focus');
      // Scroll into view within sidebar
      item.scrollIntoView({{ block: 'nearest', behavior: 'smooth' }});
    }}

    document.addEventListener('keydown', function(e) {{
      // Skip if typing in search
      const isSearch = document.activeElement && document.activeElement.classList.contains('sidebar-search');

      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {{
        e.preventDefault();
        const items = getVisibleItems();
        if (!items.length) return;

        // Find current index
        if (kbIndex < 0) {{
          // Start from active item if exists
          const activeIdx = items.findIndex(i => i.classList.contains('active'));
          kbIndex = activeIdx >= 0 ? activeIdx : -1;
        }}

        if (e.key === 'ArrowDown') {{
          kbIndex = kbIndex < items.length - 1 ? kbIndex + 1 : 0;
        }} else {{
          kbIndex = kbIndex > 0 ? kbIndex - 1 : items.length - 1;
        }}
        setKbFocus(kbIndex, items);
      }}

      if (e.key === 'Enter' && !isSearch) {{
        const items = getVisibleItems();
        if (kbIndex >= 0 && kbIndex < items.length) {{
          selectEntity(items[kbIndex].dataset.entityId);
          clearKbFocus();
        }}
      }}

      // Escape: close mobile sidebar or clear search
      if (e.key === 'Escape') {{
        const sidebar = document.querySelector('.sidebar');
        if (sidebar.classList.contains('open')) {{
          toggleSidebar();
        }} else if (isSearch && document.activeElement.value) {{
          document.activeElement.value = '';
          filterSidebar('');
        }}
        clearKbFocus();
        kbIndex = -1;
      }}

      // / to focus search
      if (e.key === '/' && !isSearch) {{
        e.preventDefault();
        const search = document.querySelector('.sidebar-search');
        if (search) search.focus();
      }}
    }});

    // Reset kb index when mouse is used on sidebar
    document.querySelector('.sidebar-list').addEventListener('mouseenter', function() {{
      clearKbFocus();
      kbIndex = -1;
    }});
  }})();

  /* ── Init: select from URL hash or first entity ── */
  (function() {{
    const hash = location.hash.slice(1);
    if (hash && document.getElementById('detail-' + hash)) {{
      selectEntity(hash, true);
    }} else {{
      const first = document.querySelector('.sidebar-item');
      if (first) selectEntity(first.dataset.entityId, true);
    }}
  }})();
</script>
</body>
</html>'''
