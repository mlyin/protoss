#!/usr/bin/env bash
# launchd entrypoint for the bot fleet (fleet.yaml): waits for the API, then runs scripts/fleet.py,
# which registers anything missing and supervises the bots. launchd restarts us if we exit.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
envval() { grep -E "^$1=" backend/.env 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' || true; }
export ADMIN_TOKEN="$(envval ADMIN_TOKEN)"
PORT="$(envval PORT)"; PORT="${PORT:-8000}"
export ARENA_URL="http://127.0.0.1:${PORT}"
for _ in $(seq 1 120); do
  curl -fsS "$ARENA_URL/health" >/dev/null 2>&1 && break
  sleep 1
done
exec "$ROOT/.venv/bin/python" -u scripts/fleet.py --config fleet.yaml
