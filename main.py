#!/usr/bin/env python3
"""Deadlock Patch Notes Tool — parse, analyze, and render patch notes.

Usage:
    # Full pipeline with Claude for ratings
    python main.py --input patch_notes.txt --llm claude --output patch.html

    # Use OpenAI instead
    python main.py --input patch_notes.txt --llm openai --output patch.html

    # Use local Ollama
    python main.py --input patch_notes.txt --llm ollama --model llama3.1 --output patch.html

    # Heuristic only (no LLM calls)
    python main.py --input patch_notes.txt --output patch.html

    # Parse only — output structured JSON
    python main.py --input patch_notes.txt --json-only

    # Skip confirmation prompt
    python main.py --input patch_notes.txt --llm claude --yes --output patch.html
"""
from __future__ import annotations
import argparse
import json
import logging
import os
import sys
from dataclasses import asdict

from api import DeadlockAPI
from parser.tokenizer import parse
from llm import get_provider
from renderer import render

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("deadlock-patch-tool")

# ── Rich console ─────────────────────────────────────────────────

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, MofNCompleteColumn, TimeElapsedColumn
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

console = Console()

RATING_STYLES = {
    1: ("▼▼ Huge Nerf", "bold red"),
    2: ("▼ Nerf", "yellow"),
    3: ("— Mixed", "dim"),
    4: ("▲ Buff", "green"),
    5: ("▲▲ Big Buff", "bold cyan"),
}


