#!/usr/bin/env python3
"""Watch the Deadlock changelog forum for new patch notes and auto-generate HTML.

The Deadlock forums run on XenForo, which exposes RSS feeds per forum section.
The changelog section feed is at:
    https://forums.playdeadlock.com/forums/changelog.10/index.rss

Usage:
    # Poll every 5 minutes, auto-run with heuristic ratings
    python watcher.py

    # Poll every 10 minutes, use Claude for ratings
    python watcher.py --interval 600 --llm claude

    # Single check (no loop), useful for cron/Task Scheduler
    python watcher.py --once

    # Custom output directory
    python watcher.py --output-dir ./patches

Automation options:
    1. Run this script in a loop (default behavior)
    2. Run with --once via cron (Linux) or Task Scheduler (Windows)
    3. Use a service like IFTTT/Zapier to watch the RSS and trigger a webhook

Cron example (check every 5 minutes):
    */5 * * * * cd /path/to/deadlock-patch-tool && python watcher.py --once --llm heuristic

Windows Task Scheduler:
    Action: Start a program
    Program: python
    Arguments: watcher.py --once --llm heuristic
    Start in: C:\\path\\to\\deadlock-patch-tool
"""
from __future__ import annotations
import argparse
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from html import unescape
from xml.etree import ElementTree

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("watcher")

CHANGELOG_RSS = "https://forums.playdeadlock.com/forums/changelog.10/index.rss"
SEEN_FILE = ".cache/seen_patches.json"
DEFAULT_OUTPUT_DIR = "./site/deadlock/updates"
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "deadlock-patch-1e9559743277")
NTFY_URL = os.environ.get("NTFY_URL", "https://ntfy.sh")
SITE_BASE_URL = "https://games.josephbokan.io/deadlock/updates"
NOTIFICATIONS_ENABLED = True  # Set to False via --no-notify


def fetch_rss(url: str = CHANGELOG_RSS) -> list[dict]:
    """Fetch and parse the RSS feed. Returns list of {title, link, description, pub_date}."""
    resp = requests.get(url, timeout=30, headers={"User-Agent": "DeadlockPatchTool/1.0"})
    resp.raise_for_status()

    root = ElementTree.fromstring(resp.content)
    entries = []

    for item in root.iter("item"):
        title = item.findtext("title", "").strip()
        link = item.findtext("link", "").strip()
        description = item.findtext("description", "").strip()
        pub_date = item.findtext("pubDate", "").strip()

        if title and link:
            entries.append({
                "title": title,
                "link": link,
                "description": description,
                "pub_date": pub_date,
                "id": hashlib.md5(link.encode()).hexdigest()[:12],
            })

    return entries


def load_seen() -> dict[str, str]:
    """Load map of already-processed patch IDs to their content hashes.

    Migrates from the old format (list of IDs) to the new format (dict of ID → hash).
    """
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, encoding="utf-8") as f:
            data = json.load(f)
        # Migrate from old list format to new dict format
        if isinstance(data, list):
            return {pid: "" for pid in data}
        return data
    return {}


def save_seen(seen: dict[str, str]):
    """Persist the map of processed patch IDs → content hashes."""
    os.makedirs(os.path.dirname(SEEN_FILE), exist_ok=True)
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(seen, f, indent=2)


def fetch_patch_text(url: str) -> str:
    """Fetch a forum thread and extract the patch notes text from the first post."""
    from feed import fetch_patch_notes
    return fetch_patch_notes(url)


