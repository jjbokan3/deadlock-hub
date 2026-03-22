"""Generate a styled index page listing all available patch notes.

Scans the patches directory for .html files, optionally reads companion .txt
files to extract hero/item change counts, and generates a visually rich
landing page matching the patch notes dark theme.

Called automatically by the watcher after each new patch, or manually:
    python index_generator.py --dir ./site/deadlock
"""
from __future__ import annotations
import argparse
import os
import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DEFAULT_DIR = "./site/deadlock"


def _parse_patch_info(filename: str, patches_dir: str) -> dict:
    """Extract metadata from a patch file and its companion .txt."""
    stem = os.path.splitext(filename)[0]
    filepath = os.path.join(patches_dir, filename)
    size_kb = os.path.getsize(filepath) / 1024

    date_display = stem.replace("_", " ").title()
    sort_key = "0"
    date_obj = None

    match = re.search(r'(\d{2})_(\d{2})_(\d{4})', stem)
    if match:
        m, d, y = match.groups()
        sort_key = f"{y}{m}{d}"
        try:
            date_obj = datetime(int(y), int(m), int(d))
        except ValueError:
            pass

    if not date_obj:
        match = re.match(r'(\d{4})-(\d{2})-(\d{2})', stem)
        if match:
            y, m, d = match.groups()
            sort_key = f"{y}{m}{d}"
            try:
                date_obj = datetime(int(y), int(m), int(d))
            except ValueError:
                pass

    if date_obj:
        date_display = date_obj.strftime("%B %d, %Y")
        date_short = date_obj.strftime("%b %d")
        date_weekday = date_obj.strftime("%A")
    else:
        date_short = stem[:10]
        date_weekday = ""

    # Read companion .txt for stats
    txt_path = os.path.join(patches_dir, stem + ".txt")
    heroes = set()
    total_lines = 0

    if os.path.exists(txt_path):
        try:
            with open(txt_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line.startswith("- "):
                        continue
                    total_lines += 1
                    colon_idx = line.find(":", 2)
                    if colon_idx > 0:
                        name = line[2:colon_idx].strip()
                        if 2 < len(name) < 30 and name[0].isupper():
                            if any(c.islower() for c in name[1:]) or "&" in name:
                                heroes.add(name)
        except Exception:
            pass

    return {
        "filename": filename,
        "title": f"{date_display} Update" if date_obj else stem.replace("_", " ").title(),
        "date_display": date_display,
        "date_short": date_short,
        "date_weekday": date_weekday,
        "sort_key": sort_key,
        "size": f"{size_kb:.0f}",
        "heroes": sorted(heroes)[:8],
        "hero_count": len(heroes),
        "total_lines": total_lines,
    }


def generate_index(patches_dir: str = DEFAULT_DIR) -> str:
    entries = []
    if not os.path.isdir(patches_dir):
        return _render_page([])
    for f in os.listdir(patches_dir):
        if f.endswith(".html") and f != "index.html":
            entries.append(_parse_patch_info(f, patches_dir))
    entries.sort(key=lambda x: x["sort_key"], reverse=True)
    return _render_page(entries)


def write_index(patches_dir: str = DEFAULT_DIR):
    html = generate_index(patches_dir)
    path = os.path.join(patches_dir, "index.html")
    os.makedirs(patches_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info(f"Index written: {path} ({len(html)} bytes)")
    return path


def _render_page(patches: list[dict]) -> str:
    if not patches:
        cards = '<div class="empty">No patch notes generated yet.<br><span>Run the watcher or process a patch to get started.</span></div>'
    else:
        card_parts = []
        for i, p in enumerate(patches):
            is_latest = i == 0
            lc = " latest" if is_latest else ""
            lb = '<div class="badge">LATEST</div>' if is_latest else ""

            hero_pills = ""
            if p["heroes"]:
                pills = "".join(f'<span class="pill">{h}</span>' for h in p["heroes"][:6])
                extra = f'<span class="pill pill-more">+{p["hero_count"] - 6}</span>' if p["hero_count"] > 6 else ""
                hero_pills = f'<div class="heroes">{pills}{extra}</div>'

            stat_parts = []
            if p["hero_count"]:
                stat_parts.append(f'<span class="stat"><span class="stat-num">{p["hero_count"]}</span> heroes</span>')
            if p["total_lines"]:
                stat_parts.append(f'<span class="stat"><span class="stat-num">{p["total_lines"]}</span> changes</span>')
            stat_parts.append(f'<span class="stat">{p["size"]} KB</span>')
            stats = f'<div class="stats">{"".join(stat_parts)}</div>'

            card_parts.append(f'''
    <a href="{p["filename"]}" class="card{lc}">
      {lb}
      <div class="card-header">
        <div class="card-date">
          <div class="date-big">{p["date_short"]}</div>
          <div class="date-sub">{p["date_weekday"]}</div>
        </div>
        <div class="card-info">
          <div class="card-title">{p["title"]}</div>
          {stats}
        </div>
        <div class="card-arrow">→</div>
      </div>
      {hero_pills}
    </a>''')
        cards = "\n".join(card_parts)

    return INDEX_TEMPLATE.format(patch_count=len(patches), cards=cards)


INDEX_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Deadlock Patch Notes</title>
<link rel="icon" href="/deadlock/deadlock_icon.ico" type="image/x-icon">
<link href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;500;600;700&family=Chakra+Petch:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg:#0a0b0f;--bg-card:#12141c;--bg-hover:#181b26;
    --border:#252a38;--border-hover:#3a4158;
    --text:#e8eaf0;--dim:#8b90a5;--faint:#565b72;
    --accent:#ff6b2c;--accent-dim:#ff6b2c25;
  }}
  *{{margin:0;padding:0;box-sizing:border-box}}
  body{{background:var(--bg);color:var(--text);font-family:'Chakra Petch',sans-serif;min-height:100vh;line-height:1.6}}
  body::before{{content:'';position:fixed;inset:0;background:radial-gradient(ellipse at 15% 0%,#ff6b2c06 0%,transparent 50%),radial-gradient(ellipse at 85% 100%,#3ecfff05 0%,transparent 50%);pointer-events:none}}
  .container{{max-width:860px;margin:0 auto;padding:60px 24px 100px;position:relative;z-index:1}}
  header{{text-align:center;margin-bottom:56px}}
  .logo{{font-family:'JetBrains Mono',monospace;font-size:11px;letter-spacing:3px;text-transform:uppercase;color:var(--accent);background:var(--accent-dim);padding:6px 18px;border-radius:4px;display:inline-block;margin-bottom:24px;border:1px solid #ff6b2c30}}
  h1{{font-family:'Rajdhani',sans-serif;font-size:clamp(40px,6vw,64px);font-weight:700;letter-spacing:3px;text-transform:uppercase;line-height:1;background:linear-gradient(135deg,#e8eaf0 30%,var(--accent) 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}}
  .subtitle{{color:var(--dim);margin-top:12px;font-size:15px}}
  .count{{font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--faint);letter-spacing:1.5px;margin-bottom:24px}}
  .cards{{display:flex;flex-direction:column;gap:12px}}
  .card{{display:block;background:var(--bg-card);border:1px solid var(--border);border-radius:14px;padding:22px 26px 18px;text-decoration:none;color:var(--text);transition:all 0.25s ease;position:relative;overflow:hidden}}
  .card:hover{{border-color:var(--border-hover);background:var(--bg-hover);transform:translateY(-2px);box-shadow:0 8px 30px #00000040}}
  .card.latest{{border-color:#ff6b2c35;background:linear-gradient(135deg,#12141c 0%,#1a1218 100%)}}
  .card.latest:hover{{border-color:var(--accent)}}
  .badge{{position:absolute;top:14px;right:16px;font-family:'JetBrains Mono',monospace;font-size:9px;letter-spacing:2px;padding:3px 10px;border-radius:4px;background:var(--accent-dim);color:var(--accent);border:1px solid #ff6b2c40}}
  .card-header{{display:flex;align-items:center;gap:20px}}
  .card-date{{flex-shrink:0;text-align:center;min-width:70px;padding-right:20px;border-right:1px solid #ffffff0a}}
  .date-big{{font-family:'Rajdhani',sans-serif;font-size:26px;font-weight:700;letter-spacing:0.5px;line-height:1.1}}
  .date-sub{{font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--faint);letter-spacing:1px;text-transform:uppercase}}
  .card-info{{flex:1;min-width:0}}
  .card-title{{font-family:'Rajdhani',sans-serif;font-size:22px;font-weight:700;letter-spacing:0.5px;line-height:1.3}}
  .stats{{display:flex;gap:16px;margin-top:6px;flex-wrap:wrap}}
  .stat{{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--faint);letter-spacing:0.5px}}
  .stat-num{{color:var(--dim);font-weight:500}}
  .card-arrow{{font-size:22px;color:var(--faint);flex-shrink:0;transition:all 0.25s;align-self:center}}
  .card:hover .card-arrow{{color:var(--accent);transform:translateX(5px)}}
  .heroes{{display:flex;flex-wrap:wrap;gap:6px;margin-top:14px;padding-top:14px;border-top:1px solid #ffffff06}}
  .pill{{font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:0.5px;padding:3px 10px;border-radius:20px;background:#ffffff08;color:var(--dim);border:1px solid #ffffff0a}}
  .pill-more{{background:var(--accent-dim);color:var(--accent);border-color:#ff6b2c30}}
  .empty{{text-align:center;padding:60px 20px;color:var(--faint);font-size:16px}}
  .empty span{{font-size:13px}}
  .back{{display:inline-flex;align-items:center;gap:6px;font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--faint);text-decoration:none;margin-bottom:32px;transition:color 0.2s;letter-spacing:0.5px}}
  .back:hover{{color:var(--dim)}}
  @media(max-width:640px){{.container{{padding:40px 16px 60px}}.card{{padding:18px 18px 14px}}.card-date{{min-width:56px;padding-right:14px}}.date-big{{font-size:22px}}.card-title{{font-size:18px}}.card-header{{gap:14px}}}}
</style>
</head>
<body>
<div class="container">
  <a href="/" class="back">← all games</a>
  <header>
    <div class="logo">games.josephbokan.io/deadlock</div>
    <h1>Deadlock</h1>
    <p class="subtitle">Auto-generated balance breakdowns with nerf/buff analysis</p>
  </header>
  <div class="count">{patch_count} UPDATE(S)</div>
  <div class="cards">
    {cards}
  </div>
</div>
</body>
</html>'''


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate patch notes index page.")
    parser.add_argument("--dir", default=DEFAULT_DIR, help="Patches directory")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    write_index(args.dir)
