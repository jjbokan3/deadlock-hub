"""Fetch patch notes from the Deadlock changelog RSS feed and forum pages.

Supports two HTML formats:
1. XenForo forum posts (forums.playdeadlock.com) — bbWrapper divs
2. Steam news pages (store.steampowered.com/news) — EventDetailsBody div

Sometimes Yoshi's forum post contains a link to a Steam news page with the full
patch notes, while the forum posts themselves only have follow-up hotfix changes.
"""
from __future__ import annotations
import re
import logging
from html import unescape
from xml.etree import ElementTree

import requests

logger = logging.getLogger(__name__)

CHANGELOG_RSS = "https://forums.playdeadlock.com/forums/changelog.10/index.rss"
STEAM_NEWS_PATTERN = re.compile(
    r'https?://store\.steampowered\.com/news/app/1422450/view/\d+',
)
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


def _extract_bbwrapper(raw: str) -> list[str]:
    """Extract patch note lines from a single bbWrapper HTML block."""
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

    return lines


def _extract_steam_urls(html: str) -> list[str]:
    """Find Steam news URLs in forum page HTML (typically in Yoshi's first post)."""
    urls = STEAM_NEWS_PATTERN.findall(html)
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique.append(u)
    return unique


def _extract_steam_news(html: str) -> list[str]:
    """Extract patch note lines from a Steam news page.

    Steam news pages embed patch content as BBCode inside a JSON object in the
    page HTML. The JSON is HTML-entity-encoded, and the body field contains
    BBCode tags like [p], [b], [u], [h1]-[h3], [list], [*].
    Closing tags use forward slash: [/tag]. HTML entities like &amp; are used.
    """
    # Strategy 1: Extract BBCode body from embedded JSON.
    # The JSON is HTML-entity-encoded in the page (&quot; for ", etc.)
    # so we decode entities first, then extract the body field.
    decoded = unescape(html)
    body_match = re.search(
        r'"announcement_body"\s*:\s*\{[^}]*?"body"\s*:\s*"((?:[^"\\]|\\.)*)"',
        decoded
    )
    if body_match:
        bbcode = body_match.group(1)
        return _parse_steam_bbcode(bbcode)

    # Strategy 2: Try EventDetailsBody div (client-side rendered, may work with
    # some Steam page variants)
    body_match = re.search(
        r'<div[^>]*class="[^"]*EventDetailsBody[^"]*"[^>]*>(.*?)</div>\s*</div>',
        html, re.DOTALL
    )
    if not body_match:
        body_match = re.search(
            r'<div[^>]*class="[^"]*EventDetailsBody[^"]*"[^>]*>(.*)',
            html, re.DOTALL
        )
    if body_match:
        return _parse_steam_html(body_match.group(1))

    logger.warning("Could not find patch content in Steam news page")
    return []


def _parse_steam_bbcode(bbcode: str) -> list[str]:
    r"""Parse Steam BBCode body string into patch note lines.

    The body uses BBCode like [p], [b], [u], [h1], [list], [*].
    Closing tags are escaped as [\/tag]. Literal brackets use \\.
    """
    text = bbcode

    # Unescape JSON string escapes (order matters: \\ first to avoid double-unescape)
    text = text.replace('\\\\', '\x00BACKSLASH\x00')  # placeholder
    text = text.replace('\\"', '"')
    text = text.replace('\\/', '/')
    text = text.replace('\\n', '\n')
    text = text.replace('\\t', '\t')
    text = text.replace('\x00BACKSLASH\x00', '\\')

    # Convert [p] and [/p] to newlines (each [p]...[/p] is a line)
    text = re.sub(r'\[/?p\]', '\n', text)

    # Convert [b][u]...[/u][/b] headers — keep the inner text
    text = re.sub(r'\[b\]\s*\[u\](.*?)\[/u\]\s*\[/b\]', r'\1', text)

    # Convert [h1]-[h3] headers
    text = re.sub(r'\[/?h[1-3]\]', '', text)

    # Convert [list] / [*] items
    text = re.sub(r'\[/?list\]', '\n', text)
    text = text.replace('[*]', '- ')

    # Strip remaining BBCode tags
    text = re.sub(r'\[/?[a-zA-Z][a-zA-Z0-9]*(?:=[^\]]+)?\]', '', text)

    # Unescape literal brackets: \[ → [  (used in section headers like \[ General ])
    text = text.replace('\\[', '[')
    text = text.replace('\\]', ']')

    # Decode HTML entities
    text = unescape(text)

    lines = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Keep patch note lines, section headers, and sub-patch date headers
        if line.startswith("- ") or line.startswith("* ") or line.startswith("["):
            lines.append(line)
        elif re.match(r'\d{2}-\d{2}-\d{4}\s+Patch', line):
            # Sub-patch date header like "03-07-2026 Patch:"
            lines.append(f"[ {line} ]")

    return lines


