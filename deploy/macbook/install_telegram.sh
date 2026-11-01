#!/usr/bin/env bash
# Install the live Telegram bot as a launchd agent on this Mac. Re-running is safe (reloads it).
#   deploy/macbook/install_telegram.sh <chat id> <user id,user id>
# The token is never an argument: save it once to ~/.protoss/telegram.env (TELEGRAM_BOT_TOKEN=...), mode 600.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CHAT="${1:?chat id}"; USERS="${2:?comma-separated Telegram user ids}"
LABEL=com.protoss.telegram; PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/.protoss"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$ROOT/deploy/macbook/run_telegram.sh</string></array>
  <key>EnvironmentVariables</key><dict>
    <key>PROTOSS_TG_CHAT</key><string>$CHAT</string>
    <key>PROTOSS_TG_USERS</key><string>$USERS</string>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string>$HOME/.protoss/telegram-live.log</string>
  <key>StandardErrorPath</key><string>$HOME/.protoss/telegram-live.log</string>
</dict></plist>
PL
launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "$LABEL loaded. Log: ~/.protoss/telegram-live.log. Stop: launchctl bootout gui/$(id -u)/$LABEL"
