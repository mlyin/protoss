#!/usr/bin/env bash
# Put the dev checkout's current commit on the live bot and restart it. Run from the dev checkout (~/Documents/protoss2).
# The bot runs from its own clone (~/protoss-bot) because launchd agents cannot read ~/Documents (macOS privacy).
set -euo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BOT="${PROTOSS_BOT_DIR:-$HOME/protoss-bot}"
BRANCH="$(git -C "$SRC" branch --show-current)"
git -C "$BOT" fetch -q "$SRC" "$BRANCH"
git -C "$BOT" checkout -q -B "$BRANCH" FETCH_HEAD
mkdir -p "$BOT/web/dist" && rsync -a --delete "$SRC/web/dist/" "$BOT/web/dist/"  # gitignored build the bot's local site serves
launchctl kickstart -k "gui/$(id -u)/com.protoss.telegram"
echo "bot restarted on $(git -C "$BOT" log --oneline -1)"
