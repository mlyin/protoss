#!/usr/bin/env bash
# One-command demo in sim mode: start the API, create two agents, run both demo agents for a while.
#   ./scripts/demo.sh            # runs until Ctrl-C
#   DURATION=120 ./scripts/demo.sh
set -euo pipefail
cd "$(dirname "$0")/.."

export ARENA_MODE="${ARENA_MODE:-sim}"
export ADMIN_TOKEN="${ADMIN_TOKEN:-demo-admin}"
export DATABASE_URL="${DATABASE_URL:-sqlite:///./demo.db}"
export TICK_SECONDS="${TICK_SECONDS:-2}"
export SNAPSHOT_SECONDS="${SNAPSHOT_SECONDS:-10}"
export ARENA_URL="http://localhost:8000"
export PYTHONPATH="sdk:${PYTHONPATH:-}"

rm -f demo.db demo.db-wal demo.db-shm
(cd backend && uvicorn app.main:app --port 8000 --log-level warning) &
API=$!
trap 'kill $API 2>/dev/null; pkill -P $$ 2>/dev/null || true' EXIT
for i in $(seq 1 30); do curl -sf localhost:8000/health >/dev/null && break; sleep 0.5; done

mk() {  # name owner runtime markets
  curl -sf -X POST localhost:8000/admin/agents -H "x-admin-token: $ADMIN_TOKEN" -H 'content-type: application/json' \
    -d "{\"name\":\"$1\",\"owner\":\"$2\",\"runtime\":\"$3\",\"starting_equity\":10000,\"limits\":{\"allowed_markets\":$4}}"
}
A=$(mk momentum-7 quantbros "Python SDK" '["BTC","ETH"]')
B=$(mk meanrev-owl 0xlena "Python SDK" '["ETH","SOL","HYPE"]')
KA=$(echo "$A" | python3 -c 'import sys,json;print(json.load(sys.stdin)["agent_key"])')
KB=$(echo "$B" | python3 -c 'import sys,json;print(json.load(sys.stdin)["agent_key"])')
echo "API:          http://localhost:8000  (leaderboard: /leaderboard, docs: /docs)"
echo "Web (if built): http://localhost:8000/"
echo "momentum-7 agent key: $KA"
echo "meanrev-owl agent key: $KB"

ARENA_API_KEY=$KA INTERVAL=2 python3 agents/momentum.py &
ARENA_API_KEY=$KB INTERVAL=2 python3 agents/meanrev.py &

if [ -n "${DURATION:-}" ]; then sleep "$DURATION"; else wait $API; fi
