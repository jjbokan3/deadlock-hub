# Deadlock Patch Notes Tool

Automatically parses Deadlock patch notes, enriches them with data from the [Deadlock Assets API](https://assets.deadlock-api.com), and generates a formatted HTML page with nerf/buff analysis.

## What it does

| Step | Method | Details |
|------|--------|---------|
| Parse lines | Code | Regex + pattern matching on raw patch note text |
| Identify heroes/items | Code | Matches against API's hero/item name indexes |
| Resolve abilities to slots | Code | Maps ability names → signature1-4 → slot 1-4 |
| Detect buff/nerf direction | Code | Keyword analysis with context-aware stat inversion |
| Categorize items | Code | Uses API's `item_slot_type` field |
| Rate changes (1-5 stars) | **LLM** | Per-entity prompt with change context |
| Write analysis blurb | **LLM** | 2-3 sentence explanation per entity |
| Generate HTML | Code | Full page with images, color-coded abilities, dropdowns |

The LLM is only used for the subjective parts (ratings + explanations). Everything else is deterministic.

## Setup

```bash
pip install -r requirements.txt

# Install your preferred LLM provider:
pip install anthropic    # for Claude
pip install openai       # for OpenAI / compatible APIs
# Ollama needs no extra package (uses requests)
```

## Usage

### Basic: heuristic ratings (no LLM, instant)
```bash
cat patch_notes.txt | python main.py --output patch.html
```

### With Claude ratings
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
cat patch_notes.txt | python main.py --llm claude --output patch.html
```

### With OpenAI ratings
```bash
export OPENAI_API_KEY="sk-..."
cat patch_notes.txt | python main.py --llm openai --output patch.html
```

### With local Ollama
```bash
# Make sure Ollama is running with a model loaded
cat patch_notes.txt | python main.py --llm ollama --model llama3.1 --output patch.html
```

### With any OpenAI-compatible API (Together, Groq, etc.)
```bash
export OPENAI_API_KEY="your-key"
cat patch_notes.txt | python main.py --llm openai \
  --base-url https://api.together.xyz/v1 \
  --model meta-llama/Llama-3-70b-chat-hf \
  --output patch.html
```

### JSON output only (no HTML, no LLM)
```bash
cat patch_notes.txt | python main.py --json-only --output parsed.json
```

## Input format

Paste Deadlock patch notes as plain text. Each change should be on its own line prefixed with `- `:

```
- Hero health growth increased by +3 and 4%
- Greater Expansion: Ability Range reduced from 35% to 30%
- Abrams: Melee damage per boon increased by 10%
- Abrams: Siphon Life T3 range reduced from +3.5m to +3m
```

The parser auto-detects:
- **System changes** — lines that don't match any hero or item name
- **Item changes** — `Item Name: change description`
- **Hero changes** — `Hero Name: change description`
  - Base stat changes (no ability name found in text)
  - Ability changes (ability name matched against API data)
  - Tier upgrades (T1/T2/T3 detected)
  - Bug fixes (`Fixed ...`)

## Adding a new LLM provider

1. Create `llm/my_provider.py`:

```python
from llm import LLMProvider

class MyProvider(LLMProvider):
    def __init__(self, model="", api_key="", **kwargs):
        # setup your client
        pass

    def complete(self, prompt: str, system: str = "") -> str:
        # call your API, return the raw text response
        return "..."
```

2. Register it in `llm/__init__.py`:

```python
from llm.my_provider import MyProvider
PROVIDERS["my_provider"] = MyProvider
```

3. Use it: `python main.py --llm my_provider`

## Project structure

```
deadlock-patch-tool/
├── main.py              # CLI entry point
├── models.py            # Data classes (Change, HeroData, ItemData, etc.)
├── requirements.txt
├── api/
│   └── __init__.py      # Deadlock Assets API client + caching
├── parser/
│   ├── __init__.py      # Direction detection (buff/nerf/neutral)
│   └── tokenizer.py     # Main line parser + entity matching
├── llm/
│   ├── __init__.py      # Abstract provider + factory + heuristic
│   ├── claude_provider.py
│   ├── openai_provider.py
│   └── ollama_provider.py
└── renderer/
    └── __init__.py      # HTML page generator
```

## API caching

Hero and item data from the Deadlock Assets API is cached in `.cache/` for 6 hours. Use `--no-cache` to force a refresh.
