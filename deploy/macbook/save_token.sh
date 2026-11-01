#!/usr/bin/env bash
# Save the Telegram bot token for the launchd bot (com.protoss.telegram), once. Reads it hidden; never prints or logs it.
# The bot service waits for this file and starts within a few seconds of it appearing.
set -euo pipefail
read -rsp "Bot token (hidden): " T
echo
[ -n "$T" ] || { echo "Nothing pasted, so nothing was saved." >&2; exit 1; }
mkdir -p "$HOME/.protoss"
umask 077
printf 'TELEGRAM_BOT_TOKEN=%s\n' "$T" > "$HOME/.protoss/telegram.env"
unset T
echo "saved to ~/.protoss/telegram.env (readable only by you). The bot starts within a few seconds."
