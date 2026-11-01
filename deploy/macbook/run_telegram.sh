#!/usr/bin/env bash
# launchd entrypoint for the live Telegram bot on this Mac (com.protoss.telegram). Waits for the token file, clears any
# leftover bot processes from a previous run, then starts telegram_demo.py --live. launchd restarts it when it exits.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
while [ ! -s "$HOME/.protoss/telegram.env" ]; do sleep 5; done  # TELEGRAM_BOT_TOKEN=..., written by Matthew, mode 600
PY="$ROOT/.venv/bin/python"; [ -x "$PY" ] || PY="$HOME/protoss-demo/.venv/bin/python"
pkill -f "scripts/telegram_bridge.py run" 2>/dev/null
pkill -f "uvicorn app.main:app --host 127.0.0.1 --port ${PROTOSS_TG_PORT:-8001}" 2>/dev/null
sleep 1
[ -f web/dist/index.html ] || (cd web && npx vite build --outDir dist --logLevel error)
echo "=== start $(date '+%F %T') on $(git log --oneline -1) ==="
# caffeinate keeps the Mac from idle-sleeping while the bot runs (a closed lid still sleeps it); it exits with the bot
printf 'LIVE\n' | caffeinate -i "$PY" -u scripts/telegram_demo.py --live --chat "$PROTOSS_TG_CHAT" --users "$PROTOSS_TG_USERS" --port "${PROTOSS_TG_PORT:-8001}"
