"""Generate the Deadlock hub landing page at site/deadlock/index.html.

Links to the updates listing and hero browser.
"""
from __future__ import annotations
import os
import logging

logger = logging.getLogger(__name__)


def write_hub_page(deadlock_dir: str):
    """Write the hub page to deadlock_dir/index.html."""
    os.makedirs(deadlock_dir, exist_ok=True)
    path = os.path.join(deadlock_dir, "index.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(HUB_TEMPLATE)
    logger.info(f"Hub page written: {path}")
    return path


HUB_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Deadlock — games.josephbokan.io</title>
<link rel="icon" href="/deadlock/deadlock_icon.ico" type="image/x-icon">
<link href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;500;600;700&family=Chakra+Petch:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root { --bg:#0a0b0f; --card:#12141c; --card-hover:#181b26; --border:#252a38; --border-hover:#3a4158; --text:#e8eaf0; --dim:#8b90a5; --faint:#565b72; --accent:#ff6b2c; --accent-dim:#ff6b2c25; }
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background:var(--bg); color:var(--text); font-family:'Chakra Petch',sans-serif; min-height:100vh; }
  body::before { content:''; position:fixed; inset:0; background:radial-gradient(ellipse at 20% 0%,#ff6b2c08 0%,transparent 50%),radial-gradient(ellipse at 80% 100%,#3ecfff06 0%,transparent 50%); pointer-events:none; }
  .container { max-width:700px; margin:0 auto; padding:80px 24px 100px; position:relative; z-index:1; }
  .back { display:inline-flex; align-items:center; gap:6px; font-family:'JetBrains Mono',monospace; font-size:12px; color:var(--faint); text-decoration:none; margin-bottom:40px; transition:color 0.2s; letter-spacing:0.5px; }
  .back:hover { color:var(--dim); }
  header { text-align:center; margin-bottom:56px; }
  .logo { font-family:'JetBrains Mono',monospace; font-size:11px; letter-spacing:3px; text-transform:uppercase; color:var(--accent); background:var(--accent-dim); padding:6px 18px; border-radius:4px; display:inline-block; margin-bottom:24px; border:1px solid #ff6b2c30; }
  h1 { font-family:'Rajdhani',sans-serif; font-size:clamp(48px,7vw,72px); font-weight:700; letter-spacing:3px; text-transform:uppercase; line-height:1; background:linear-gradient(135deg,#e8eaf0 30%,var(--accent) 100%); -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; }
  .subtitle { color:var(--dim); margin-top:12px; font-size:15px; }
  .cards { display:flex; flex-direction:column; gap:16px; }
  .card { display:flex; align-items:center; justify-content:space-between; padding:28px 32px; background:var(--card); border:1px solid var(--border); border-radius:14px; text-decoration:none; color:var(--text); transition:all 0.25s ease; }
  .card:hover { border-color:var(--border-hover); background:var(--card-hover); transform:translateY(-2px); box-shadow:0 8px 30px #00000040; }
  .card-left { display:flex; align-items:center; gap:18px; }
  .card-icon { width:48px; height:48px; border-radius:10px; display:flex; align-items:center; justify-content:center; font-size:22px; flex-shrink:0; }
  .card-icon.updates { background:#ff6b2c20; color:var(--accent); border:1px solid #ff6b2c35; }
  .card-icon.heroes { background:#3ecfff20; color:#3ecfff; border:1px solid #3ecfff35; }
  .card-title { font-family:'Rajdhani',sans-serif; font-size:24px; font-weight:700; letter-spacing:1px; text-transform:uppercase; }
  .card-desc { font-size:13px; color:var(--dim); margin-top:2px; }
  .card-arrow { font-size:22px; color:var(--faint); transition:all 0.25s; }
  .card:hover .card-arrow { color:var(--accent); transform:translateX(5px); }
  .github { position:fixed; top:20px; right:20px; display:flex; align-items:center; gap:8px; font-family:'JetBrains Mono',monospace; font-size:11px; color:var(--faint); text-decoration:none; background:var(--card); border:1px solid var(--border); padding:8px 14px; border-radius:8px; transition:all 0.2s; z-index:10; }
  .github:hover { color:var(--accent); border-color:var(--accent); }
  .github svg { width:16px; height:16px; fill:currentColor; }
  @media(max-width:640px) { .container { padding:50px 16px 60px; } .card { padding:20px 20px; } .card-icon { width:40px; height:40px; font-size:18px; } .card-title { font-size:20px; } .github { top:12px; right:12px; padding:6px 10px; font-size:10px; } }
</style>
</head>
<body>
<a href="https://github.com/jjbokan3/deadlock-hub" target="_blank" rel="noopener" class="github">
  <svg viewBox="0 0 16 16"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>
  GitHub
</a>
<div class="container">
  <a href="/" class="back">← all games</a>
  <header>
    <div class="logo">games.josephbokan.io/deadlock</div>
    <h1>Deadlock</h1>
    <p class="subtitle">Game tools, patch analysis & hero data</p>
  </header>
  <div class="cards">
    <a href="/deadlock/updates/" class="card">
      <div class="card-left">
        <div class="card-icon updates">📋</div>
        <div>
          <div class="card-title">Patch Notes</div>
          <div class="card-desc">Auto-generated balance breakdowns with buff/nerf analysis</div>
        </div>
      </div>
      <span class="card-arrow">→</span>
    </a>
    <a href="/deadlock/heroes.html" class="card">
      <div class="card-left">
        <div class="card-icon heroes">⚔</div>
        <div>
          <div class="card-title">Hero Browser</div>
          <div class="card-desc">Explore all heroes, abilities, stats & scaling</div>
        </div>
      </div>
      <span class="card-arrow">→</span>
    </a>
  </div>
</div>
</body>
</html>'''
