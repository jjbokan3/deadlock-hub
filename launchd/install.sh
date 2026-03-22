#!/bin/bash
# Install launchd services for the Deadlock patch tool.
#
# This script:
#   1. Creates the prod clone if it doesn't exist
#   2. Sets up the prod venv and installs deps
#   3. Copies .env to prod
#   4. Symlinks plist files to ~/Library/LaunchAgents/
#   5. Loads the services
#
# Usage:
#   cd /path/to/deadlock-patch-tool/launchd
#   ./install.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEV_DIR="$(dirname "$SCRIPT_DIR")"
PROD_DIR="/Users/josephbokan/deadlock-patch-tool-prod"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
UID_NUM=$(id -u)

echo "=== Deadlock Patch Tool — Service Installer ==="
echo "Dev:  $DEV_DIR"
echo "Prod: $PROD_DIR"
echo ""

# 1. Create prod clone
if [ ! -d "$PROD_DIR/.git" ]; then
    echo "Creating prod clone..."
    REMOTE=$(cd "$DEV_DIR" && git remote get-url origin 2>/dev/null || echo "")
    if [ -z "$REMOTE" ]; then
        echo "Error: No git remote found. Push to GitHub first."
        exit 1
    fi
    git clone "$REMOTE" "$PROD_DIR"
else
    echo "Prod clone exists, pulling latest..."
    cd "$PROD_DIR" && git fetch origin && git reset --hard origin/main
fi

# 2. Set up prod venv
echo "Setting up prod venv..."
cd "$PROD_DIR"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
.venv/bin/pip install -r requirements.txt --quiet 2>/dev/null || true

# 3. Copy .env
if [ -f "$DEV_DIR/.env" ]; then
    cp "$DEV_DIR/.env" "$PROD_DIR/.env"
    echo "Copied .env to prod"
fi

# 4. Create logs directory
mkdir -p "$PROD_DIR/logs"

# 5. Symlink plist files
echo "Installing launchd plists..."
mkdir -p "$LAUNCH_AGENTS"
for plist in "$SCRIPT_DIR"/*.plist; do
    name=$(basename "$plist")
    target="$LAUNCH_AGENTS/$name"
    if [ -L "$target" ] || [ -f "$target" ]; then
        # Unload existing service first
        launchctl bootout "gui/$UID_NUM/$( basename "$name" .plist )" 2>/dev/null || true
        rm -f "$target"
    fi
    ln -s "$plist" "$target"
    echo "  Linked: $name"
done

# 6. Load services
echo "Loading services..."
for plist in "$LAUNCH_AGENTS"/io.josephbokan.deadlock-*.plist; do
    name=$(basename "$plist" .plist)
    launchctl bootstrap "gui/$UID_NUM" "$plist" 2>/dev/null || true
    echo "  Loaded: $name"
done

echo ""
echo "=== Installation complete ==="
echo ""
echo "Services:"
launchctl list | grep "josephbokan.deadlock" || echo "  (none running yet — may need a moment)"
echo ""
echo "URLs:"
echo "  Prod server:  http://localhost:8085"
echo "  Dev server:   http://localhost:8086  (run manually: uv run server.py --port 8086)"
echo "  Dashboard:    http://localhost:8087"
echo ""
echo "Cloudflare tunnel: point games.josephbokan.io -> http://localhost:8085"
