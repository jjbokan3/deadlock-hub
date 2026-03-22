#!/bin/bash
# Deploy latest code from origin/main and restart services.
#
# Usage:
#   ./deploy.sh                    # deploy to prod directory
#   ./deploy.sh /path/to/prod      # custom prod directory

set -e

PROD_DIR="${1:-/Users/josephbokan/deadlock-patch-tool-prod}"
UID_NUM=$(id -u)

echo "=== Deploying to $PROD_DIR ==="

if [ ! -d "$PROD_DIR/.git" ]; then
    echo "Error: $PROD_DIR is not a git repository"
    exit 1
fi

cd "$PROD_DIR"

echo "Fetching latest..."
git fetch origin

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" = "$REMOTE" ]; then
    echo "Already up to date ($LOCAL)"
    exit 0
fi

echo "Updating $LOCAL -> $(git rev-parse --short origin/main)..."
git reset --hard origin/main

echo "Installing dependencies..."
if [ -f ".venv/bin/pip" ]; then
    .venv/bin/pip install -r requirements.txt --quiet 2>/dev/null
elif command -v uv &>/dev/null; then
    uv pip install -r requirements.txt --quiet 2>/dev/null
fi

echo "Regenerating patch pages with updated renderer..."
rm -f .cache/seen_patches.json
if [ -f ".venv/bin/python3" ]; then
    .venv/bin/python3 watcher.py --once --llm heuristic --output-dir ./site/deadlock/updates 2>&1 || true
elif command -v uv &>/dev/null; then
    uv run python3 watcher.py --once --llm heuristic --output-dir ./site/deadlock/updates 2>&1 || true
fi

echo "Restarting services..."
launchctl kickstart -k "gui/$UID_NUM/io.josephbokan.deadlock-server" 2>/dev/null || true
launchctl kickstart -k "gui/$UID_NUM/io.josephbokan.deadlock-watcher" 2>/dev/null || true
launchctl kickstart -k "gui/$UID_NUM/io.josephbokan.deadlock-dashboard" 2>/dev/null || true

echo "=== Deploy complete ==="
git log -1 --format="Commit: %h (%ci)"
