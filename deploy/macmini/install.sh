#!/usr/bin/env bash
# Coliseum on a Mac mini, as always-on launchd services (API + bot fleet).
#
#   cd ~/coliseum && bash deploy/macmini/install.sh
#
# Env overrides (first run only; afterwards edit backend/.env and `coliseumctl restart`):
#   ARENA_MODE=paper|sim|testnet   default paper (real Hyperliquid prices, simulated fills)
#   DATABASE_URL=postgresql+psycopg://...   default: local SQLite at backend/coliseum.db
#   PORT=8000
#
# Idempotent: re-running updates deps and reloads the services, keeps .env and bot keys.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PORT="${PORT:-8000}"
LA="$HOME/Library/LaunchAgents"
mkdir -p "$ROOT/logs" "$LA"
cd "$ROOT"

say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }

# ---- 1. Python 3.11+ ------------------------------------------------------------------------
PY=""
for c in python3.12 python3.13 python3.11 /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    PY="$(command -v "$c")"; break
  fi
done
if [ -z "$PY" ]; then
  if command -v brew >/dev/null 2>&1; then
    say "Installing Python 3.12 with Homebrew"
    brew install python@3.12
    PY="$(brew --prefix python@3.12)/bin/python3.12"
  else
    echo "Need Python 3.11+. Install Homebrew (https://brew.sh) then re-run, or install Python from python.org." >&2
    exit 1
  fi
fi
say "Python: $PY ($("$PY" --version 2>&1))"

# ---- 2. venv + deps ---------------------------------------------------------------------------
if [ ! -x .venv/bin/python ]; then
  say "Creating .venv"
  "$PY" -m venv .venv
fi
say "Installing dependencies"
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q -r requirements.txt

# ---- 3. config ----------------------------------------------------------------------------------
if [ ! -f backend/.env ]; then
  TOKEN="$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(24))')"
  cat > backend/.env <<EOF
# written by deploy/macmini/install.sh — edit and \`coliseumctl restart\`
ARENA_MODE=${ARENA_MODE:-paper}
ADMIN_TOKEN=${TOKEN}
DATABASE_URL=${DATABASE_URL:-sqlite:///./coliseum.db}
HL_BUILDER_FEE_TENTHS_BP=30
HL_PERP_DEXS=["xyz"]
TICK_SECONDS=5
SNAPSHOT_SECONDS=60
PORT=${PORT}
EOF
  chmod 600 backend/.env
  say "Wrote backend/.env (mode=${ARENA_MODE:-paper}, admin token generated)"
else
  say "Keeping existing backend/.env"
  grep -q '^PORT=' backend/.env || echo "PORT=${PORT}" >> backend/.env
fi

# ---- 4. launchd services ------------------------------------------------------------------------
chmod +x deploy/macmini/*.sh deploy/macmini/coliseumctl
write_plist() {  # label, script
  cat > "$LA/$1.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$1</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$ROOT/deploy/macmini/$2</string></array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string>$ROOT/logs/$1.log</string>
  <key>StandardErrorPath</key><string>$ROOT/logs/$1.log</string>
  <key>EnvironmentVariables</key><dict>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    <key>HOME</key><string>$HOME</string>
  </dict>
</dict></plist>
EOF
}
write_plist com.coliseum.api run_api.sh
write_plist com.coliseum.fleet run_fleet.sh

say "Loading services"
for svc in com.coliseum.api com.coliseum.fleet; do
  launchctl bootout "gui/$(id -u)/$svc" >/dev/null 2>&1 || true
  launchctl bootstrap "gui/$(id -u)" "$LA/$svc.plist"
done

# ---- 5. verify ------------------------------------------------------------------------------------
say "Waiting for the API"
for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then break; fi
  sleep 1
done
HEALTH="$(curl -fsS "http://127.0.0.1:${PORT}/health" 2>/dev/null || true)"
if [ -z "$HEALTH" ]; then
  echo "API did not come up. Last log lines:" >&2; tail -n 20 logs/com.coliseum.api.log >&2; exit 1
fi
echo "    $HEALTH"
case "$HEALTH" in *'"markets":0'*)
  echo "    WARNING: no markets loaded — Hyperliquid unreachable? Switch to sim: deploy/macmini/coliseumctl mode sim" ;;
esac

LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"
TS_IP="$(command -v tailscale >/dev/null 2>&1 && tailscale ip -4 2>/dev/null | head -1 || true)"
[ -z "$TS_IP" ] && [ -x /Applications/Tailscale.app/Contents/MacOS/Tailscale ] && TS_IP="$(/Applications/Tailscale.app/Contents/MacOS/Tailscale ip -4 2>/dev/null | head -1 || true)"
echo
say "Coliseum is running (and will restart on reboot)."
echo "    this Mac:   http://localhost:${PORT}"
[ -n "$LAN_IP" ] && echo "    on your LAN: http://${LAN_IP}:${PORT}"
[ -n "$TS_IP" ]  && echo "    Tailscale:   http://${TS_IP}:${PORT}"
echo "    logs:        deploy/macmini/coliseumctl logs      status: deploy/macmini/coliseumctl status"
echo "    public URL:  deploy/macmini/coliseumctl funnel    (Tailscale Funnel → https://<mini>.<tailnet>.ts.net)"
