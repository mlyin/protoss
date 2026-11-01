#!/usr/bin/env python3
"""Two-account Telegram demo. Long polling; no public webhook or signing keys needed.

Set TELEGRAM_BOT_TOKEN and ADMIN_TOKEN locally. `inspect` prints chat/user IDs only.
`run --chat -100123 --users 123,456 [--legion demo]` enables replies in that group.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


class APIError(RuntimeError):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def request(url, body=None, headers=None, timeout=35):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        # Telegram URLs contain the token. Never print the URL or raw exception.
        raise APIError(f"HTTP {exc.code}; check local credentials, permissions and service status", status=exc.code) from None
    except (urllib.error.URLError, TimeoutError, ValueError):
        raise APIError("service unreachable or invalid response") from None


class Telegram:
    def __init__(self, token):
        self.base = "https://api.telegram.org/bot" + token + "/"

    def call(self, method, **body):
        result = request(self.base + method, body, timeout=35)
        if not result.get("ok"):
            raise APIError(f"Telegram {method} failed; inspect the bot configuration locally")
        return result["result"]


class Protoss:
    def __init__(self, base, token):
        self.base = base.rstrip("/")
        self.headers = {"x-admin-token": token}

    def call(self, method, path, body=None):
        if method not in ("GET", "POST"):
            raise ValueError("unsupported method")
        return request(self.base + path, body, self.headers)


class State:
    def __init__(self, path):
        self.path = Path(path)
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {"offset": None, "sent": {}}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", dir=self.path.parent, delete=False) as output:
            json.dump(self.data, output)
            temp = Path(output.name)
        temp.replace(self.path)


def discover_groups(updates):
    """Find actual human senders in groups, never channels, anonymous posts or private chats."""
    groups = {}
    for update in updates:
        message = update.get("message", {})
        chat, user = message.get("chat", {}), message.get("from", {})
        if chat.get("type") not in ("group", "supergroup") or user.get("is_bot") or not user.get("id"):
            continue
        group = groups.setdefault(chat["id"], {"title": chat.get("title", "Demo group"), "users": set()})
        group["users"].add(user["id"])
    return groups


def setup_demo(live=False, wallet_review=False):
    """Run only in the owner's terminal. The token is hidden and never written to disk."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or getpass.getpass("Telegram bot token (hidden): ").strip()
    if not token:
        raise APIError("a bot token is required")
    telegram = Telegram(token)
    me = telegram.call("getMe")
    if telegram.call("getWebhookInfo").get("url"):
        raise APIError("use a dedicated demo bot without a webhook")
    print(f"Add @{me['username']} and both accounts to one private Telegram group.")
    print(f"Send /help@{me['username']} in that group once from EACH account. Keep privacy mode enabled.")
    while True:
        answer = input("Press Enter when both accounts have sent it, or type q to cancel: ").strip()
        if answer.lower() == "q":
            raise APIError("setup cancelled")
        groups = discover_groups(telegram.call("getUpdates", timeout=0, allowed_updates=["message", "callback_query"]))
        if not groups:
            print("No group messages found. Check that the bot is a member and both commands mention its exact username.")
            continue
        for chat_id, group in groups.items():
            title = re.sub(r"[\x00-\x1f\x7f]", "", group["title"])
            print(f"Group {chat_id}: {title}; participant IDs: {','.join(str(user) for user in sorted(group['users']))}")
        chat_id = next(iter(groups)) if len(groups) == 1 else int(input("Enter the intended group ID: "))
        if chat_id not in groups:
            print("That group was not found. Try again.")
            continue
        users = sorted(groups[chat_id]["users"])
        if len(users) != 2:
            print("The demo needs exactly two human accounts in the pending messages. Use a new private demo group.")
            continue
        mode = "Real trades require individual browser wallet approvals." if wallet_review else "Real orders use your authorized API wallets." if live else "Practice trading only."
        print(f"Using group {chat_id} with participant IDs {users[0]} and {users[1]}. {mode}")
        os.environ["TELEGRAM_BOT_TOKEN"] = token
        return chat_id, ",".join(str(user) for user in users)


