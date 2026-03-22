"""Fetch patch notes from the Deadlock changelog RSS feed and forum pages."""
from __future__ import annotations
import re
import logging
from html import unescape
from xml.etree import ElementTree

import requests

logger = logging.getLogger(__name__)

CHANGELOG_RSS = "https://forums.playdeadlock.com/forums/changelog.10/index.rss"
NS = {
    "content": "http://purl.org/rss/1.0/modules/content/",
}


def fetch_latest_url(rss_url: str = CHANGELOG_RSS) -> tuple[str, str]:
    """Fetch the RSS feed and return (title, thread_url) for the most recent entry."""
    logger.info(f"Fetching RSS feed: {rss_url}")
    resp = requests.get(rss_url, timeout=30, headers={"User-Agent": "DeadlockPatchTool/1.0"})
    resp.raise_for_status()

    root = ElementTree.fromstring(resp.content)
    first_item = root.find(".//item")
    if first_item is None:
        raise RuntimeError("No items found in RSS feed")

    title = first_item.findtext("title", "").strip()
    link = first_item.findtext("link", "").strip()
    logger.info(f"Latest patch: {title}")
    logger.info(f"Thread URL: {link}")
    return title, link


def extract_from_html(html: str) -> str:
    """Extract patch note lines from a forum thread HTML page.

    The Deadlock forums (XenForo) wrap the first post in:
        <div class="bbWrapper">...</div>
    Lines are separated by <br /> tags. Patch note lines start with '- '.
    Section headers are wrapped in <b>[ Section ]</b>.
    Indented lines use <div style="margin-left: 20px">.
    """
    # Find the first bbWrapper (the OP's post content)
    match = re.search(r'<div class="bbWrapper">(.*?)</div>\s*(?:</div>|<div class="js-selectToQuoteEnd">)',
                       html, re.DOTALL)
    if not match:
        # Fallback: find any bbWrapper
        match = re.search(r'<div class="bbWrapper">(.*?)</div>', html, re.DOTALL)

    if not match:
        logger.warning("Could not find bbWrapper in HTML")
        return ""

    raw = match.group(1)

    # Replace <br /> with newlines
    text = re.sub(r'<br\s*/?>', '\n', raw)

    # Handle indented lines (XenForo uses margin-left divs)
    text = re.sub(r'<div[^>]*style="margin-left:\s*\d+px"[^>]*>', '  ', text)

    # Strip remaining HTML tags
    text = re.sub(r'<[^>]+>', '', text)

    # Decode HTML entities
    text = unescape(text)

    # Filter to patch note lines
    lines = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Keep lines that start with "- " or "* " (patch notes use both formats)
        # Also keep section headers like "[ General ]"
        if line.startswith("- ") or line.startswith("* ") or line.startswith("["):
            lines.append(line)

    return "\n".join(lines)


def fetch_patch_notes(thread_url: str) -> str:
    """Fetch a forum thread page and extract the patch notes text."""
    logger.info(f"Fetching thread: {thread_url}")
    resp = requests.get(thread_url, timeout=30, headers={"User-Agent": "DeadlockPatchTool/1.0"})
    resp.raise_for_status()
    return extract_from_html(resp.text)


def fetch_latest_patch_notes(rss_url: str = CHANGELOG_RSS) -> tuple[str, str]:
    """Convenience: fetch RSS → get latest thread → extract notes.

    Returns (title, patch_notes_text).
    """
    title, url = fetch_latest_url(rss_url)
    text = fetch_patch_notes(url)
    line_count = len(text.strip().splitlines()) if text else 0
    logger.info(f"Extracted {line_count} lines from '{title}'")
    return title, text
