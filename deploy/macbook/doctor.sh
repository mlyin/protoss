#!/usr/bin/env bash
# Read-only health check for the live Telegram bot on this Mac. Prints one OK / FAIL line per check and changes nothing.
#
#   ~/Documents/protoss2/deploy/macbook/doctor.sh
#
# The token is read from ~/.protoss/telegram.env only to ask Telegram about the bot; it is never printed.
set -uo pipefail
LABEL=com.protoss.telegram
fails=0
ok()   { printf 'OK    %s\n' "$*"; }
bad()  { printf 'FAIL  %s\n' "$*"; fails=$((fails + 1)); }
note() { printf '      %s\n' "$*"; }

[ -s "$HOME/.protoss/telegram.env" ] && ok "token file ~/.protoss/telegram.env exists" \
  || bad "no token file: run ~/Documents/protoss2/deploy/macbook/save_token.sh in a terminal"

svc="$(launchctl print "gui/$(id -u)/$LABEL" 2>/dev/null)"
if [ -z "$svc" ]; then
  bad "launchd service $LABEL is not loaded: ~/protoss-bot/deploy/macbook/install_telegram.sh <chat id> <user ids>"
else
  state="$(printf '%s\n' "$svc" | awk '/^\tstate = /{print $3; exit}')"
  [ "$state" = running ] && ok "launchd service $LABEL is running" || bad "launchd service $LABEL is $state"
  chat="$(printf '%s\n' "$svc" | awk -F'=> ' '/PROTOSS_TG_CHAT/{print $2; exit}')"
fi

if pgrep -f 'scripts/telegram_bridge.py' >/dev/null; then ok "bot process is polling Telegram"
else bad "no bot process: see the last lines of ~/.protoss/telegram-live.log"; fi
last="$(grep -E '^=== start' "$HOME/.protoss/telegram-live.log" 2>/dev/null | tail -1)"
last="${last#=== }"; [ -n "$last" ] && note "${last% ===}"

if [ -d "$HOME/protoss-bot/.git" ]; then
  ok "bot runs from ~/protoss-bot at $(git -C "$HOME/protoss-bot" log --oneline -1 | cut -c1-70)"
else bad "~/protoss-bot is missing: git clone ~/Documents/protoss2 ~/protoss-bot"; fi

if pmset -g assertions 2>/dev/null | grep -q 'caffeinate asserting'; then ok "the Mac is held awake while the bot runs"
else bad "nothing keeps the Mac awake: restart the service (launchctl kickstart -k gui/$(id -u)/$LABEL)"; fi
power="$(pmset -g batt 2>/dev/null | sed -n 1p)"
case "$power" in *Battery*) note "on battery: keep it plugged in, and keep the lid open (a closed lid still sleeps it)";; esac

if curl -fsS -m 5 http://127.0.0.1:8001/health >/dev/null 2>&1; then ok "the bot's local API answers on :8001"
else bad "the bot's local API is not answering on :8001"; fi

if [ -s "$HOME/.protoss/telegram.env" ]; then
  token="$(sed -n 's/^TELEGRAM_BOT_TOKEN=//p' "$HOME/.protoss/telegram.env" | head -1)"
  me="$(curl -fsS -m 10 "https://api.telegram.org/bot${token}/getMe" 2>/dev/null)"
  name="$(printf '%s' "$me" | python3 -c 'import json,sys; r=json.load(sys.stdin).get("result",{}); print("@"+r.get("username",""), r.get("id",""))' 2>/dev/null)"
  [ -n "$name" ] && ok "token belongs to $name" || bad "Telegram rejected the saved token"
  hook="$(curl -fsS -m 10 "https://api.telegram.org/bot${token}/getWebhookInfo" 2>/dev/null | python3 -c 'import json,sys; print(bool(json.load(sys.stdin).get("result",{}).get("url")))' 2>/dev/null)"
  [ "$hook" = False ] && ok "no webhook is taking the bot's messages" || bad "a webhook is set: messages go there, not to this bot"
  if [ -n "${chat:-}" ]; then
    bot_id="${name##* }"
    status="$(curl -fsS -m 10 "https://api.telegram.org/bot${token}/getChatMember?chat_id=${chat}&user_id=${bot_id}" 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin).get("result",{}).get("status",""))' 2>/dev/null)"
    [ "$status" = administrator ] && ok "the bot is an administrator in the group, so it sees every message" \
      || bad "the bot is '${status:-unknown}' in the group: make it an administrator or it only sees slash commands"
  fi
  unset token
fi

if health="$(curl -fsS -m 10 https://api.protoss.trade/health 2>/dev/null)"; then ok "public API api.protoss.trade answers ($health)"
else bad "public API api.protoss.trade is not answering (the Mac mini)"; fi

echo
[ "$fails" = 0 ] && echo "All checks passed." || echo "$fails check(s) failed."
exit "$fails"
