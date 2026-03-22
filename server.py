#!/usr/bin/env python3
"""Serve the site directory as a static website.

Usage:
    python server.py                        # serve on port 8080
    python server.py --port 3000            # custom port
    python server.py --dir ./site           # custom root directory

Directory structure:
    site/
    ├── index.html              ← games.josephbokan.io
    ├── deadlock/
    │   ├── index.html          ← games.josephbokan.io/deadlock/
    │   ├── 03_21_2026.html
    │   └── ...
    └── (other games)/

Point your Cloudflare tunnel to http://localhost:8080
"""
from __future__ import annotations
import argparse
import logging
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler
from functools import partial

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("server")

DEFAULT_DIR = "./site"
DEFAULT_PORT = 8080


class SiteHandler(SimpleHTTPRequestHandler):
    """Handler with cache headers and clean logging."""

    def end_headers(self):
        self.send_header("Cache-Control", "public, max-age=60")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def log_message(self, format, *args):
        logger.info(f"{self.client_address[0]} - {format % args}")


def ensure_site_root(site_dir: str):
    """Create the site root index if it doesn't exist."""
    os.makedirs(site_dir, exist_ok=True)
    root_index = os.path.join(site_dir, "index.html")
    if not os.path.exists(root_index):
        with open(root_index, "w", encoding="utf-8") as f:
            f.write(SITE_ROOT_TEMPLATE)
        logger.info(f"Created site root: {root_index}")


SITE_ROOT_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Game Patch Notes — games.josephbokan.io</title>
<link href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;500;600;700&family=Chakra+Petch:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root { --bg: #0a0b0f; --card: #12141c; --border: #252a38; --text: #e8eaf0; --dim: #8b90a5; --accent: #ff6b2c; }
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background:var(--bg); color:var(--text); font-family:'Chakra Petch',sans-serif; min-height:100vh; display:flex; align-items:center; justify-content:center; }
  .container { max-width:500px; padding:40px 24px; text-align:center; }
  h1 { font-family:'Rajdhani',sans-serif; font-size:42px; font-weight:700; letter-spacing:2px; text-transform:uppercase; margin-bottom:8px; }
  p { color:var(--dim); margin-bottom:40px; }
  .games { display:flex; flex-direction:column; gap:12px; }
  a { display:flex; align-items:center; justify-content:space-between; padding:20px 24px; background:var(--card); border:1px solid var(--border); border-radius:12px; text-decoration:none; color:var(--text); font-family:'Rajdhani',sans-serif; font-size:24px; font-weight:700; letter-spacing:1px; text-transform:uppercase; transition:all 0.2s; }
  a:hover { border-color:#3a4158; transform:translateX(4px); }
  .arrow { color:var(--dim); transition:color 0.2s; }
  a:hover .arrow { color:var(--accent); }
</style>
</head>
<body>
<div class="container">
  <h1>Game Patch Notes</h1>
  <p>games.josephbokan.io</p>
  <div class="games">
    <a href="/deadlock/">Deadlock <span class="arrow">→</span></a>
  </div>
</div>
</body>
</html>'''


def main():
    parser = argparse.ArgumentParser(description="Serve game patch notes site.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Port (default: {DEFAULT_PORT})")
    parser.add_argument("--dir", default=DEFAULT_DIR, help=f"Site root directory (default: {DEFAULT_DIR})")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    args = parser.parse_args()

    site_dir = os.path.abspath(args.dir)
    ensure_site_root(site_dir)

    # Ensure deadlock subdirectory structure exists
    dl_dir = os.path.join(site_dir, "deadlock")
    updates_dir = os.path.join(dl_dir, "updates")
    os.makedirs(updates_dir, exist_ok=True)

    # Generate deadlock hub page if needed
    dl_index = os.path.join(dl_dir, "index.html")
    if not os.path.exists(dl_index):
        try:
            from hub_generator import write_hub_page
            write_hub_page(dl_dir)
        except Exception as e:
            logger.warning(f"Could not generate deadlock hub: {e}")

    # Generate updates index if needed
    updates_index = os.path.join(updates_dir, "index.html")
    if not os.path.exists(updates_index):
        try:
            from index_generator import write_index
            write_index(updates_dir)
        except Exception as e:
            logger.warning(f"Could not generate updates index: {e}")

    # Generate heroes page if needed
    heroes_page = os.path.join(dl_dir, "heroes.html")
    if not os.path.exists(heroes_page):
        try:
            from hero_browser import write_heroes_page
            write_heroes_page(dl_dir)
        except Exception as e:
            logger.warning(f"Could not generate heroes page: {e}")

    handler = partial(SiteHandler, directory=site_dir)

    class ReusableHTTPServer(HTTPServer):
        allow_reuse_address = True

    server = ReusableHTTPServer((args.host, args.port), handler)

    logger.info(f"Serving {site_dir}")
    logger.info(f"  Root:     http://localhost:{args.port}/")
    logger.info(f"  Deadlock: http://localhost:{args.port}/deadlock/")
    logger.info(f"Point Cloudflare tunnel (games.josephbokan.io) → http://localhost:{args.port}")
    logger.info("Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Stopped.")
        server.server_close()


if __name__ == "__main__":
    main()