def run_pipeline(patch_text: str, title: str, output_dir: str, llm: str, extra_args: list[str]):
    """Run main.py on the extracted patch text."""
    os.makedirs(output_dir, exist_ok=True)

    # Create a safe filename from the title (title already contains the date)
    filename = re.sub(r'[^\w\-]', '_', title.lower()).strip('_')

    txt_path = os.path.join(output_dir, f"{filename}.txt")
    html_path = os.path.join(output_dir, f"{filename}.html")

    # Write the raw text
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(patch_text)

    # Run the main pipeline
    cmd = [
        sys.executable, "main.py",
        "--input", txt_path,
        "--output", html_path,
        "--llm", llm,
        "--title", title,
        "--yes",  # skip confirmation
        *extra_args,
    ]

    logger.info(f"Running pipeline: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        logger.info(f"Generated: {html_path}")
        if result.stderr:
            # Show pipeline output (progress info, warnings, etc.)
            for line in result.stderr.strip().splitlines():
                logger.info(f"  | {line}")
    else:
        logger.error(f"Pipeline failed (exit code {result.returncode}):\n{result.stderr}")

    return html_path if result.returncode == 0 else None


def _content_hash(text: str) -> str:
    """Hash patch text content to detect changes from new posts."""
    return hashlib.md5(text.encode()).hexdigest()


def _notify(title: str, message: str, url: str = "", updated: bool = False):
    """Send a push notification via ntfy.sh."""
    if not NOTIFICATIONS_ENABLED:
        logger.info(f"Notification suppressed (--no-notify): {title}")
        return
    if not NTFY_TOPIC:
        return
    try:
        headers = {
            "Title": title,
            "Priority": "4" if not updated else "3",
            "Tags": "video_game,deadlock",
        }
        if url:
            headers["Click"] = url
            headers["Actions"] = f"view, Open Patch Notes, {url}"
        requests.post(
            f"{NTFY_URL}/{NTFY_TOPIC}",
            data=message.encode("utf-8"),
            headers=headers,
            timeout=10,
        )
        logger.info(f"Notification sent: {title}")
    except Exception as e:
        logger.warning(f"Failed to send notification: {e}")


def check_and_process(output_dir: str, llm: str, extra_args: list[str], max_new: int = 0) -> int:
    """Check RSS for new or updated patches and process them. Returns count processed.

    Detects both new threads and updated threads (new follow-up posts by Yoshi).
    If max_new > 0, only process at most that many of the newest unseen entries.
    """
    try:
        entries = fetch_rss()
    except Exception as e:
        logger.error(f"Failed to fetch RSS: {e}")
        return 0

    seen = load_seen()
    new_count = 0

    # Split into unseen (brand new threads) and seen (check for updates)
    unseen = [e for e in entries if e["id"] not in seen]
    if max_new > 0 and len(unseen) > max_new:
        # Mark the older ones as seen without processing
        for entry in unseen[max_new:]:
            logger.info(f"Skipping older patch (cold start): {entry['title']}")
            seen[entry["id"]] = ""
        save_seen(seen)
        unseen = unseen[:max_new]

    # Process new threads
    for entry in unseen:
        if entry["id"] in seen:
            continue

        logger.info(f"New patch detected: {entry['title']}")
        logger.info(f"  URL: {entry['link']}")

        try:
            patch_text = fetch_patch_text(entry["link"])
        except Exception as e:
            logger.error(f"Failed to fetch patch text: {e}")
            seen[entry["id"]] = ""
            save_seen(seen)
            continue

        if not patch_text.strip():
            logger.warning("Extracted empty patch text, skipping")
            seen[entry["id"]] = ""
            save_seen(seen)
            continue

        line_count = len(patch_text.strip().splitlines())
        logger.info(f"  Extracted {line_count} lines of patch notes")

        result = run_pipeline(patch_text, entry["title"], output_dir, llm, extra_args)

        if result:
            # Build URL from output filename
            fname = os.path.basename(result)
            page_url = f"{SITE_BASE_URL}/{fname}"
            line_count = len(patch_text.strip().splitlines())
            _notify(
                f"New Patch: {entry['title']}",
                f"{line_count} lines of patch notes processed and published.",
                url=page_url,
            )

        seen[entry["id"]] = _content_hash(patch_text)
        save_seen(seen)
        new_count += 1

    # Check recently-seen threads for updated content (new follow-up posts).
    # Only check threads from the current RSS feed (i.e. recent threads).
    for entry in entries:
        if entry["id"] not in seen:
            continue  # will be handled above on next iteration
        old_hash = seen[entry["id"]]
        if not old_hash:
            # Migrated from old format — no hash stored yet, fetch to establish baseline
            try:
                patch_text = fetch_patch_text(entry["link"])
                seen[entry["id"]] = _content_hash(patch_text) if patch_text.strip() else ""
                save_seen(seen)
            except Exception:
                pass
            continue

        # Re-fetch and compare
        try:
            patch_text = fetch_patch_text(entry["link"])
        except Exception as e:
            logger.error(f"Failed to re-fetch {entry['title']}: {e}")
            continue

        if not patch_text.strip():
            continue

        new_hash = _content_hash(patch_text)
        if new_hash == old_hash:
            continue

        logger.info(f"Updated content detected: {entry['title']}")
        line_count = len(patch_text.strip().splitlines())
        logger.info(f"  Now {line_count} lines (was different)")

        result = run_pipeline(patch_text, entry["title"], output_dir, llm, extra_args)

        if result:
            fname = os.path.basename(result)
            page_url = f"{SITE_BASE_URL}/{fname}"
            _notify(
                f"Updated: {entry['title']}",
                f"Follow-up post detected. Page regenerated with {line_count} lines.",
                url=page_url,
                updated=True,
            )

        seen[entry["id"]] = new_hash
        save_seen(seen)
        new_count += 1

    if new_count == 0:
        logger.info("No new patches found")
    else:
        # Regenerate the index page
        try:
            from index_generator import write_index
            write_index(output_dir)
            logger.info(f"Index regenerated ({new_count} new/updated patch(es))")
        except Exception as e:
            logger.warning(f"Failed to regenerate index: {e}")

    return new_count


def main():
    global CHANGELOG_RSS
    parser = argparse.ArgumentParser(
        description="Watch Deadlock changelog for new patch notes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=300,
        help="Seconds between RSS checks (default: 300 = 5 min)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Check once and exit (for cron/Task Scheduler)",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory for generated files (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--llm",
        default="heuristic",
        choices=["claude", "openai", "ollama", "heuristic"],
        help="LLM provider passed to main.py (default: heuristic)",
    )
    parser.add_argument(
        "--rss-url",
        default=CHANGELOG_RSS,
        help="RSS feed URL to watch",
    )
    parser.add_argument(
        "--no-notify",
        action="store_true",
        help="Suppress push notifications (for dashboard/debug use)",
    )

    args, extra = parser.parse_known_args()

    global NOTIFICATIONS_ENABLED
    if args.no_notify:
        NOTIFICATIONS_ENABLED = False
        logger.info("Notifications disabled (--no-notify)")

    CHANGELOG_RSS = args.rss_url

    # On cold start (no cache), limit to 3 most recent patches
    cold_start = not os.path.exists(SEEN_FILE)
    max_new = 3 if cold_start else 0
    if cold_start:
        logger.info("No seen-patches cache found — will process at most 3 most recent patches")

    if args.once:
        count = check_and_process(args.output_dir, args.llm, extra, max_new=max_new)
        sys.exit(0 if count >= 0 else 1)

    # Polling loop
    logger.info(f"Watching {CHANGELOG_RSS}")
    logger.info(f"Polling every {args.interval}s. Press Ctrl+C to stop.")
    logger.info(f"Output directory: {os.path.abspath(args.output_dir)}")

    try:
        first_run = True
        while True:
            check_and_process(args.output_dir, args.llm, extra, max_new=max_new if first_run else 0)
            first_run = False
            time.sleep(args.interval)
    except KeyboardInterrupt:
        logger.info("Stopped.")


if __name__ == "__main__":
    main()