HELP = ("Protoss practice demo\n/demo (choose a crypto example)\n/idea buy and hold 60% BTC and 40% ETH\n/back 1 (or tap Back this idea)\n"
        "/pledge 20 (your own paper pledge)\n/status\n/join (private wallet connection)\n"
        "Wallet ownership is checked with a signature. Chat backing never authorizes spending.")
HELP_LIVE = ("Protoss\n/demo (choose an idea)\n/idea buy and hold 60% BTC and 40% ETH\n/idea buy and hold xyz:ANT\n/back 1 (or tap Back this idea)\n"
             "/pledge 20 (a real order of that size from your own account)\n/status\n/join (private wallet connection)\n"
             "Orders leave your own Hyperliquid account through an API wallet you authorized. Nothing is pooled. Close any position yourself at any time.")


def friendly(text):
    # Leave URLs intact, including the existing ?legion= parameter.
    replacements = {"thesis": "idea", "theses": "ideas", "legion": "group", "sandbox": "risk checks", "pledged": "confirmed", "paper money": "practice money"}
    parts = re.split(r"(https?://\S+)", text)
    for index in range(0, len(parts), 2):
        for word, replacement in replacements.items():
            parts[index] = re.sub(r"\b" + re.escape(word) + r"\b", replacement, parts[index], flags=re.I)
    return "".join(parts)


