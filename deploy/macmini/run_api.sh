#!/usr/bin/env bash
# launchd entrypoint for the Coliseum API. Settings come from backend/.env (pydantic reads it from cwd).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT/backend"
PORT="$(grep -E '^PORT=' .env 2>/dev/null | cut -d= -f2 || true)"
exec "$ROOT/.venv/bin/python" -m uvicorn app.main:app \
  --host 0.0.0.0 --port "${PORT:-8000}" \
  --proxy-headers --forwarded-allow-ips='*' \
  --log-level info
