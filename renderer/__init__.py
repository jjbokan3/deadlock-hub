"""HTML renderer — generates the complete patch notes page from structured data."""
from __future__ import annotations
import html as html_lib
import json
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


def _wiki_url(name: str) -> str:
    """Convert a hero or item name to a deadlock.wiki URL."""
    slug = name.replace(" ", "_").replace("&", "%26")
    return f"https://deadlock.wiki/{slug}"


# ── Change line rendering ────────────────────────────────────────

def _ability_wiki_url(hero_name: str, ability_slot: int, ability_name: str) -> str:
    """Build a wiki URL for a specific ability, e.g. https://deadlock.wiki/Wraith#(2)_Project_Mind"""
    hero_slug = hero_name.replace(" ", "_").replace("&", "%26")
    ability_slug = ability_name.replace(" ", "_")
    return f"https://deadlock.wiki/{hero_slug}#({ability_slot})_{ability_slug}"


def _render_change(c: Change, show_ability: bool = True, hero_name: str = "") -> str:
    sym, cls = DIRECTION_SYMBOLS.get(c.direction, ("●", "neutral"))

    # Determine tag
    if c.ability_slot and show_ability:
        slot_str = SLOT_COLORS.get(c.ability_slot, "general")
        tag_cls = f"tag-{slot_str}"
        bg_cls = f"bg-{slot_str}"
        tag_text = _e(c.ability_name or f"ABILITY {c.ability_slot}")
        if len(tag_text) > 18:
            tag_text = tag_text[:16] + "."
        # Make ability tag a link to the wiki with hover preview
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
    return (
        f'<div class="change-item {bg_cls}">'
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


# ── Section renderers ────────────────────────────────────────────

_DIRECTION_SORT = {ChangeDirection.BUFF: 0, ChangeDirection.NERF: 1, ChangeDirection.NEUTRAL: 2}

def _render_system_section(changes: list[Change]) -> str:
    if not changes:
        return ""
    sorted_changes = sorted(changes, key=lambda c: _DIRECTION_SORT.get(c.direction, 2))
    lines = "\n".join(_render_change(c, show_ability=False) for c in sorted_changes)
    return f'''
  <div class="system-section">
    <h2>System Changes</h2>
    <div class="system-card">
      <div class="changes-list">{lines}</div>
    </div>
  </div>'''


def _render_item_card(group: ItemChangeGroup) -> str:
    rating = group.rating or LLMRating.from_score(3, "")
    badge = _render_rating_badge(rating, small=True)
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
    return f'''
        <div class="item-card">
          <div class="item-header" onclick="toggleItem(this)">
            <span class="item-name">{_e(group.item.name)}</span>
            <div class="item-right">
              {badge}
              <span class="toggle-icon">▼</span>
            </div>
          </div>
          <div class="item-body">
            <div class="changes-list">{changes_html}</div>
            {explanation}
            <a href="{wiki}" target="_blank" rel="noopener" class="wiki-link" onclick="event.stopPropagation()">View on Wiki ↗</a>
          </div>
        </div>'''


def _render_item_groups(item_changes: dict[str, ItemChangeGroup]) -> str:
    if not item_changes:
        return ""

    # Group by category
    groups: dict[ItemCategory, list[ItemChangeGroup]] = {}
    for group in item_changes.values():
        cat = group.item.category
        groups.setdefault(cat, []).append(group)

    sections = []
    for cat in [ItemCategory.WEAPON, ItemCategory.VITALITY, ItemCategory.SPIRIT, ItemCategory.UNKNOWN]:
        items = groups.get(cat, [])
        if not items:
            continue
        title, icon_cls, icon_char = CATEGORY_META[cat]
        cards = "\n".join(_render_item_card(g) for g in items)
        sections.append(f'''
    <div class="item-group">
      <div class="item-group-header" onclick="toggleGroup(this)">
        <div class="item-group-left">
          <div class="item-group-icon {icon_cls}">{icon_char}</div>
          <div>
            <div class="item-group-title">{title}</div>
            <div class="item-group-count">{len(items)} ITEMS CHANGED</div>
          </div>
        </div>
        <span class="item-group-toggle">▼</span>
      </div>
      <div class="item-group-body">{cards}</div>
    </div>''')

    return f'''
  <div class="item-groups">
    <h2 style="font-family:'Rajdhani',sans-serif;font-size:22px;font-weight:700;letter-spacing:1px;text-transform:uppercase;margin-bottom:16px;color:var(--text-secondary);">Item Changes</h2>
    {"".join(sections)}
  </div>'''


def _sort_changes(changes: list[Change]) -> list[Change]:
    """Sort changes: base stats first, then by ability slot (1-4), then tier."""
    def sort_key(c: Change):
        # Base stat changes (no ability) come first
        has_ability = 0 if c.ability_slot is None and not c.ability_name else 1
        slot = c.ability_slot or 0
        tier = c.tier or 0
        # Within same ability+tier, preserve original order via index
        return (has_ability, slot, c.ability_name or "", tier)
    return sorted(changes, key=sort_key)


def _render_hero_card(group: HeroChangeGroup) -> str:
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
    return f'''
    <div class="hero-card">
      <div class="hero-header" onclick="toggleCard(this)">
        <span class="hero-name">{_e(group.hero.name)}</span>
        <div class="hero-right">
          {badge}
          <span class="toggle-icon">▼</span>
        </div>
      </div>
      <div class="hero-body">
        <div class="changes-list">{changes_html}</div>
        {explanation}
        <a href="{wiki}" target="_blank" rel="noopener" class="wiki-link" onclick="event.stopPropagation()">View on Wiki ↗</a>
      </div>
    </div>'''


def _render_hero_section(hero_changes: dict[str, HeroChangeGroup]) -> str:
    if not hero_changes:
        return ""
    cards = "\n".join(_render_hero_card(g) for g in sorted(hero_changes.values(), key=lambda g: g.hero.name.lower()))
    return f'''
  <h2 style="font-family:'Rajdhani',sans-serif;font-size:22px;font-weight:700;letter-spacing:1px;text-transform:uppercase;margin-bottom:16px;color:var(--text-secondary);">Hero Changes</h2>
  <div id="heroes">{cards}</div>'''


# ── Full page ────────────────────────────────────────────────────

def render(data: ParsedPatchNotes) -> str:
    """Render complete HTML page from parsed + rated patch notes."""
    system_html = _render_system_section(data.system_changes)
    items_html = _render_item_groups(data.item_changes)
    heroes_html = _render_hero_section(data.hero_changes)
    title = _e(data.title) if data.title else "Deadlock Patch Notes"
    summary_html = f'<p class="patch-summary">{_e(data.summary)}</p>' if data.summary else ''

    return PAGE_TEMPLATE.format(
        page_title=title,
        patch_summary=summary_html,
        system_section=system_html,
        items_section=items_html,
        heroes_section=heroes_html,
    )


# ── Page template (CSS + JS shell) ──────────────────────────────

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
  }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:var(--bg-deep); color:var(--text-primary); font-family:'Chakra Petch',sans-serif; min-height:100vh; line-height:1.6; }}
  body::before {{ content:''; position:fixed; inset:0; background:radial-gradient(ellipse at 20% 0%,#ff6b2c08 0%,transparent 50%),radial-gradient(ellipse at 80% 100%,#3ecfff06 0%,transparent 50%); pointer-events:none; z-index:0; }}
  .container {{ max-width:1100px; margin:0 auto; padding:40px 24px 80px; position:relative; z-index:1; }}
  header {{ text-align:center; margin-bottom:48px; padding-bottom:40px; border-bottom:1px solid var(--border); }}
  header .tag {{ display:inline-block; font-family:'JetBrains Mono',monospace; font-size:11px; letter-spacing:3px; text-transform:uppercase; color:var(--accent-orange); background:var(--accent-orange-dim); padding:6px 16px; border-radius:4px; margin-bottom:20px; }}
  header h1 {{ font-family:'Rajdhani',sans-serif; font-size:clamp(36px,5vw,56px); font-weight:700; letter-spacing:2px; text-transform:uppercase; line-height:1.1; background:linear-gradient(135deg,#e8eaf0 40%,var(--accent-orange) 100%); -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; }}
  header p {{ color:var(--text-secondary); margin-top:12px; font-size:15px; }}
  .patch-summary {{ color:var(--text-secondary); margin-top:14px; font-size:15px; line-height:1.6; max-width:700px; margin-left:auto; margin-right:auto; }}
  .legend {{ display:flex; flex-wrap:wrap; gap:16px 28px; justify-content:center; margin-bottom:40px; padding:20px 24px; background:var(--bg-card); border:1px solid var(--border); border-radius:10px; }}
  .legend-item {{ display:flex; align-items:center; gap:8px; font-size:13px; color:var(--text-secondary); }}
  .legend-dot {{ width:10px; height:10px; border-radius:50%; flex-shrink:0; }}
  .rating-legend {{ display:flex; flex-wrap:wrap; gap:12px 24px; justify-content:center; margin-bottom:44px; font-size:13px; color:var(--text-dim); }}
  .rating-legend span {{ display:flex; align-items:center; gap:6px; }}
  .rating-legend .r-label {{ font-weight:600; font-family:'JetBrains Mono',monospace; font-size:12px; }}
  .system-section {{ margin-bottom:44px; }}
  .system-section h2, .item-groups h2 {{ font-family:'Rajdhani',sans-serif; font-size:22px; font-weight:700; letter-spacing:1px; text-transform:uppercase; margin-bottom:16px; color:var(--text-secondary); }}
  .system-card {{ background:var(--bg-card); border:1px solid var(--border); border-radius:10px; padding:20px 24px; }}
  .hero-card, .item-group {{ background:var(--bg-card); border:1px solid var(--border); border-radius:12px; margin-bottom:20px; overflow:hidden; transition:border-color 0.2s; }}
  .hero-card:hover, .item-group:hover {{ border-color:var(--border-hover); }}
  .hero-header, .item-group-header {{ display:flex; align-items:center; justify-content:space-between; padding:20px 24px; cursor:pointer; user-select:none; gap:16px; flex-wrap:wrap; }}
  .hero-header:hover, .item-group-header:hover {{ background:var(--bg-card-hover); }}
  .hero-name {{ font-family:'Rajdhani',sans-serif; font-size:26px; font-weight:700; letter-spacing:1px; text-transform:uppercase; }}
  .hero-name-wrap {{ display:flex; align-items:center; gap:14px; }}
  .hero-img {{ width:44px; height:44px; border-radius:8px; object-fit:cover; border:1px solid #ffffff15; background:#1a1d28; flex-shrink:0; opacity:0; transition:opacity 0.3s; }}
  .hero-img.loaded {{ opacity:1; }}
  .hero-right, .item-right {{ display:flex; align-items:center; gap:16px; flex-wrap:wrap; }}
  .hero-body, .item-body {{ display:none; padding:0 24px 24px; }}
  .hero-card.open .hero-body, .item-card.open .item-body {{ display:block; }}
  .item-group-body {{ display:none; padding:0 16px 16px; }}
  .item-group.open .item-group-body {{ display:block; }}
  .item-group-left {{ display:flex; align-items:center; gap:14px; }}
  .item-group-icon {{ width:32px; height:32px; border-radius:8px; display:flex; align-items:center; justify-content:center; font-size:16px; flex-shrink:0; }}
  .item-group-icon.weapon {{ background:#ff6b2c20; color:var(--accent-orange); border:1px solid #ff6b2c35; }}
  .item-group-icon.vitality {{ background:#5dff7e20; color:var(--ability-2); border:1px solid #5dff7e35; }}
  .item-group-icon.spirit {{ background:#d98fff20; color:var(--ability-3); border:1px solid #d98fff35; }}
  .item-group-title {{ font-family:'Rajdhani',sans-serif; font-size:22px; font-weight:700; letter-spacing:1px; text-transform:uppercase; }}
  .item-group-count {{ font-family:'JetBrains Mono',monospace; font-size:11px; color:var(--text-dim); letter-spacing:1px; }}
  .item-group-toggle, .toggle-icon {{ color:var(--text-dim); font-size:18px; transition:transform 0.3s; flex-shrink:0; }}
  .item-group.open .item-group-toggle, .hero-card.open .toggle-icon, .item-card.open .toggle-icon {{ transform:rotate(180deg); }}
  .item-card {{ background:#0e1018; border:1px solid #1e2230; border-radius:8px; margin-bottom:8px; overflow:hidden; transition:border-color 0.2s; }}
  .item-card:last-child {{ margin-bottom:0; }}
  .item-header {{ display:flex; align-items:center; justify-content:space-between; padding:12px 16px; cursor:pointer; user-select:none; gap:12px; flex-wrap:wrap; }}
  .item-header:hover {{ background:#14171f; }}
  .item-name {{ font-family:'Rajdhani',sans-serif; font-size:18px; font-weight:600; letter-spacing:0.5px; }}
  .item-name-wrap {{ display:flex; align-items:center; gap:10px; }}
  .item-img {{ width:28px; height:28px; border-radius:6px; object-fit:contain; background:#1a1d28; border:1px solid #ffffff10; flex-shrink:0; opacity:0; transition:opacity 0.3s; }}
  .item-img.loaded {{ opacity:1; }}
  .item-card .toggle-icon {{ font-size:14px; }}
  .changes-list {{ display:flex; flex-direction:column; gap:6px; margin-bottom:20px; }}
  .change-item {{ display:flex; align-items:flex-start; gap:10px; padding:8px 12px; border-radius:6px; font-size:14px; line-height:1.5; }}
  .change-item .ability-tag {{ font-family:'JetBrains Mono',monospace; font-size:11px; font-weight:500; padding:2px 8px; border-radius:4px; white-space:nowrap; flex-shrink:0; margin-top:2px; letter-spacing:0.5px; text-decoration:none; }}
  a.ability-tag:hover {{ filter:brightness(1.3); }}
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
  .rating-badge {{ display:flex; align-items:center; gap:8px; padding:6px 14px; border-radius:6px; font-family:'JetBrains Mono',monospace; font-size:12px; font-weight:600; letter-spacing:1px; text-transform:uppercase; white-space:nowrap; }}
  .rating-badge.sm {{ font-size:11px; padding:4px 10px; }}
  .rating-badge.sm .stars {{ gap:2px; }} .rating-badge.sm .star {{ width:11px; height:11px; }}
  .rating-1 {{ background:#ff3b3b18; color:var(--rating-1); border:1px solid #ff3b3b30; }}
  .rating-2 {{ background:#ff8c4218; color:var(--rating-2); border:1px solid #ff8c4230; }}
  .rating-3 {{ background:#a0a5b818; color:var(--rating-3); border:1px solid #a0a5b830; }}
  .rating-4 {{ background:#5dff7e18; color:var(--rating-4); border:1px solid #5dff7e30; }}
  .rating-5 {{ background:#3ecfff18; color:var(--rating-5); border:1px solid #3ecfff30; }}
  .stars {{ display:flex; gap:3px; }} .star {{ width:14px; height:14px; display:inline-block; }} .star svg {{ width:100%; height:100%; }}
  .rating-explanation {{ padding:16px 18px; background:#ffffff06; border-left:3px solid var(--accent-orange); border-radius:0 8px 8px 0; font-size:14px; color:var(--text-secondary); line-height:1.65; }}
  .rating-explanation strong {{ color:var(--text-primary); font-weight:600; }}
  .controls {{ display:flex; justify-content:flex-end; margin-bottom:16px; }}
  .controls button {{ font-family:'Chakra Petch',sans-serif; font-size:13px; color:var(--accent-orange); background:var(--accent-orange-dim); border:1px solid #ff6b2c40; padding:8px 18px; border-radius:6px; cursor:pointer; transition:all 0.2s; }}
  .controls button:hover {{ background:#ff6b2c22; border-color:var(--accent-orange); }}
  .street-brawl-tag {{ font-family:'JetBrains Mono',monospace; font-size:10px; font-weight:600; padding:2px 6px; border-radius:3px; color:#ffb347; background:#ffb34715; border:1px solid #ffb34730; white-space:nowrap; flex-shrink:0; margin-top:2px; letter-spacing:0.5px; text-transform:uppercase; }}
  .wiki-link {{ display:inline-block; margin-top:12px; font-family:'JetBrains Mono',monospace; font-size:11px; letter-spacing:0.5px; color:var(--text-dim); background:#ffffff08; border:1px solid var(--border); padding:5px 12px; border-radius:5px; text-decoration:none; transition:all 0.2s; }}
  .wiki-link:hover {{ color:var(--accent-orange); border-color:var(--accent-orange); background:var(--accent-orange-dim); }}
  .ability-icon {{ width:18px; height:18px; border-radius:4px; object-fit:contain; vertical-align:middle; margin-right:2px; opacity:0; transition:opacity 0.3s; flex-shrink:0; margin-top:1px; }}
  .ability-icon.loaded {{ opacity:1; }}
  .github-link {{ position:fixed; top:16px; right:16px; z-index:100; display:flex; align-items:center; gap:8px; font-family:'JetBrains Mono',monospace; font-size:12px; color:var(--text-dim); background:var(--bg-card); border:1px solid var(--border); padding:8px 14px; border-radius:8px; text-decoration:none; transition:all 0.2s; }}
  .github-link:hover {{ color:var(--text-primary); border-color:var(--border-hover); background:var(--bg-card-hover); }}
  .github-link svg {{ width:18px; height:18px; fill:currentColor; }}
  @media (max-width:640px) {{
    .container {{ padding:24px 14px 60px; }} .hero-header {{ padding:16px; }}
    .hero-body {{ padding:0 16px 20px; }} .hero-name {{ font-size:20px; }}
    .legend {{ gap:10px 20px; padding:14px 16px; }}
    .rating-badge {{ font-size:11px; padding:5px 10px; }}
    .change-item {{ font-size:13px; }} .hero-img {{ width:36px; height:36px; }}
    .item-img {{ width:24px; height:24px; }}
    .github-link span {{ display:none; }} .github-link {{ padding:8px; }}
    .ability-popup-prop {{ min-width:70px; padding:6px 8px 4px; }}
  }}
</style>
</head>
<body>
<a href="https://github.com/jjbokan3/deadlock-hub" target="_blank" rel="noopener" class="github-link"><svg viewBox="0 0 16 16"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/></svg><span>GitHub</span></a>
<div class="container">
  <header>
    <div class="tag">Patch Notes</div>
    <h1>{page_title}</h1>
    {patch_summary}
  </header>

  <div class="legend">
    <div class="legend-item"><div class="legend-dot" style="background:var(--ability-general)"></div> Base Stats</div>
    <div class="legend-item"><div class="legend-dot" style="background:var(--ability-1)"></div> Ability 1</div>
    <div class="legend-item"><div class="legend-dot" style="background:var(--ability-2)"></div> Ability 2</div>
    <div class="legend-item"><div class="legend-dot" style="background:var(--ability-3)"></div> Ability 3</div>
    <div class="legend-item"><div class="legend-dot" style="background:var(--ability-4)"></div> Ability 4 / Ult</div>
  </div>

  <div class="rating-legend">
    <span><span class="r-label" style="color:var(--rating-1)">★</span> Huge Nerf</span>
    <span><span class="r-label" style="color:var(--rating-2)">★★</span> Nerf</span>
    <span><span class="r-label" style="color:var(--rating-3)">★★★</span> Neutral / Mixed</span>
    <span><span class="r-label" style="color:var(--rating-4)">★★★★</span> Buff</span>
    <span><span class="r-label" style="color:var(--rating-5)">★★★★★</span> Big Buff</span>
  </div>

  <div class="controls">
    <button onclick="toggleAll()">Expand / Collapse All</button>
  </div>

  {system_section}
  {items_section}
  {heroes_section}

</div>

<script>
  function toggleCard(h){{ h.closest('.hero-card').classList.toggle('open'); }}
  function toggleGroup(h){{ h.closest('.item-group').classList.toggle('open'); }}
  function toggleItem(h){{ h.closest('.item-card').classList.toggle('open'); }}
  function toggleAll(){{
    const c=document.querySelectorAll('.hero-card,.item-group,.item-card');
    const allOpen=[...c].every(x=>x.classList.contains('open'));
    c.forEach(x=>{{ if(allOpen) x.classList.remove('open'); else x.classList.add('open'); }});
  }}
  function renderStars(){{
    document.querySelectorAll('.stars').forEach(el=>{{
      const b=el.closest('.rating-badge'); let n=3;
      if(b.classList.contains('rating-1'))n=1;else if(b.classList.contains('rating-2'))n=2;
      else if(b.classList.contains('rating-3'))n=3;else if(b.classList.contains('rating-4'))n=4;
      else if(b.classList.contains('rating-5'))n=5;
      let h='';for(let i=0;i<5;i++){{const f=i<n;h+=`<span class="star"><svg viewBox="0 0 20 20" fill="${{f?'var(--star-filled)':'var(--star-empty)'}}"><path d="M10 1.5l2.47 5.01 5.53.8-4 3.9.94 5.49L10 14.26 5.06 16.7 6 11.21l-4-3.9 5.53-.8z"/></svg></span>`;}}
      el.innerHTML=h;
    }});
  }}
  renderStars();

  // Runtime image injection from Deadlock API
  const HEROES_URL='https://assets.deadlock-api.com/v2/heroes';
  const ITEMS_URL='https://assets.deadlock-api.com/v2/items';
  const HERO_ALIASES={{'Doorman':'The Doorman'}};
  function createImg(src,cls){{const img=document.createElement('img');img.src=src;img.className=cls;img.loading='lazy';img.onload=()=>img.classList.add('loaded');img.onerror=()=>img.style.display='none';return img;}}
  // Global store for ability data (populated by loadImages, used by popup)
  const abilityDataStore={{}};

  async function loadImages(){{
    let heroes,items;
    try{{const[hr,ir]=await Promise.all([fetch(HEROES_URL),fetch(ITEMS_URL)]);heroes=await hr.json();items=await ir.json();}}catch(e){{return;}}
    const hm={{}};heroes.forEach(h=>{{if(h.name)hm[h.name.toLowerCase()]=h;}});
    const im={{}};const ic={{}};items.forEach(i=>{{if(i.name)im[i.name.toLowerCase()]=i;if(i.class_name)ic[i.class_name.toLowerCase()]=i;}});

    // Build ability data store: heroName_slot -> full item data
    heroes.forEach(h=>{{
      if(!h.name||!h.items)return;
      const sigs=['signature1','signature2','signature3','signature4'];
      sigs.forEach((k,i)=>{{
        const cn=h.items[k];
        if(!cn)return;
        const item=ic[cn.toLowerCase()];
        if(item){{
          const key=h.name.toLowerCase()+'_'+(i+1);
          abilityDataStore[key]={{...item,slot:i+1,heroName:h.name}};
        }}
      }});
    }});

    document.querySelectorAll('.hero-card').forEach(card=>{{
      const ne=card.querySelector('.hero-name');if(!ne)return;
      const n=ne.textContent.trim();const an=HERO_ALIASES[n]||n;
      const h=hm[an.toLowerCase()];if(!h||!h.images)return;
      const url=h.images.icon_hero_card||h.images.icon_image_small;if(!url)return;
      if(card.querySelector('.hero-name-wrap'))return;
      const w=document.createElement('div');w.className='hero-name-wrap';
      w.appendChild(createImg(url,'hero-img'));ne.parentNode.insertBefore(w,ne);w.appendChild(ne);
      const sigs=['signature1','signature2','signature3','signature4'];
      const am={{}};if(h.items)sigs.forEach((k,i)=>{{if(h.items[k])am[i+1]=h.items[k].toLowerCase();}});
      card.querySelectorAll('.ability-tag').forEach(tag=>{{
        let s=null;if(tag.classList.contains('tag-1'))s=1;else if(tag.classList.contains('tag-2'))s=2;
        else if(tag.classList.contains('tag-3'))s=3;else if(tag.classList.contains('tag-4'))s=4;
        if(s&&am[s]){{const ai=ic[am[s]];if(ai&&ai.image){{if(tag.previousElementSibling&&tag.previousElementSibling.classList.contains('ability-icon'))return;tag.parentNode.insertBefore(createImg(ai.image,'ability-icon'),tag);}}}}
      }});
    }});
    document.querySelectorAll('.item-card').forEach(card=>{{
      const ne=card.querySelector('.item-name');if(!ne)return;
      const i=im[ne.textContent.trim().toLowerCase()];if(!i||!i.image)return;
      if(card.querySelector('.item-name-wrap'))return;
      const w=document.createElement('div');w.className='item-name-wrap';
      w.appendChild(createImg(i.image,'item-img'));ne.parentNode.insertBefore(w,ne);w.appendChild(ne);
    }});
  }}
  loadImages();

  // Ability popup on hover
  (function(){{
    const popup=document.createElement('div');
    popup.className='ability-popup';
    document.body.appendChild(popup);
    let hoverTimer=null;
    let currentKey='';

    function buildPopup(data){{
      const props=data.properties||{{}};
      const rawDesc=data.description||{{}};
      const upgrades=data.upgrades||[];
      const slotLabels={{1:'Ability 1',2:'Ability 2',3:'Ability 3',4:'Ultimate'}};

      // Header with icon + name
      let html='<div class="ability-popup-header">';
      if(data.image)html+=`<img class="ability-popup-icon" src="${{data.image}}" alt="">`;
      html+=`<div><div class="ability-popup-title">${{data.name||''}}</div>`;
      html+=`<div class="ability-popup-slot">${{slotLabels[data.slot]||'Ability'}}</div>`;
      html+='</div></div>';

      // Core stats bar (cooldown, duration, range)
      const headerStats=['AbilityCooldown','AbilityDuration','AbilityCastRange','AbilityChannelTime'];
      let statsHtml='';
      for(const key of headerStats){{
        const p=props[key];
        if(!p||typeof p!=='object')continue;
        const val=p.value;
        if(val===undefined||val===null||val===''||val==='0'||val===0)continue;
        const icon=p.icon?`<img src="${{p.icon}}" alt="">`:'';
        const postfix=p.postfix||'';
        statsHtml+=`<div class="ability-popup-stat">${{icon}}<span class="stat-val">${{val}}</span><span class="stat-unit">${{postfix}}</span></div>`;
      }}
      if(statsHtml)html+=`<div class="ability-popup-stats">${{statsHtml}}</div>`;

      // Description
      const descText=typeof rawDesc==='object'?(rawDesc.desc||''):String(rawDesc);
      if(descText){{
        // Strip SVG/HTML tags but keep text
        const cleanDesc=descText.replace(/<svg[\\s\\S]*?<\\/svg>/gi,'🔮').replace(/<[^>]*>/g,'').replace(/\\n/g,' ').trim();
        if(cleanDesc)html+=`<div class="ability-popup-desc">${{cleanDesc}}</div>`;
      }}

      // Properties as stat boxes — only show player-facing stats (must have label + icon)
      // Skip header stats, internal mechanics, and negative modifiers
      const skipKeys=new Set([...headerStats,
        'AbilityCastDelay','AbilityUnitTargetLimit','AbilityUnitTargetType','AbilityCastAnimation',
        'TickRate','AbilityCooldownBetweenCharge','ChannelMoveSpeed',
        'DashSpeed','DashRange','DashRadius','SideMoveSpeed','TurnRateMax',
        'CounterattackAntiMashDelay','SlashConeAngle','SlashRadius','SlashHalfWidth',
        'DampingFactor','LiftHeight','DamageThreshold','ParryWindow',
        'AbilityResourceCost','AbilityCharges','AbilityMaxCharges',
        'ProjectileSpeed','BulletSpeed','TravelSpeed',
        'MaxJumpHeight','MinJumpHeight','LaunchAngle','VerticalLaunchSpeed',
      ]);
      let propBoxes='';
      for(const[k,v] of Object.entries(props)){{
        if(skipKeys.has(k))continue;
        if(!v||typeof v!=='object')continue;
        const val=v.value;
        if(val===undefined||val===null||val===''||val==='0'||val===0)continue;
        if(!v.label||!v.icon)continue; // Must have both label and icon (player-facing)
        if(typeof val==='number'&&val<0)continue; // Skip negative modifiers (internal)
        const postfix=v.postfix||'';
        // Check for spirit scaling
        const sf=v.scale_function;
        const hasScale=sf&&sf.specific_stat_scale_type==='ETechPower';
        const scaleVal=hasScale&&sf.stat_scale?sf.stat_scale:null;
        propBoxes+=`<div class="ability-popup-prop">`;
        if(scaleVal)propBoxes+=`<span class="prop-scale">x${{scaleVal}}</span>`;
        else if(hasScale)propBoxes+=`<span class="prop-scale">✦</span>`;
        propBoxes+=`<span class="prop-val">${{val}}<span class="prop-unit">${{postfix}}</span></span>`;
        propBoxes+=`<span class="prop-label">${{v.label}}</span></div>`;
      }}
      if(propBoxes)html+=`<div class="ability-popup-props">${{propBoxes}}</div>`;

      // Upgrades (array: index 0=T1, 1=T2, 2=T3)
      let upgradeHtml='';
      const apCosts=[1,2,5];
      for(let i=0;i<Math.min(upgrades.length,3);i++){{
        const u=upgrades[i];
        if(!u||!u.property_upgrades||!u.property_upgrades.length)continue;
        let parts=[];
        for(const pu of u.property_upgrades){{
          const propDef=props[pu.name];
          const label=propDef&&propDef.label?propDef.label:pu.name.replace(/([A-Z])/g,' $1').trim();
          const postfix=propDef&&propDef.postfix?propDef.postfix:'';
          const bonus=pu.bonus;
          const isScale=pu.upgrade_type==='EAddToScale';
          if(isScale){{
            parts.push(`+${{bonus}} Spirit Scaling`);
          }}else{{
            const sign=typeof bonus==='number'&&bonus>0?'+':'';
            parts.push(`${{sign}}${{bonus}}${{postfix}} ${{label}}`);
          }}
        }}
        upgradeHtml+=`<div class="ability-popup-upgrade"><div class="ability-popup-upgrade-hdr">◆ ${{apCosts[i]}}</div><div class="ability-popup-upgrade-body">${{parts.join('<br>')}}</div></div>`;
      }}
      if(upgradeHtml)html+=`<div class="ability-popup-upgrades">${{upgradeHtml}}</div>`;

      return html;
    }}

    function show(tag){{
      const heroName=tag.dataset.heroName;
      const slot=tag.dataset.abilitySlot;
      if(!heroName||!slot)return;
      const key=heroName.toLowerCase()+'_'+slot;
      if(currentKey===key&&popup.classList.contains('visible'))return;
      const data=abilityDataStore[key];
      if(!data)return;
      currentKey=key;
      popup.innerHTML=buildPopup(data);
      // Position near the tag
      const rect=tag.getBoundingClientRect();
      let left=rect.right+12;
      let top=rect.top-60;
      const pw=380;
      if(left+pw>window.innerWidth)left=rect.left-pw-12;
      if(left<8)left=8;
      const ph=popup.offsetHeight||350;
      if(top+ph>window.innerHeight)top=window.innerHeight-ph-8;
      if(top<8)top=8;
      popup.style.left=left+'px';
      popup.style.top=top+'px';
      popup.classList.add('visible');
    }}

    function hide(){{
      clearTimeout(hoverTimer);
      hoverTimer=null;
      popup.classList.remove('visible');
      currentKey='';
    }}

    const isTouch='ontouchstart' in window;

    if(isTouch){{
      // Tap to toggle popup, tap elsewhere to close
      document.addEventListener('click',function(e){{
        const tag=e.target.closest('a.ability-tag[data-hero-name]');
        if(tag){{
          e.preventDefault();
          e.stopPropagation();
          if(currentKey===tag.dataset.heroName.toLowerCase()+'_'+tag.dataset.abilitySlot&&popup.classList.contains('visible')){{
            hide();
          }}else{{
            show(tag);
          }}
          return;
        }}
        if(!popup.contains(e.target))hide();
      }});
    }}else{{
      // Desktop: hover with delay
      document.addEventListener('mouseover',function(e){{
        const tag=e.target.closest('a.ability-tag[data-hero-name]');
        if(!tag)return;
        clearTimeout(hoverTimer);
        hoverTimer=setTimeout(()=>show(tag),800);
      }});

      document.addEventListener('mouseout',function(e){{
        const tag=e.target.closest('a.ability-tag[data-hero-name]');
        if(!tag)return;
        const related=e.relatedTarget;
        if(related&&(popup.contains(related)||popup===related))return;
        hide();
      }});

      popup.addEventListener('mouseenter',function(){{
        clearTimeout(hoverTimer);
      }});
      popup.addEventListener('mouseleave',function(){{
        hide();
      }});
    }}
  }})();
</script>
</body>
</html>'''
