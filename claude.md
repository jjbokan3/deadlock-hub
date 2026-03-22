# Deadlock Patch Notes Tool — Project Context

## What this is

An automated pipeline that takes Deadlock patch notes (raw text from Valve's forum posts), parses them into structured data using the Deadlock Assets API, rates each hero/item change via an LLM or heuristic, and generates a formatted HTML page with interactive dropdowns, color-coded ability tags, star ratings, and runtime image injection. The output is served as a static site at `games.josephbokan.io/deadlock/`.

The project owner is Joseph (josephbokan.io). He's an active Deadlock player with deep MOBA experience (League, Dota 2, Smite) who approaches the game analytically. He cares about spirit scaling interactions, ability range stacking, and how balance changes compound across item ecosystems. Keep explanations technical and game-aware.

## Architecture

```
Raw text  →  parser/       →  Tokenize, match heroes/items/abilities via API
          →  parser/       →  Detect buff/nerf/neutral per line (keyword + inverted stat logic)
          →  llm/          →  Rate each entity (pluggable: Claude, OpenAI, Ollama, heuristic)
          →  renderer/     →  Generate HTML with embedded data + runtime image JS
          →  site/deadlock/ →  Static files served by server.py via Cloudflare tunnel
```

## File map

```
deadlock-patch-tool/
├── main.py              # CLI entry point. --input, --latest (RSS), --llm, --json-only, --yes
├── models.py            # Dataclasses: Change, HeroData, ItemData, LLMRating, ParsedPatchNotes
├── feed.py              # RSS feed fetcher + XenForo HTML extractor (bbWrapper → plain text)
├── index_generator.py   # Generates site/deadlock/index.html listing page with hero pills + stats
├── server.py            # Static file server for site/ directory (point Cloudflare tunnel here)
├── watcher.py           # Polls RSS feed, auto-runs pipeline on new patches, regenerates index
├── debug_items.py       # Diagnostic: dumps raw API item fields to find category field name
├── requirements.txt     # requests, rich (core); anthropic/openai (optional LLM)
├── .env                 # (user-created) ANTHROPIC_API_KEY, etc.
├── .cache/              # Auto-created. heroes.json, items.json (6hr TTL), seen_patches.json
│
├── api/
│   └── __init__.py      # DeadlockAPI class
│                        #   Fetches /v2/heroes and /v2/items, builds indexes:
│                        #   - heroes_by_name, items_by_name, items_by_class
│                        #   - ability_lookup: display_name → (hero, slot 1-4)
│                        #   - hero_names, item_names (for parser entity matching)
│                        #   Shop items detected by class_name prefix "upgrade_"
│                        #   KNOWN ISSUE: Item category field not confirmed. Code tries
│                        #   multiple field names. If items land in "Other", run debug_items.py.
│
├── parser/
│   ├── __init__.py      # detect_direction(): keyword + inverted-stat-aware buff/nerf detection
│   │                    #   INVERTED_STATS: cooldown, cast time, deploy time, reload time,
│   │                    #   wind up time, wait time, lockout, stamina cooldown, etc.
│   │                    #   "increased cooldown" = NERF. "reduced cooldown" = BUFF.
│   │                    #   Also: extract_values() for "from X to Y" patterns.
│   └── tokenizer.py     # parse(): splits lines on ":", matches prefix against API hero/item names,
│                        #   resolves abilities via longest-match against hero's signature1-4 display
│                        #   names, detects T1/T2/T3 tiers, classifies change types.
│                        #   HERO_ALIASES: {"doorman": "the doorman"} — keep in sync with renderer JS.
│
├── llm/
│   ├── __init__.py      # LLMProvider ABC with:
│   │                    #   - Call tracking (_call_count, _skip_count)
│   │                    #   - Budget enforcement (max_calls=200, max_prompt_chars=8000)
│   │                    #   - Auto-fallback to HeuristicProvider when budget exhausted
│   │                    #   - RATING_PROMPT: extensive Deadlock-specific guidance including:
│   │                    #     spirit scaling as highest-leverage stat, movement speed value,
│   │                    #     signature ability weighting, build path disruption cost,
│   │                    #     explicit "what qualifies" / "what does NOT" per rating tier
│   │                    #   - HeuristicProvider: buff/nerf ratio → 1-5 rating
│   │                    #     Extreme ratings (1,5) require 3+ directional changes
│   │                    #     Single buff → 4 (Buff), single nerf → 2 (Nerf)
│   │                    #   - get_provider(name, **kwargs) factory
│   ├── claude_provider.py   # anthropic SDK. Env: ANTHROPIC_API_KEY, ANTHROPIC_MODEL
│   ├── openai_provider.py   # openai SDK. Env: OPENAI_API_KEY, OPENAI_MODEL, OPENAI_BASE_URL
│   └── ollama_provider.py   # Raw HTTP requests. Env: OLLAMA_MODEL, OLLAMA_URL. No budget limit.
│
├── renderer/
│   └── __init__.py      # Generates complete HTML page. All CSS inline. JS handles:
│                        #   - Toggle/expand/collapse interactions
│                        #   - Star SVG rendering from rating-N CSS classes
│                        #   - Runtime image fetch from Deadlock API (/v2/heroes + /v2/items)
│                        #   - Injects hero portraits, item icons, ability icons
│                        #   - HERO_ALIASES in JS must stay in sync with parser's HERO_ALIASES
│
└── site/                # Static site root served by server.py
    ├── index.html       # Game picker (links to /deadlock/)
    └── deadlock/
        ├── index.html   # Patch listing (auto-regenerated)
        └── *.html       # Individual patch pages
```

## Deployment (Mac Mini)

```bash
# Server: serves site/ on port 8080
python3 server.py --port 8080

# Watcher: polls RSS every 5 min, generates patches, regenerates index
python3 watcher.py --interval 300 --llm heuristic --output-dir ./site/deadlock

# Cloudflare tunnel: games.josephbokan.io → http://localhost:8080
```

URL structure:
```
games.josephbokan.io/                          → site/index.html (game picker)
games.josephbokan.io/deadlock/                 → site/deadlock/index.html (patch listing)
games.josephbokan.io/deadlock/03_21_2026.html  → specific patch notes page
```

Use macOS launchd plist files in ~/Library/LaunchAgents/ to auto-start server + watcher on boot.

## API data

### Heroes: GET https://assets.deadlock-api.com/v2/heroes
- `name`: Display name ("Infernus", "The Doorman", "Mo & Krill")
- `images.icon_hero_card`: Portrait PNG
- `items.signature1-4`: Ability class_names → slot 1-4
- `player_selectable`: Filter to playable heroes only

### Items: GET https://assets.deadlock-api.com/v2/items
- `name`: Display name ("Metal Skin")
- `class_name`: Internal ID ("upgrade_metal_skin" for shop items, "ability_flame_dash" for abilities)
- `image`: Icon URL
- Category field: **not confirmed** — code tries multiple field names. Run `debug_items.py` if items aren't categorizing.

### Codename mappings (for reference)
API uses internal codenames for hero images. Key mappings:
inferno=Infernus, ghost=Lady Geist, forge=McGinnis, krill=Mo & Krill,
nano=Calico, necro=Graves, fencer=Apollo, frank=Victor, punkgoat=Billy,
tengu=Ivy, unicorn=Celeste, vampirebat=Mina, werewolf=Silver, familiar=Rem,
priest=Venator, astro=Holliday, bookworm=Paige, chrono=Paradox, hornet=Vindicta,
kali=Grey Talon, magician=Sinclair, slork=Fathom, doorman=The Doorman.
Direct matches: bebop, haze, kelvin, lash, mirage, shiv, viscous, warden, wraith, yamato.

## RSS feed

Deadlock forums (XenForo) expose RSS at:
`https://forums.playdeadlock.com/forums/changelog.10/index.rss`

Patch content is in `<content:encoded>` as HTML with `<br />` line breaks inside
`<div class="bbWrapper">`. The feed.py module extracts this by:
1. Fetching the full thread URL (RSS content is truncated)
2. Finding the first `bbWrapper` div
3. Converting `<br />` → newlines, stripping HTML tags, decoding entities
4. Filtering to lines starting with `- ` or `* ` or `[`

## LLM prompt design

The rating prompt (in `llm/__init__.py`) includes:
- Explicit "what qualifies" / "what does NOT qualify" criteria per rating tier (1-5)
- Deadlock-specific balance principles from community research:
  - Spirit scaling compounds multiplicatively with items (highest leverage stat)
  - Movement speed creates options raw stats can't match
  - Signature ability changes >> peripheral ability changes
  - Ultimate changes >> basic ability changes
  - Build path disruption (forced re-itemization) is a hidden cost
  - Global context compounds (12 items losing range + hero range nerfs = double hit)
- Per-change context sent to LLM includes: ability name, slot number, tier, old→new values
- Response format: JSON with `rating` (int 1-5) and `explanation` (2-4 sentences)

## Adding a new LLM provider

1. Create `llm/my_provider.py`, subclass `LLMProvider`
2. Call `super().__init__(**kwargs)` in `__init__`
3. Implement `complete(self, prompt: str, system: str = "") -> str`
4. Set `self.max_calls = 999999` for local/free providers
5. Register in `llm/__init__.py` `_register_optional_providers()`

## Common fixes

**Items all in "Other"**: Run `python3 debug_items.py`, find the category field name,
add it to `CATEGORY_FIELDS` and its values to `CATEGORY_VALUE_MAP` in `api/__init__.py`.

**Hero name mismatch**: Add to `HERO_ALIASES` in both `parser/tokenizer.py` and the
JS section of `renderer/__init__.py`.

**Windows encoding errors**: All `open()` calls use `encoding="utf-8"`. If new file
operations are added, always include this parameter.

**Testing direction detection**:
```python
from parser import detect_direction
from models import ChangeDirection
assert detect_direction("cooldown increased from 7s to 9s") == ChangeDirection.NERF
assert detect_direction("cooldown reduced from 140s to 130s") == ChangeDirection.BUFF
assert detect_direction("now also grants +20 Spirit Power") == ChangeDirection.BUFF
assert detect_direction("no longer grants +1m Move Speed") == ChangeDirection.NERF
```

## Progress bars

Uses Rich library. The rating loop shows:
- Animated spinner + progress bar per group (Heroes, Items)
- After each group completes, a bordered panel with star ratings and colored verdicts
- Cloud provider confirmation uses a Rich panel with estimated token usage

## Adding another game

1. Create processing pipeline in a new directory
2. Output HTML to `site/anothergame/`
3. Add a link in `site/index.html` (game picker page — styled template in `server.py`)

## Dependencies

| Package | Required | Purpose |
|---------|----------|---------|
| requests | Yes | Deadlock API + RSS fetching |
| rich | Yes | Progress bars, confirmation UI |
| anthropic | For --llm claude | Claude API |
| openai | For --llm openai | OpenAI API |
| (none) | For --llm ollama | Uses requests |
