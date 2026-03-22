"""Generate the Hero Browser page at site/deadlock/heroes.html.

A single static HTML page that fetches all hero/ability data from the
Deadlock Assets API at runtime and renders interactive hero cards with
full ability details, stats, scaling, and tier upgrades.
"""
from __future__ import annotations
import os
import logging

logger = logging.getLogger(__name__)


def write_heroes_page(deadlock_dir: str):
    """Write the heroes page to deadlock_dir/heroes.html."""
    os.makedirs(deadlock_dir, exist_ok=True)
    path = os.path.join(deadlock_dir, "heroes.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(HEROES_TEMPLATE)
    logger.info(f"Heroes page written: {path}")
    return path


HEROES_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hero Browser — Deadlock</title>
<link rel="icon" href="/deadlock/deadlock_icon.ico" type="image/x-icon">
<link href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;500;600;700&family=Chakra+Petch:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {
    --bg:#0a0b0f; --bg-card:#12141c; --bg-card-hover:#181b26;
    --border:#252a38; --border-hover:#3a4158;
    --text:#e8eaf0; --dim:#8b90a5; --faint:#565b72;
    --accent:#ff6b2c; --accent-dim:#ff6b2c25;
    --ability-1:#3ecfff; --ability-2:#5dff7e; --ability-3:#d98fff; --ability-4:#ffcf3e;
    --ability-1-bg:#3ecfff15; --ability-2-bg:#5dff7e15; --ability-3-bg:#d98fff15; --ability-4-bg:#ffcf3e15;
  }
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background:var(--bg); color:var(--text); font-family:'Chakra Petch',sans-serif; min-height:100vh; line-height:1.6; }
  body::before { content:''; position:fixed; inset:0; background:radial-gradient(ellipse at 20% 0%,#ff6b2c08 0%,transparent 50%),radial-gradient(ellipse at 80% 100%,#3ecfff06 0%,transparent 50%); pointer-events:none; }
  .container { max-width:1200px; margin:0 auto; padding:40px 24px 80px; position:relative; z-index:1; }
  .back { display:inline-flex; align-items:center; gap:6px; font-family:'JetBrains Mono',monospace; font-size:12px; color:var(--faint); text-decoration:none; margin-bottom:32px; transition:color 0.2s; letter-spacing:0.5px; }
  .back:hover { color:var(--dim); }
  header { text-align:center; margin-bottom:32px; }
  .tag { display:inline-block; font-family:'JetBrains Mono',monospace; font-size:11px; letter-spacing:3px; text-transform:uppercase; color:var(--accent); background:var(--accent-dim); padding:6px 16px; border-radius:4px; margin-bottom:20px; border:1px solid #ff6b2c30; }
  header h1 { font-family:'Rajdhani',sans-serif; font-size:clamp(36px,5vw,56px); font-weight:700; letter-spacing:2px; text-transform:uppercase; line-height:1.1; background:linear-gradient(135deg,#e8eaf0 40%,var(--accent) 100%); -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; }
  header p { color:var(--dim); margin-top:8px; font-size:15px; }

  /* Search */
  .search-wrap { max-width:400px; margin:0 auto 32px; position:relative; }
  .search-wrap input { width:100%; padding:12px 18px 12px 42px; background:var(--bg-card); border:1px solid var(--border); border-radius:10px; color:var(--text); font-family:'Chakra Petch',sans-serif; font-size:15px; outline:none; transition:border-color 0.2s; }
  .search-wrap input:focus { border-color:var(--accent); }
  .search-wrap input::placeholder { color:var(--faint); }
  .search-wrap .search-icon { position:absolute; left:14px; top:50%; transform:translateY(-50%); color:var(--faint); font-size:16px; }

  /* Hero grid */
  .hero-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(140px,1fr)); gap:12px; }
  .hero-tile { background:var(--bg-card); border:1px solid var(--border); border-radius:12px; padding:16px 12px; text-align:center; cursor:pointer; transition:all 0.2s; user-select:none; }
  .hero-tile:hover { border-color:var(--border-hover); background:var(--bg-card-hover); transform:translateY(-2px); }
  .hero-tile.active { border-color:var(--accent); box-shadow:0 0 20px #ff6b2c20; }
  .hero-tile img { width:64px; height:64px; border-radius:8px; object-fit:cover; margin-bottom:8px; background:#1a1d28; }
  .hero-tile .name { font-family:'Rajdhani',sans-serif; font-size:15px; font-weight:700; letter-spacing:0.5px; text-transform:uppercase; line-height:1.2; }
  .hero-tile.hidden { display:none; }

  /* Loading */
  .loading { text-align:center; padding:80px 20px; color:var(--dim); font-size:16px; }
  .loading .spinner { display:inline-block; width:32px; height:32px; border:3px solid var(--border); border-top-color:var(--accent); border-radius:50%; animation:spin 0.8s linear infinite; margin-bottom:16px; }
  @keyframes spin { to { transform:rotate(360deg); } }

  /* Hero detail panel */
  .hero-detail { display:none; margin-top:24px; background:var(--bg-card); border:1px solid var(--border); border-radius:14px; overflow:hidden; animation:fadeIn 0.3s ease; }
  .hero-detail.visible { display:block; }
  @keyframes fadeIn { from { opacity:0; transform:translateY(10px); } to { opacity:1; transform:translateY(0); } }
  .detail-header { display:flex; align-items:center; gap:20px; padding:24px 28px; border-bottom:1px solid var(--border); }
  .detail-header img { width:72px; height:72px; border-radius:10px; object-fit:cover; border:2px solid #ffffff15; }
  .detail-header .hero-title { font-family:'Rajdhani',sans-serif; font-size:32px; font-weight:700; letter-spacing:1px; text-transform:uppercase; }
  .detail-header .wiki-link { font-family:'JetBrains Mono',monospace; font-size:11px; color:var(--faint); text-decoration:none; background:#ffffff08; border:1px solid var(--border); padding:5px 12px; border-radius:5px; transition:all 0.2s; margin-left:auto; }
  .detail-header .wiki-link:hover { color:var(--accent); border-color:var(--accent); background:var(--accent-dim); }
  .detail-close { margin-left:12px; background:none; border:1px solid var(--border); color:var(--faint); width:32px; height:32px; border-radius:6px; cursor:pointer; font-size:16px; transition:all 0.2s; display:flex; align-items:center; justify-content:center; }
  .detail-close:hover { color:var(--text); border-color:var(--border-hover); }

  /* Ability tabs */
  .ability-tabs { display:flex; border-bottom:1px solid var(--border); }
  .ability-tab { flex:1; padding:14px 12px; text-align:center; cursor:pointer; font-family:'Rajdhani',sans-serif; font-size:14px; font-weight:700; letter-spacing:0.5px; text-transform:uppercase; color:var(--dim); border-bottom:2px solid transparent; transition:all 0.2s; user-select:none; }
  .ability-tab:hover { color:var(--text); background:#ffffff05; }
  .ability-tab.active { border-bottom-color:var(--accent); color:var(--text); }
  .ability-tab .tab-slot { font-family:'JetBrains Mono',monospace; font-size:10px; display:block; margin-bottom:2px; }
  .ability-tab .tab-slot-1 { color:var(--ability-1); }
  .ability-tab .tab-slot-2 { color:var(--ability-2); }
  .ability-tab .tab-slot-3 { color:var(--ability-3); }
  .ability-tab .tab-slot-4 { color:var(--ability-4); }

  /* Ability detail */
  .ability-detail { display:none; padding:28px; }
  .ability-detail.visible { display:block; }
  .ability-head { display:flex; align-items:center; gap:16px; margin-bottom:20px; }
  .ability-head img { width:48px; height:48px; border-radius:8px; object-fit:contain; }
  .ability-head .ability-title { font-family:'Rajdhani',sans-serif; font-size:26px; font-weight:700; letter-spacing:1px; text-transform:uppercase; }
  .ability-head .ability-slot-label { font-family:'JetBrains Mono',monospace; font-size:11px; margin-top:2px; }

  /* Core stats bar */
  .core-stats { display:flex; flex-wrap:wrap; gap:10px; margin-bottom:20px; }
  .core-stat { display:flex; align-items:center; gap:6px; background:#2C2C2C; padding:6px 14px; border-radius:6px; font-size:14px; }
  .core-stat .val { font-weight:700; }
  .core-stat .unit { font-size:12px; color:#B2B2B2; }
  .core-stat .label { font-size:11px; color:#9C9C9C; margin-left:4px; }

  /* Description */
  .ability-desc { font-size:14px; color:#ccc; line-height:1.6; margin-bottom:24px; padding:16px 18px; background:#ffffff05; border-radius:8px; border-left:3px solid #583D6F; }

  /* Properties grid */
  .props-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(130px,1fr)); gap:8px; margin-bottom:24px; }
  .prop-box { display:flex; flex-direction:column; align-items:center; text-align:center; background:radial-gradient(circle,#2a292b,#3b3145); border:2px solid #583D6F; border-radius:6px; padding:12px 10px 8px; position:relative; }
  .prop-box .prop-val { font-weight:700; font-size:16px; }
  .prop-box .prop-unit { font-size:11px; color:#B2B2B2; }
  .prop-box .prop-label { font-size:11px; color:#9C9C9C; margin-top:4px; line-height:1.2; }
  .prop-box .prop-scale { position:absolute; top:-8px; right:-4px; font-size:10px; color:#E3BDFA; background:#533669; padding:1px 6px; border-radius:4px; font-weight:700; font-style:italic; }
  .prop-box.conditional { border-color:#444; background:radial-gradient(circle,#222,#2a2a2a); }

  /* Upgrades */
  .upgrades-row { display:flex; gap:10px; }
  .upgrade-card { flex:1; background:#131211; border-radius:8px; overflow:hidden; border:1px solid #2a2a2a; }
  .upgrade-hdr { background:#402f4c; padding:6px 0; text-align:center; font-family:'JetBrains Mono',monospace; font-size:13px; font-weight:700; color:#bc8ee8; }
  .upgrade-body { padding:12px 10px; font-size:13px; color:#ccc; text-align:center; line-height:1.4; }

  /* GitHub */
  .github { position:fixed; top:20px; right:20px; display:flex; align-items:center; gap:8px; font-family:'JetBrains Mono',monospace; font-size:11px; color:var(--faint); text-decoration:none; background:var(--bg-card); border:1px solid var(--border); padding:8px 14px; border-radius:8px; transition:all 0.2s; z-index:10; }
  .github:hover { color:var(--accent); border-color:var(--accent); }
  .github svg { width:16px; height:16px; fill:currentColor; }

  /* Responsive */
  @media(max-width:640px) {
    .container { padding:24px 14px 60px; }
    .hero-grid { grid-template-columns:repeat(auto-fill,minmax(100px,1fr)); gap:8px; }
    .hero-tile { padding:12px 8px; }
    .hero-tile img { width:48px; height:48px; }
    .hero-tile .name { font-size:12px; }
    .detail-header { flex-wrap:wrap; padding:18px 16px; gap:14px; }
    .detail-header img { width:56px; height:56px; }
    .detail-header .hero-title { font-size:24px; }
    .ability-detail { padding:18px 14px; }
    .ability-tab { padding:10px 6px; font-size:11px; }
    .props-grid { grid-template-columns:repeat(auto-fill,minmax(100px,1fr)); }
    .upgrades-row { flex-direction:column; }
    .github { top:12px; right:12px; padding:6px 10px; font-size:10px; }
  }
</style>
</head>
<body>
<a href="https://github.com/jjbokan3/deadlock-hub" target="_blank" rel="noopener" class="github">
  <svg viewBox="0 0 16 16"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>
  GitHub
</a>
<div class="container">
  <a href="/deadlock/" class="back">← deadlock hub</a>
  <header>
    <div class="tag">Hero Browser</div>
    <h1>Deadlock Heroes</h1>
    <p>Explore abilities, stats, scaling & tier upgrades</p>
  </header>
  <div class="search-wrap">
    <span class="search-icon">🔍</span>
    <input type="text" id="hero-search" placeholder="Search heroes..." autocomplete="off">
  </div>
  <div id="hero-grid" class="hero-grid">
    <div class="loading"><div class="spinner"></div><br>Loading heroes from API...</div>
  </div>
  <div id="hero-detail" class="hero-detail"></div>
</div>

<script>
const HEROES_URL='https://assets.deadlock-api.com/v2/heroes';
const ITEMS_URL='https://assets.deadlock-api.com/v2/items';

// Properties to skip (internal mechanics, not player-facing)
const SKIP_PROPS = new Set([
  'AbilityResourceCost','AbilityCooldownBetweenCharge','ChannelMoveSpeed',
  'AbilityChargesReceiveFromPassive'
]);

// Core stat keys shown in the stats bar (not in the props grid)
const CORE_KEYS = new Set(['AbilityCooldown','AbilityDuration','AbilityCastRange','AbilityCharges']);
const CORE_LABELS = {
  AbilityCooldown: {icon:'⏱', label:'Cooldown'},
  AbilityDuration: {icon:'⏳', label:'Duration'},
  AbilityCastRange: {icon:'◎', label:'Range'},
  AbilityCharges: {icon:'✦', label:'Charges'},
};

let heroesData = [];
let itemsByClass = {};
let selectedHero = null;

async function init() {
  try {
    const [hr, ir] = await Promise.all([fetch(HEROES_URL), fetch(ITEMS_URL)]);
    const heroes = await hr.json();
    const items = await ir.json();

    items.forEach(i => { if(i.class_name) itemsByClass[i.class_name.toLowerCase()] = i; });
    heroesData = heroes.filter(h => h.player_selectable && h.name).sort((a,b) => a.name.localeCompare(b.name));

    renderGrid();
  } catch(e) {
    document.getElementById('hero-grid').innerHTML = '<div class="loading">Failed to load data. Try refreshing.</div>';
  }
}

function renderGrid() {
  const grid = document.getElementById('hero-grid');
  grid.innerHTML = '';
  heroesData.forEach((h, idx) => {
    const tile = document.createElement('div');
    tile.className = 'hero-tile';
    tile.dataset.name = h.name.toLowerCase();
    const imgUrl = h.images?.icon_hero_card || h.images?.icon_image_small || '';
    tile.innerHTML = `<img src="${imgUrl}" alt="${h.name}" loading="lazy"><div class="name">${h.name}</div>`;
    tile.onclick = () => showHero(h, tile);
    grid.appendChild(tile);
  });
}

function showHero(hero, tile) {
  // Toggle active tile
  document.querySelectorAll('.hero-tile.active').forEach(t => t.classList.remove('active'));
  tile.classList.add('active');

  const detail = document.getElementById('hero-detail');
  const imgUrl = hero.images?.icon_hero_card || '';
  const wikiUrl = 'https://deadlock.wiki/' + hero.name.replace(/ /g,'_').replace(/&/g,'%26');

  // Resolve abilities
  const abilities = [];
  const sigs = ['signature1','signature2','signature3','signature4'];
  const slotLabels = ['Ability 1','Ability 2','Ability 3','Ultimate'];
  const slotColors = ['var(--ability-1)','var(--ability-2)','var(--ability-3)','var(--ability-4)'];

  sigs.forEach((sig, i) => {
    const className = hero.items?.[sig];
    if (!className) return;
    const item = itemsByClass[className.toLowerCase()];
    if (!item) return;
    abilities.push({ slot: i+1, label: slotLabels[i], color: slotColors[i], item });
  });

  let tabsHtml = abilities.map((a, i) =>
    `<div class="ability-tab${i===0?' active':''}" data-idx="${i}">
      <span class="tab-slot tab-slot-${a.slot}">(${a.slot})</span>
      ${a.item.name}
    </div>`
  ).join('');

  let detailsHtml = abilities.map((a, i) => renderAbilityDetail(a, i===0)).join('');

  detail.innerHTML = `
    <div class="detail-header">
      <img src="${imgUrl}" alt="${hero.name}">
      <div>
        <div class="hero-title">${hero.name}</div>
      </div>
      <a href="${wikiUrl}" target="_blank" rel="noopener" class="wiki-link">View on Wiki ↗</a>
      <button class="detail-close" onclick="closeDetail()">✕</button>
    </div>
    <div class="ability-tabs">${tabsHtml}</div>
    <div class="ability-panels">${detailsHtml}</div>
  `;

  // Wire up tabs
  detail.querySelectorAll('.ability-tab').forEach(tab => {
    tab.onclick = () => {
      detail.querySelectorAll('.ability-tab').forEach(t => t.classList.remove('active'));
      detail.querySelectorAll('.ability-detail').forEach(d => d.classList.remove('visible'));
      tab.classList.add('active');
      detail.querySelectorAll('.ability-detail')[parseInt(tab.dataset.idx)].classList.add('visible');
    };
  });

  detail.classList.add('visible');
  detail.scrollIntoView({ behavior:'smooth', block:'nearest' });
}

function renderAbilityDetail(ability, visible) {
  const item = ability.item;
  const desc = item.description?.desc || item.description || 'No description available.';
  const imgUrl = item.image || '';

  // Parse properties
  const props = item.properties || {};
  const propKeys = Object.keys(props);

  // Core stats
  let coreHtml = '';
  propKeys.forEach(key => {
    if (!CORE_KEYS.has(key)) return;
    const p = props[key];
    if (!p || p.value === undefined || p.value === null) return;
    const info = CORE_LABELS[key] || {icon:'•', label:key};
    const postfix = p.postfix || '';
    coreHtml += `<div class="core-stat"><span>${info.icon}</span><span class="val">${p.value}</span><span class="unit">${postfix}</span><span class="label">${info.label}</span></div>`;
  });

  // Other properties
  let propsHtml = '';
  propKeys.forEach(key => {
    if (CORE_KEYS.has(key) || SKIP_PROPS.has(key)) return;
    const p = props[key];
    if (!p || p.value === undefined || p.value === null) return;
    if (p.value === 0 && !p.scale_function) return; // Skip zero-value props with no scaling

    const label = p.label || key.replace(/([A-Z])/g,' $1').trim();
    const postfix = p.postfix || '';
    const scale = p.scale_function ? `<span class="prop-scale">×${p.scale_function}</span>` : '';
    const conditional = p.conditional ? ' conditional' : '';
    const prefix = p.prefix || '';

    propsHtml += `<div class="prop-box${conditional}">
      ${scale}
      <div><span class="prop-val">${prefix}${p.value}</span><span class="prop-unit">${postfix}</span></div>
      <div class="prop-label">${label}</div>
    </div>`;
  });

  // Upgrades
  const upgrades = item.upgrades || [];
  let upgradesHtml = '';
  if (upgrades.length > 0) {
    const cards = upgrades.map(u => {
      const cost = u.cost || u.ability_point_cost || '?';
      const desc = u.description || u.desc || '';
      return `<div class="upgrade-card">
        <div class="upgrade-hdr">◆ ${cost}</div>
        <div class="upgrade-body">${desc}</div>
      </div>`;
    }).join('');
    upgradesHtml = `<div class="upgrades-row">${cards}</div>`;
  }

  return `<div class="ability-detail${visible?' visible':''}">
    <div class="ability-head">
      ${imgUrl ? `<img src="${imgUrl}" alt="${item.name}">` : ''}
      <div>
        <div class="ability-title">${item.name}</div>
        <div class="ability-slot-label" style="color:${ability.color}">${ability.label}</div>
      </div>
    </div>
    ${coreHtml ? `<div class="core-stats">${coreHtml}</div>` : ''}
    <div class="ability-desc">${desc}</div>
    ${propsHtml ? `<div class="props-grid">${propsHtml}</div>` : ''}
    ${upgradesHtml}
  </div>`;
}

function closeDetail() {
  document.getElementById('hero-detail').classList.remove('visible');
  document.querySelectorAll('.hero-tile.active').forEach(t => t.classList.remove('active'));
}

// Search filter
document.getElementById('hero-search').addEventListener('input', function() {
  const q = this.value.toLowerCase().trim();
  document.querySelectorAll('.hero-tile').forEach(tile => {
    tile.classList.toggle('hidden', q && !tile.dataset.name.includes(q));
  });
});

init();
</script>
</body>
</html>'''