def _parse_steam_html(body_html: str) -> list[str]:
    """Parse Steam EventDetailsBody HTML into patch note lines (fallback)."""
    text = re.sub(r'<(?:br|wbr)\s*/?>', '\n', body_html)
    text = re.sub(r'<b>\s*<u>(.*?)</u>\s*</b>', r'\1', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = unescape(text)

    lines = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("- ") or line.startswith("* ") or line.startswith("["):
            lines.append(line)
        elif re.match(r'\d{2}-\d{2}-\d{4}\s+Patch', line):
            lines.append(f"[ {line} ]")

    return lines


def extract_from_html(html: str) -> str:
    """Extract patch note lines from a forum thread HTML page.

    The Deadlock forums (XenForo) wrap each post in:
        <article data-author="Yoshi" ...>
            ...
            <div class="bbWrapper">...</div>
            ...
        </article>

    We extract bbWrapper content from ALL posts by the developer (Yoshi),
    since patch notes sometimes span multiple posts in the same thread.
    """
    all_lines = []

    # Find all posts by Yoshi (the Valve developer who posts patch notes)
    # Each post is an <article> with data-author="Yoshi"
    yoshi_posts = list(re.finditer(
        r'<article[^>]*\bdata-author="Yoshi"[^>]*>(.*?)</article>',
        html, re.DOTALL
    ))

    if yoshi_posts:
        logger.info(f"Found {len(yoshi_posts)} post(s) by Yoshi")
        for i, post_match in enumerate(yoshi_posts):
            post_html = post_match.group(1)

            # Skip posts that are just a Steam news URL unfurl (the actual
            # content is fetched separately via _fetch_steam_patch_notes)
            if STEAM_NEWS_PATTERN.search(post_html) and 'bbCodeBlock--unfurl' in post_html:
                # Check if this post has any real patch content beyond the unfurl
                # Strip out unfurl blocks, then check for bbWrapper content
                stripped = re.sub(
                    r'<div class="bbCodeBlock bbCodeBlock--unfurl.*?</div>\s*</div>\s*</div>\s*</div>',
                    '', post_html, flags=re.DOTALL
                )
                bb_match = re.search(r'<div class="bbWrapper">(.*?)</div>', stripped, re.DOTALL)
                if not bb_match or not _extract_bbwrapper(bb_match.group(1)):
                    logger.info(f"  Post {i+1}: skipped (Steam URL unfurl only)")
                    continue

            # Extract post date from <time> element
            time_match = re.search(
                r'<time[^>]*datetime="(\d{4})-(\d{2})-(\d{2})T',
                post_html
            )

            # Find the bbWrapper within this post
            bb_match = re.search(
                r'<div class="bbWrapper">(.*?)</div>\s*(?:</div>|<div class="js-selectToQuoteEnd">)',
                post_html, re.DOTALL
            )
            if not bb_match:
                bb_match = re.search(r'<div class="bbWrapper">(.*?)</div>', post_html, re.DOTALL)
            if bb_match:
                lines = _extract_bbwrapper(bb_match.group(1))
                if lines:
                    # Inject date header before this post's lines so the parser
                    # can tag each change with the date it was actually posted
                    if time_match:
                        y, m, d = time_match.group(1), time_match.group(2), time_match.group(3)
                        date_header = f"[ {m}-{d}-{y} Update: ]"
                        all_lines.append(date_header)
                    logger.info(f"  Post {i+1}: {len(lines)} lines")
                    all_lines.extend(lines)
    else:
        # Fallback: no Yoshi posts found, grab first bbWrapper (legacy behavior)
        logger.info("No Yoshi posts found, falling back to first bbWrapper")
        match = re.search(
            r'<div class="bbWrapper">(.*?)</div>\s*(?:</div>|<div class="js-selectToQuoteEnd">)',
            html, re.DOTALL
        )
        if not match:
            match = re.search(r'<div class="bbWrapper">(.*?)</div>', html, re.DOTALL)
        if match:
            all_lines = _extract_bbwrapper(match.group(1))

    if not all_lines:
        logger.warning("Could not extract any patch note lines from HTML")

    return "\n".join(all_lines)


def _fetch_steam_patch_notes(steam_url: str) -> list[str]:
    """Fetch a Steam news page and extract patch note lines."""
    logger.info(f"Fetching Steam news page: {steam_url}")
    resp = requests.get(steam_url, timeout=30, headers={"User-Agent": "DeadlockPatchTool/1.0"})
    resp.raise_for_status()
    lines = _extract_steam_news(resp.text)
    if lines:
        logger.info(f"  Extracted {len(lines)} lines from Steam news page")
    else:
        logger.warning("  No patch note lines found on Steam news page")
    return lines


def fetch_patch_notes(thread_url: str) -> str:
    """Fetch a forum thread and extract patch notes from all Yoshi posts.

    If Yoshi's post contains a Steam news URL, fetches that page first for
    the main patch notes. Forum post content (hotfixes, follow-ups) is
    appended after the Steam content.

    Handles multi-page threads by following pagination links, since Yoshi's
    follow-up posts may be on page 2+ in threads with many community replies.
    """
    all_lines = []
    steam_urls_fetched = set()
    page = 1
    url = thread_url

    while url:
        logger.info(f"Fetching thread{f' (page {page})' if page > 1 else ''}: {url}")
        resp = requests.get(url, timeout=30, headers={"User-Agent": "DeadlockPatchTool/1.0"})
        resp.raise_for_status()
        html = resp.text

        # On the first page, check for Steam news URLs in Yoshi's posts
        if page == 1:
            # Extract the first Yoshi post's date for the initial Steam content
            first_time = re.search(
                r'<article[^>]*\bdata-author="Yoshi"[^>]*>.*?'
                r'<time[^>]*datetime="(\d{4})-(\d{2})-(\d{2})T',
                html, re.DOTALL
            )
            steam_urls = _extract_steam_urls(html)
            for steam_url in steam_urls:
                if steam_url not in steam_urls_fetched:
                    steam_urls_fetched.add(steam_url)
                    try:
                        # Inject the thread date header before Steam content
                        if first_time:
                            y, m, d = first_time.group(1), first_time.group(2), first_time.group(3)
                            all_lines.append(f"[ {m}-{d}-{y} Update: ]")
                        steam_lines = _fetch_steam_patch_notes(steam_url)
                        all_lines.extend(steam_lines)
                    except Exception as e:
                        logger.error(f"Failed to fetch Steam news page: {e}")

        # Extract lines from forum posts on this page
        page_text = extract_from_html(html)
        if page_text:
            forum_lines = page_text.splitlines()
            if steam_urls_fetched:
                # Deduplicate: Steam page often includes the same hotfix content
                # that's also in the forum follow-up posts
                seen_lines = set(all_lines)
                new_lines = [l for l in forum_lines if l not in seen_lines]
                # Remove orphaned date headers (date header with no content after it)
                cleaned = []
                for j, line in enumerate(new_lines):
                    if re.match(r'^\[.*\d{2}-\d{2}-\d{4}.*\]$', line):
                        # Check if next non-header line exists
                        has_content = any(
                            not re.match(r'^\[.*\]$', new_lines[k])
                            for k in range(j + 1, len(new_lines))
                        )
                        if not has_content:
                            continue
                    cleaned.append(line)
                if len(forum_lines) - len(cleaned) > 0:
                    skipped = len(forum_lines) - len(cleaned)
                    logger.info(f"  Deduped {skipped} lines already in Steam content")
                all_lines.extend(cleaned)
            else:
                all_lines.extend(forum_lines)

        # Check for next page — only follow if we found Yoshi posts on page 1
        # (don't paginate through dozens of community reply pages)
        if page == 1:
            # Count total Yoshi posts expected vs found on this page
            yoshi_count = len(re.findall(r'<article[^>]*\bdata-author="Yoshi"', html))
            if yoshi_count == 0:
                break  # No Yoshi posts at all, stop

        # Look for "next page" link
        next_match = re.search(
            r'<a[^>]*class="pageNav-jump pageNav-jump--next"[^>]*href="([^"]+)"',
            html
        )
        if next_match and page < 5:  # Safety limit: max 5 pages
            next_url = unescape(next_match.group(1))
            if not next_url.startswith("http"):
                next_url = "https://forums.playdeadlock.com" + next_url
            url = next_url
            page += 1
        else:
            break

    return "\n".join(all_lines)


def fetch_latest_patch_notes(rss_url: str = CHANGELOG_RSS) -> tuple[str, str]:
    """Convenience: fetch RSS → get latest thread → extract notes.

    Returns (title, patch_notes_text).
    """
    title, url = fetch_latest_url(rss_url)
    text = fetch_patch_notes(url)
    line_count = len(text.strip().splitlines()) if text else 0
    logger.info(f"Extracted {line_count} lines from '{title}'")
    return title, text