def _rate_with_progress(label, change_groups, entity_type, provider):
    """Rate all entities in a group with a Rich progress bar."""
    total = len(change_groups)
    if total == 0:
        return

    results = []

    with Progress(
        SpinnerColumn("dots"),
        TextColumn("[bold]{task.description}"),
        BarColumn(bar_width=30, style="bar.back", complete_style="bar.complete", finished_style="bar.finished"),
        MofNCompleteColumn(),
        TextColumn("│"),
        TextColumn("[dim]{task.fields[current]}"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task(label, total=total, current="")

        for name, group in change_groups.items():
            progress.update(task, current=name)
            group.rating = provider.rate_changes(name, entity_type, group.changes)
            r = group.rating
            sym, style = RATING_STYLES.get(r.rating, ("—", "dim"))
            results.append((name, r.rating, sym, style))
            progress.advance(task)

        progress.update(task, current="[green]done[/green]")

    # Print results table
    table = Table(
        box=box.SIMPLE_HEAVY,
        show_header=False,
        padding=(0, 1),
        pad_edge=False,
    )
    table.add_column("Name", min_width=20)
    table.add_column("Rating", justify="center", width=6)
    table.add_column("Verdict", min_width=14)

    for name, score, sym, style in results:
        stars = "★" * score + "☆" * (5 - score)
        table.add_row(
            Text(name),
            Text(stars, style="bold yellow"),
            Text(sym, style=style),
        )

    console.print(Panel(table, title=f"[bold]{label} Ratings", border_style="dim", expand=False))


def _load_env_file():
    """Load .env file if it exists (simple KEY=VALUE format)."""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")
            if key and value and key not in os.environ:
                os.environ[key] = value
    logger.info("Loaded .env file")


def main():
    parser = argparse.ArgumentParser(
        description="Parse Deadlock patch notes into a formatted HTML page.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--input", "-i",
        help="Path to patch notes text file (default: read from stdin)",
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Fetch the latest patch notes from the Deadlock changelog RSS feed",
    )
    parser.add_argument(
        "--output", "-o",
        help="Path to write HTML output (default: stdout)",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Output parsed JSON instead of HTML (skips LLM and rendering)",
    )
    parser.add_argument(
        "--llm",
        default="heuristic",
        choices=["claude", "openai", "ollama", "heuristic"],
        help="LLM provider for ratings (default: heuristic)",
    )
    parser.add_argument(
        "--model",
        default="",
        help="Model name override for the LLM provider",
    )
    parser.add_argument(
        "--api-key",
        default="",
        help="API key for the LLM provider (or set env var / .env file)",
    )
    parser.add_argument(
        "--base-url",
        default="",
        help="Base URL override (for OpenAI-compatible APIs or Ollama)",
    )
    parser.add_argument(
        "--max-llm-calls",
        type=int,
        default=200,
        help="Max LLM API calls per run (default: 200). Safety limit for cloud providers.",
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Skip confirmation prompt before making LLM calls",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Skip API cache and fetch fresh data",
    )
    parser.add_argument(
        "--title",
        default="",
        help="Patch title (auto-detected with --latest)",
    )

    args = parser.parse_args()

    # ── Load .env file ───────────────────────────────────────────
    _load_env_file()

    # ── Read input ───────────────────────────────────────────────
    patch_title = args.title or None

    if args.latest:
        from feed import fetch_latest_patch_notes
        patch_title, raw_text = fetch_latest_patch_notes()
        if not raw_text.strip():
            logger.error("Fetched empty patch notes from RSS feed")
            sys.exit(1)
        # Auto-generate output filename if not specified
        if not args.output and not args.json_only:
            import re as _re
            safe = _re.sub(r'[^\w\-]', '_', patch_title.lower()).strip('_')
            os.makedirs("./site/deadlock/updates", exist_ok=True)
            args.output = f"./site/deadlock/updates/{safe}.html"
            logger.info(f"Auto output: {args.output}")
    elif args.input:
        with open(args.input, encoding="utf-8") as f:
            raw_text = f.read()
    elif not sys.stdin.isatty():
        raw_text = sys.stdin.read()
    else:
        logger.error("No input provided. Use --latest, --input FILE, or pipe via stdin")
        sys.exit(1)

    if not raw_text.strip():
        logger.error("Input is empty")
        sys.exit(1)

    # ── Load API data ────────────────────────────────────────────
    logger.info("Loading Deadlock API data...")
    api = DeadlockAPI()

    if args.no_cache:
        import glob
        for f in glob.glob(".cache/*.json"):
            os.remove(f)

    api.load()

    # ── Parse ────────────────────────────────────────────────────
    logger.info("Parsing patch notes...")
    parsed = parse(raw_text, api)
    if patch_title:
        parsed.title = patch_title

    # ── JSON-only mode ───────────────────────────────────────────
    if args.json_only:
        output = json.dumps(asdict(parsed), indent=2, default=str)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output)
            logger.info(f"JSON written to {args.output}")
        else:
            print(output)
        return

    # ── LLM ratings ──────────────────────────────────────────────
    total_heroes = len(parsed.hero_changes)
    total_items = len(parsed.item_changes)
    total_calls = total_heroes + total_items
    is_cloud = args.llm in ("claude", "openai")

    logger.info(f"Getting ratings via '{args.llm}' provider...")

    # Confirmation for cloud providers
    if is_cloud and not args.yes:
        info_table = Table(show_header=False, box=None, padding=(0, 2))
        info_table.add_column(style="dim")
        info_table.add_column()
        info_table.add_row("Provider", f"[bold]{args.llm}[/bold]")
        info_table.add_row("Model", args.model or "[dim](default)[/dim]")
        info_table.add_row("Calls needed", f"[bold]{total_calls}[/bold] ({total_heroes} heroes + {total_items} items)")
        info_table.add_row("Call limit", str(args.max_llm_calls))
        info_table.add_row("Est. tokens", f"~{total_calls * 700:,} input + ~{total_calls * 200:,} output")
        console.print()
        console.print(Panel(info_table, title="[bold]LLM Usage Estimate", border_style="yellow", expand=False))
        try:
            from rich.prompt import Confirm
            if not Confirm.ask("  Proceed?", default=True, console=console):
                console.print("[dim]Cancelled. Use --llm heuristic for free ratings, or --yes to skip this.[/dim]")
                sys.exit(0)
        except (EOFError, KeyboardInterrupt):
            sys.exit(0)

    provider_kwargs = {"max_calls": args.max_llm_calls}
    if args.model:
        provider_kwargs["model"] = args.model
    if args.api_key:
        provider_kwargs["api_key"] = args.api_key
    if args.base_url:
        provider_kwargs["base_url"] = args.base_url

    try:
        provider = get_provider(args.llm, **provider_kwargs)
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)
    except Exception as e:
        logger.warning(f"Failed to init '{args.llm}' provider: {e}. Falling back to heuristic.")
        provider = get_provider("heuristic")

    # Rate heroes
    console.print()
    _rate_with_progress(
        "Heroes", parsed.hero_changes, "hero", provider
    )

    # Rate items
    _rate_with_progress(
        "Items", parsed.item_changes, "item", provider
    )
    console.print()

    # LLM usage summary
    if is_cloud:
        logger.info(
            f"LLM calls: {provider.calls_made} made, "
            f"{provider.calls_skipped} skipped (budget: {args.max_llm_calls})"
        )

    # ── Patch summary ─────────────────────────────────────────────
    logger.info("Generating patch summary...")
    parsed.summary = provider.summarize_patch(parsed)
    console.print(f"[dim]Summary: {parsed.summary}[/dim]")

    # ── Render HTML ──────────────────────────────────────────────
    logger.info("Rendering HTML...")
    html = render(parsed)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(html)
        logger.info(f"HTML written to {args.output}")

        # Regenerate index for the output directory
        output_dir = os.path.dirname(os.path.abspath(args.output))
        try:
            from index_generator import write_index
            write_index(output_dir)
        except Exception:
            pass  # non-critical
    else:
        print(html)

    # ── Summary ──────────────────────────────────────────────────
    logger.info(
        f"Done! {len(parsed.system_changes)} system changes, "
        f"{total_items} items, {total_heroes} heroes processed."
    )


if __name__ == "__main__":
    main()