class Bridge:
    def __init__(self, telegram, protoss, state, chat, users, username, hid, live=False, wallet_review=False):
        self.telegram, self.protoss, self.state = telegram, protoss, state
        self.chat, self.users, self.username, self.hid = chat, set(users), username, hid
        self.live = live
        self.help = HELP_LIVE if live else HELP
        self.wallet_review = wallet_review

    def send(self, chat, text, key, keyboard=None):
        """Checkpoint every successful chunk. Telegram delivery is at least once across a crash."""
        for index, start in enumerate(range(0, len(text), 3800)):
            part_key = f"{key}:{index}"
            if part_key in self.state.data["sent"]:
                continue
            body = {"chat_id": chat, "text": text[start:start + 3800], "link_preview_options": {"is_disabled": True}}
            if keyboard and index == 0:
                body["reply_markup"] = {"inline_keyboard": keyboard}
            result = self.telegram.call("sendMessage", **body)
            self.state.data["sent"][part_key] = result["message_id"]
            self.state.save()

    def drain(self):
        rows = self.protoss.call("GET", f"/huddle/{self.hid}/outbox")
        if not rows:
            return
        huddle = self.protoss.call("GET", f"/huddle/{self.hid}")
        theses = {t["id"]: t for t in huddle["theses"]}
        for row in rows:
            thesis = theses.get(row.get("thesis_id"))
            keyboard = None
            if row["kind"] == "card" and thesis and thesis["status"] == "proposed":
                keyboard = [[{"text": "Back this idea", "callback_data": f"back:{thesis['n']}"}]]
            text = friendly(row["text"])
            if not self.wallet_review and huddle.get("mode") in ("sim", "paper"):
                text = "Paper demo. No real funds.\n" + text
            self.send(self.chat, text, f"outbox:{row['id']}", keyboard)
            self.protoss.call("POST", f"/huddle/{self.hid}/delivered", {"ids": [row["id"]]})

    def handle(self, update):
        uid = update["update_id"]
        callback = update.get("callback_query")
        message = callback.get("message", {}) if callback else update.get("message", {})
        user = callback.get("from", {}) if callback else message.get("from", {})
        chat = message.get("chat", {})
        user_id = user.get("id")
        private = chat.get("type") == "private" and chat.get("id") == user_id
        if user.get("is_bot") or user_id not in self.users:
            return
        if not private and (chat.get("id") != self.chat or chat.get("type") not in ("group", "supergroup")):
            return
        if self.wallet_review:
            try:
                return self.handle_live(update, user, message, private, callback)
            except APIError as exc:
                if exc.status and 400 <= exc.status < 500 and exc.status != 429:
                    self.send(user_id if private else self.chat,
                        "This request could not be accepted. Use your own review button and the original amount. "
                        "Send /status in the group to check existing requests before creating a new idea.", f"update:{uid}:error")
                    return
                raise
        key = f"update:{uid}"
        if callback:
            payload = callback.get("data", "")
            match = re.fullmatch(r"back:([1-9][0-9]*)", payload)
            if private:
                return
            if match:
                text = f"protoss back {match[1]}"
            elif payload in ("idea:crypto", "idea:bitcoin", "idea:ant"):
                text = "protoss buy and hold " + {"idea:crypto": "60% BTC and 40% ETH", "idea:bitcoin": "BTC", "idea:ant": "xyz:ANT"}[payload]
            else:
                return
        else:
            raw = message.get("text", "").strip()
            match = re.fullmatch(r"/([a-z]+)(?:@([A-Za-z0-9_]+))?(?:\s+([\s\S]*))?", raw)
            if not match or (match[2] and match[2].lower() != self.username.lower()):
                return  # privacy mode works with explicit slash commands; ignore casual chat
            command, argument = match[1], (match[3] or "").strip()
            if private:
                if command != "start" or argument != f"join_{self.chat}":
                    self.send(user_id, "Use /join in the demo group to connect your own wallet.", key)
                    return
                if f"{key}:0" in self.state.data["sent"]:
                    return  # do not rotate an already-delivered connection link after a restart
                link = self.protoss.call("POST", "/telegram/links", {"huddle_id": self.hid,
                    "telegram_user_id": str(user_id), "display_name": str(user.get("first_name") or "Participant")[:80]})
                self.send(user_id, "Your private Protoss wallet link expires in 15 minutes. Open it in your wallet browser or a browser with your wallet extension. Sign the ownership message only. No deposit or trade is authorized.", key,
                          [[{"text": "Connect my wallet", "url": link["url"]}]])
                return
            if command in ("start", "help"):
                self.send(self.chat, self.help, key)
                return
            if command == "demo":
                intro = ("Choose an idea. You and your friend each confirm your own amount with /pledge; each order leaves your own account. Perpetual markets, not coin ownership."
                         if self.live else
                         "Choose a practice idea. You and your friend each choose your own amount. No real money moves. These examples use perpetual markets, not coin ownership.")
                self.send(self.chat, intro, key,
                    [[{"text": "60% Bitcoin + 40% Ethereum", "callback_data": "idea:crypto"}],
                     [{"text": "Bitcoin only", "callback_data": "idea:bitcoin"}],
                     [{"text": "ANT (xyz) only", "callback_data": "idea:ant"}]])
                return
            if command == "join":
                url = f"https://t.me/{self.username}?start=join_{self.chat}"
                self.send(self.chat, "Open the bot privately to connect your own wallet. Each participant uses their own Telegram account. A verified wallet is not a verified deposit.", key,
                          [[{"text": "Connect my wallet privately", "url": url}]])
                return
            if command == "status":
                connections = self.protoss.call("GET", f"/telegram/huddles/{self.hid}/connections")
                lines = [f"tg:{r['telegram_user_id']}: wallet ownership verified ({r['wallet'][:8]}…{r['wallet'][-4:]}). Deposit not checked." for r in connections]
                self.send(self.chat, "Wallet connections\n" + ("\n".join(lines) or "No verified wallets yet. Each participant can use /join."), key)
                text = "protoss status"
            elif command == "idea" and argument:
                text = "protoss " + argument
            elif command == "back" and re.fullmatch(r"[1-9][0-9]*", argument):
                text = "protoss back " + argument
            elif command == "pledge" and re.fullmatch(r"\d+(?:\.\d{1,2})?", argument) and 0 < float(argument) <= 1000:
                text = "in for " + argument
            else:
                self.send(self.chat, self.help, key)
                return
        self.protoss.call("POST", f"/huddle/{self.hid}/messages", {"sender": f"tg:{user_id}", "text": text[:2000],
                          "guid": f"tg-update:{uid}"})
        self.drain()
        if callback:
            self.telegram.call("answerCallbackQuery", callback_query_id=callback["id"], text="Recorded." if self.live else "Demo step recorded. No funds moved.")

    def handle_live(self, update, user, message, private, callback):
        key = f"update:{update['update_id']}"
        if callback:
            self.telegram.call("answerCallbackQuery", callback_query_id=callback["id"],
                               text="Choose your own amount with /pledge 20. Wallet approval is required.")
            return
        raw = message.get("text", "").strip()
        match = re.fullmatch(r"/([a-z]+)(?:@([A-Za-z0-9_]+))?(?:\s+([\s\S]*))?", raw)
        if not match or (match[2] and match[2].lower() != self.username.lower()):
            return
        command, argument = match[1], (match[3] or "").strip()
        if private:
            if command != "start" or not re.fullmatch(r"trade_[a-f0-9]{32}", argument):
                self.send(user["id"], "Use the Review my trade button in your group to get a personal link.", key)
                return
            if f"{key}:0" in self.state.data["sent"]:
                return
            link = self.protoss.call("POST", f"/live/intents/{argument[6:]}/link",
                {"telegram_user_id": str(user["id"]), "huddle_id": self.hid})
            self.send(user["id"], "Your private real-trade review link. Open it on the Mac running Protoss with your wallet extension, "
                      "or use the configured HTTPS site. Review the price, wallet and amount. Only your wallet approvals can place an order.", key,
                      [[{"text": "Review my trade", "url": link["url"]}]])
            return
        if command == "idea":
            asset = re.fullmatch(r"(?:buy(?: and hold)?\s+)?(ANT|Anthropic|xyz:ANT|BTC|ETH)", argument, re.I)
            if not asset:
                self.send(self.chat, "Start with one market: /idea buy and hold ANT (or BTC, ETH). Each participant approves a separate buy.", key)
                return
            idea = self.protoss.call("POST", "/live/ideas", {"huddle_id": self.hid,
                "request_id": f"telegram:{self.chat}:{update['update_id']}", "market": asset[1]})
            self.send(self.chat, f"Buy {idea['market']} · idea {idea['id']}\nEach person keeps their own position. "
                "Send /pledge 20 to review a buy of up to $20. The review uses a live quote and 1× cross margin, with fees additional. "
                "Your wallet must approve it. ANT is an Anthropic-linked perpetual, not shares.", key)
        elif command == "pledge":
            if not re.fullmatch(r"\d+(?:\.\d{1,2})?", argument) or not 12 <= float(argument) <= 100:
                self.send(self.chat, "Choose $12 to $100 for this first version, for example /pledge 20.", key)
                return
            ideas = self.protoss.call("GET", f"/live/groups/{self.hid}")
            if not ideas:
                self.send(self.chat, "Start an idea first: /idea buy and hold ANT", key)
                return
            intent = self.protoss.call("POST", "/live/intents", {"idea_id": ideas[0]["id"], "telegram_user_id": str(user["id"]),
                "display_name": str(user.get("first_name") or "Participant")[:80], "budget": argument})
            self.send(self.chat, f"{user.get('first_name') or 'Participant'}: review up to ${intent['budget']} of {ideas[0]['market']}. "
                      "No order has been placed by this message. Open your private link, then press Start.", key,
                      [[{"text": "Review my trade privately", "url": f"https://t.me/{self.username}?start=trade_{intent['id']}"}]])
        elif command == "status":
            self.protoss.call("POST", f"/live/groups/{self.hid}/verify", {})
            ideas = self.protoss.call("GET", f"/live/groups/{self.hid}")
            labels = {"draft": "waiting for wallet review", "prepared": "awaiting exchange verification", "filled": "fill verified", "partial": "partial fill verified"}
            lines = [f"Idea {i['id']} · {i['market']}: " + ("; ".join(
                f"{p['participant']} (tg:{p['telegram_user_id']}), up to ${p['budget']}: {labels.get(p['status'], p['status'])}"
                for p in i['participants']) or "waiting for participants") for i in ideas]
            self.send(self.chat, "Real-trade requests\n" + ("\n".join(lines) or "No requests yet."), key)
            self.drain()
        else:
            self.send(self.chat, "Protoss · individual wallet approvals\n/idea buy and hold ANT\n/pledge 20 (each person chooses their own amount)\n/status\n"
                "A chat message never places an order. Open the private review link and approve from your own wallet. No automatic copying or closing.", key)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("inspect", help="read bot/webhook status and pending chat/user IDs, without sending")
    run = sub.add_parser("run", help="enable the demo bot in one allowlisted group")
    run.add_argument("--chat", required=True, type=int)
    run.add_argument("--users", required=True, help="exactly two numeric Telegram user IDs, comma separated")
    run.add_argument("--legion")
    run.add_argument("--state", help="local restart checkpoint; never store this in git")
    args = parser.parse_args()
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        parser.error("set TELEGRAM_BOT_TOKEN locally; never paste it into chat")
    telegram = Telegram(token)
    try:
        me = telegram.call("getMe")
        webhook = telegram.call("getWebhookInfo")
        if args.command == "inspect":
            updates = telegram.call("getUpdates", timeout=0, allowed_updates=["message", "callback_query"]) if not webhook.get("url") else []
            print(json.dumps({"bot": me["username"], "webhook_configured": bool(webhook.get("url")),
                "pending": [{"chat_id": u["message"]["chat"]["id"], "user_id": u["message"].get("from", {}).get("id"),
                             "chat_type": u["message"]["chat"]["type"]} for u in updates if "message" in u]}, indent=2))
            return
        if webhook.get("url"):
            parser.error("this bot has a webhook; use a dedicated demo bot or remove its webhook locally first")
        if not re.fullmatch(r"[1-9][0-9]*,[1-9][0-9]*", args.users):
            parser.error("--users needs exactly two positive user IDs separated by a comma")
        users = [int(value) for value in args.users.split(",")]
        if args.chat >= 0 or len(set(users)) != 2:
            parser.error("use a negative group chat ID and two distinct participant IDs")
        admin = os.environ.get("ADMIN_TOKEN", "")
        if not admin:
            parser.error("set ADMIN_TOKEN locally to match the Protoss API")
        protoss = Protoss(os.environ.get("PROTOSS_API", "http://127.0.0.1:8000"), admin)
        health = protoss.call("GET", "/health")
        group = telegram.call("getChat", chat_id=args.chat)
        if group.get("type") not in ("group", "supergroup"):
            parser.error("the selected Telegram chat must be a group")
        huddle = protoss.call("POST", "/huddle", {"chat_id": f"telegram:{args.chat}", "title": group.get("title", "Protoss demo"), "org_slug": args.legion, "quorum": 2})
        if args.legion and huddle.get("org_slug") != args.legion:
            parser.error("selected legion was not found; create it in Protoss before running")
        path = args.state or str(Path.home() / ".protoss" / f"telegram-{me['id']}-{args.chat}.json")
        state = State(path)
        identity = {"bot": me["id"], "chat": args.chat, "users": sorted(users)}
        if "identity" in state.data and state.data["identity"] != identity:
            parser.error("checkpoint belongs to another bot/group/participant pair; use a different --state")
        state.data["identity"] = identity
        if state.data["offset"] is None:
            latest = telegram.call("getUpdates", offset=-1, timeout=0, allowed_updates=["message", "callback_query"])
            state.data["offset"] = latest[-1]["update_id"] + 1 if latest else 0
            state.save()  # first start ignores old commands; send fresh commands after this point
        live = health.get("mode") == "copies"
        wallet_review = health.get("telegram_live_enabled", False)
        if live and wallet_review:
            parser.error("API-wallet trading and browser wallet review must run separately")
        bridge = Bridge(telegram, protoss, state, args.chat, users, me["username"], huddle["id"], live=live, wallet_review=wallet_review)
        mode_label = "individual wallet approval" if wallet_review else health["mode"]
        print(f"Protoss Telegram bridge running in {mode_label} mode. Send fresh commands in the selected group. Ctrl-C stops it.")
        while True:
            try:
                if wallet_review:
                    protoss.call("POST", f"/live/groups/{huddle['id']}/verify", {})
                bridge.drain()
                updates = telegram.call("getUpdates", offset=state.data["offset"], timeout=20, allowed_updates=["message", "callback_query"])
                for update in updates:
                    bridge.handle(update)
                    state.data["offset"] = update["update_id"] + 1
                    state.save()
            except APIError as exc:
                print(f"{exc}; retrying in 3 seconds", flush=True)
                time.sleep(3)
    except APIError as exc:
        parser.exit(1, str(exc) + "\n")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
