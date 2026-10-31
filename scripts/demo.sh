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
# --- a sample phalanx: Lee's mandate, two agents inside it, three friends deposited
ORG=$(curl -sf -X POST localhost:8000/admin/orgs -H "x-admin-token: $ADMIN_TOKEN" -H 'content-type: application/json' -d '{
  "name": "Lee'"'"'s Semis Phalanx", "slug": "lee-semis", "leader": "lee", "initial_deposit": 1000, "profit_share_pct": 10,
  "mandate": "Memory and AI chips are mispriced vs demand. Trade xyz:NVDA and xyz:SP500 perps plus BTC as a hedge. Never above 3x. Stop everything at 12% drawdown.",
  "limits": {"max_leverage": 3, "max_notional_usd": 40000, "drawdown_flatten_pct": 12, "daily_loss_pct": 5, "allowed_markets": ["xyz:NVDA", "xyz:SP500", "BTC"]}}')
OK=$(echo "$ORG" | python3 -c 'import sys,json;print(json.load(sys.stdin)["org_key"])')
for who in matthew sam priya; do curl -sf -X POST localhost:8000/orgs/lee-semis/deposit -H 'content-type: application/json' -d "{\"depositor\":\"$who\",\"amount_usd\":100}" >/dev/null; done
M1=$(curl -sf -X POST localhost:8000/orgs/lee-semis/agents -H "authorization: Bearer $OK" -H 'content-type: application/json' -d '{"name":"lee-momentum","allocation_usd":800,"strategy":"Crossover on NVDA + SP500 inside Lee'"'"'s mandate","limits":{"max_leverage":3}}')
M2=$(curl -sf -X POST localhost:8000/orgs/lee-semis/agents -H "authorization: Bearer $OK" -H 'content-type: application/json' -d '{"name":"lee-hedge","allocation_usd":400,"strategy":"Mean-reversion BTC hedge leg","limits":{"max_leverage":2}}')
KM1=$(echo "$M1" | python3 -c 'import sys,json;print(json.load(sys.stdin)["agent_key"])')
KM2=$(echo "$M2" | python3 -c 'import sys,json;print(json.load(sys.stdin)["agent_key"])')
MARKETS=xyz:NVDA,xyz:SP500 RISK_FRACTION=0.8 ARENA_API_KEY=$KM1 INTERVAL=2 python3 agents/momentum.py > /dev/null 2>&1 &
MARKETS=BTC RISK_FRACTION=0.5 ARENA_API_KEY=$KM2 INTERVAL=2 python3 agents/meanrev.py > /dev/null 2>&1 &

echo "API:          http://localhost:8000  (leaderboard: /leaderboard, phalanxes: /orgs, docs: /docs)"
echo "Web (if built): http://localhost:8000/"
echo "momentum-7 agent key: $KA"
echo "meanrev-owl agent key: $KB"

ARENA_API_KEY=$KA INTERVAL=2 python3 agents/momentum.py &
ARENA_API_KEY=$KB INTERVAL=2 python3 agents/meanrev.py &

if [ -n "${DURATION:-}" ]; then sleep "$DURATION"; else wait $API; fi
