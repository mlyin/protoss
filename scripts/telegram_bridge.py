#!/usr/bin/env python3
"""Two-account Telegram demo. Long polling; no public webhook or signing keys needed.

Set TELEGRAM_BOT_TOKEN and ADMIN_TOKEN locally. `inspect` reads bot/webhook status without polling.
`run --chat -100123 --users 123,456 [--legion demo]` enables replies in that group.
"""
from __future__ import annotations

import argparse
import getpass
import io
import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path


class APIError(RuntimeError):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def acquire_poller_lock(bot_id, directory=None):
    """One polling process per bot on this host, even with different checkpoint paths."""
    directory = Path(directory) if directory is not None else Path.home() / ".protoss"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"telegram-{int(bot_id)}.lock"
    handle = os.fdopen(os.open(path, os.O_RDWR | os.O_CREAT, 0o600), "r+b")
    try:
        if os.name == "nt":
            import msvcrt
            if path.stat().st_size == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise APIError("Another local process is using this bot. Stop that process before starting another poller.") from None
    return handle  # Closing the handle (including process exit) releases the OS lock.


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

    def upload(self, method, fields, name, filename, data, mime="image/png"):
        """multipart/form-data for sendPhoto: the card PNG comes from the local API, which Telegram cannot reach by URL."""
        boundary = "protoss" + uuid.uuid4().hex
        out = io.BytesIO()
        for key, value in fields.items():
            out.write(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n'.encode())
            out.write((value if isinstance(value, str) else json.dumps(value)).encode() + b"\r\n")
        out.write(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\nContent-Type: {mime}\r\n\r\n'.encode())
        out.write(data + f"\r\n--{boundary}--\r\n".encode())
        req = urllib.request.Request(self.base + method, data=out.getvalue(), headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        try:
            with urllib.request.urlopen(req, timeout=35) as response:
                result = json.load(response)
        except urllib.error.HTTPError as exc:
            raise APIError(f"HTTP {exc.code}; check local credentials, permissions and service status", status=exc.code) from None
        except (urllib.error.URLError, TimeoutError, ValueError):
            raise APIError("service unreachable or invalid response") from None
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

    def get_bytes(self, path):
        try:
            with urllib.request.urlopen(urllib.request.Request(self.base + path, headers=self.headers), timeout=20) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError):
            raise APIError("card image unavailable") from None


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


def bind_identity(state, identity, previous_chat=None):
    """Permit only an explicit group upgrade; keep the existing update/delivery checkpoint."""
    old = state.data.get("identity")
    expected_old = {**identity, "chat": previous_chat}
    if old is not None and old != identity and (previous_chat is None or old != expected_old):
        raise APIError("checkpoint belongs to another bot/group/participant pair; use a different --state")
    state.data["identity"] = identity
    state.save()


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
    with acquire_poller_lock(me["id"]):
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


# The four ideas Protoss demos, in order (same sentences as the Lab's examples). Button label, callback, what the chat hears.
IDEAS = [
    ("Buy XMR on every major hack", "idea:xmr", "Let's buy XMR every time a major company gets hacked"),
    ("Robots take over: buy Unitree", "idea:unitree", "I think robots are going to take over the world"),
    ("Anthropic bubble pops: short ANT", "idea:ant", "The Anthropic bubble is going to pop"),
    ("Dwarkesh is right: NVDA each episode", "idea:dwarkesh", "Dwarkesh is always right. Trade every new episode"),
]

HELP = ("Protoss practice demo\n/demo (choose one of the four ideas)\n/idea I think robots are going to take over the world\n/back 1 (or tap Back this idea)\n"
        "/pledge 20 (your own paper pledge)\n/status\n/join (private wallet connection)\n"
        "Wallet ownership is checked with a signature. Chat backing never authorizes spending.")
HELP_LIVE = ("Protoss listens to this chat.\n"
             "Say an idea, or tap /demo for the four: XMR on every hack, robots (Unitree), the Anthropic bubble (short ANT), NVDA on each new Dwarkesh episode.\n"
             "Back it: thumbs up the card, tap \"I'm in for $20\", or say \"in for 11\" with your own amount.\n"
             "Each amount is a real order from your own Hyperliquid account, through the API wallet you authorized. Nothing is pooled; close a position yourself any time.\n"
             "Also: \"my position\" or /mine (yours only), \"close idea 1\" (closes your own), \"show the events\", \"protoss status\", \"protoss score\", \"protoss hack: <what happened>\".")


# this bot's own links: anything on the local API, and Protoss page shapes (/t/1, /h/x, /l/x, /#/feed) anywhere.
# Links to news sources (a hack report) stay.
OWN_LINK = re.compile(r"[ \t]*\(?https?://(?:(?:127\.0\.0\.1|localhost)(?::\d+)?\S*|[^\s/]+/(?:[thl]/|#/)\S*)")


def tidy(text, names=None):
    """Telegram copy: drop links to this bot's own local API (nobody else can open them) and show names, not tg:<id>."""
    app = os.environ.get("APP_URL", "")
    if app and not re.match(r"https?://(127\.0\.0\.1|localhost)", app):
        text = re.sub(r"[ \t]*" + re.escape(app.rstrip("/")) + r"\S*", "", text)
    text = OWN_LINK.sub("", text)
    text = text.replace("Every fill is public:", "Every fill is public on Hyperliquid.")
    text = re.sub(r"\btg:(\d+)", lambda m: (names or {}).get(m.group(1), "a friend"), text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def friendly(text):
    # Leave URLs intact, including the existing ?legion= parameter.
    replacements = {"thesis": "idea", "theses": "ideas", "legion": "group", "sandbox": "risk checks", "pledged": "confirmed", "paper money": "practice money"}
    parts = re.split(r"(https?://\S+)", text)
    for index in range(0, len(parts), 2):
        for word, replacement in replacements.items():
            parts[index] = re.sub(r"\b" + re.escape(word) + r"\b", lambda m, r=replacement: r[:1].upper() + r[1:] if m.group(0)[:1].isupper() else r,
                                  parts[index], flags=re.I)
    return "".join(parts)


class Bridge:
    def __init__(self, telegram, protoss, state, chat, users, username, hid, live=False, wallet_review=False):
        self.telegram, self.protoss, self.state = telegram, protoss, state
        self.chat, self.users, self.username, self.hid = chat, set(users), username, hid
        self.live = live
        self.help = HELP_LIVE if live else HELP
        self.wallet_review = wallet_review

    def private_reply(self, update, user, message, callback):
        """Private research never reads a group or reaches its approval/order handlers."""
        key = f"update:{update['update_id']}"
        chat = user["id"]
        raw = message.get("text", "").strip()
        menu = [[{"text": label,
                  "callback_data": data.replace("idea:", "research:")}]
                for label, data, _ in IDEAS]
        if callback:
            self.telegram.call("answerCallbackQuery", callback_query_id=callback["id"], text="Research only. No order placed.")
            raw = next((said for _, data, said in IDEAS
                        if data.replace("idea:", "research:") == callback.get("data")), "")
        command = re.fullmatch(r"/([a-z]+)(?:@([A-Za-z0-9_]+))?(?:\s+([\s\S]*))?", raw)
        if command and command[2] and command[2].lower() != self.username.lower():
            return
        if command and command[1] in ("positions", "status", "join"):
            self.send(chat, "Connect your own wallet on protoss.trade/app/ to see its real positions. "
                      "I don't share group members' wallets or positions in this chat.", key,
                      [[{"text": "My positions", "url": "https://protoss.trade/app/"}]])
            return
        if command and command[1] in ("pledge", "back", "buy", "sell", "trade"):
            self.send(chat, "This private chat is for research. No order was placed and nothing was posted to your group.", key)
            return
        if command and command[1] == "idea":
            raw = (command[3] or "").strip()
        elif command or raw.lower() in ("", "hi", "hey", "hello", "start", "help", "demo", "yo", "test"):
            self.send(chat, "I'm here. Choose one of the four ideas or describe a strategy to research. "
                      "Private messages stay here. Research does not place an order.", key, menu)
            return
        if "dwarkesh" in raw.lower():
            self.send(chat, "For each new Dwarkesh episode: extract its claims, find a related tradable market, "
                      "and review the evidence before proposing a trade. There is no automatic NVDA purchase. "
                      "Episode monitoring and transcript analysis are not connected yet. No trade was placed.", key)
            return
        # The Lab is read-only. Never create a private huddle against a live copies engine.
        if not self.live:
            self.send(chat, "Real-data research is not available on this bot's current backend. "
                      "You can view live markets on protoss.trade. No simulated result or order was created.", key, menu)
            return
        try:
            result = self.protoss.call("POST", "/lab/chat", {"message": raw[:2000]})
            reply = result.get("reply") or "Research returned no result. Try a market and holding period."
            if result.get("kind") == "backtest" and "simulated" in reply.lower():
                reply = "Real market history is unavailable. I won't substitute a simulated performance result."
        except APIError:
            reply = "Research is unavailable right now. Please try again shortly."
        self.send(chat, reply + "\nResearch only. No order placed and nothing posted to your group.", key)

    def send_card(self, chat, png, caption, key, keyboard=None, reply_to=None):
        """The card as one photo: the backtest chart with the text as its caption. Falls back to text on any failure."""
        if f"{key}:0" in self.state.data["sent"]:
            return
        fields = {"chat_id": str(chat), "caption": caption}
        if keyboard:
            fields["reply_markup"] = {"inline_keyboard": keyboard}
        if reply_to:
            fields["reply_parameters"] = {"message_id": reply_to, "allow_sending_without_reply": True}
        try:
            result = self.telegram.upload("sendPhoto", fields, "photo", "idea.png", png)
        except APIError:
            return self.send(chat, caption, key, keyboard, reply_to)
        self.state.data["sent"][f"{key}:0"] = result["message_id"]
        self.state.save()

    def send(self, chat, text, key, keyboard=None, reply_to=None):
        """Checkpoint every successful chunk. Telegram delivery is at least once across a crash. reply_to threads the
        answer under the message it answers, so the group sees who it is talking to."""
        for index, start in enumerate(range(0, len(text), 3800)):
            part_key = f"{key}:{index}"
            if part_key in self.state.data["sent"]:
                continue
            body = {"chat_id": chat, "text": text[start:start + 3800], "link_preview_options": {"is_disabled": True}}
            if keyboard and index == 0:
                body["reply_markup"] = {"inline_keyboard": keyboard}
            if reply_to and index == 0:
                body["reply_parameters"] = {"message_id": reply_to, "allow_sending_without_reply": True}
            result = self.telegram.call("sendMessage", **body)
            self.state.data["sent"][part_key] = result["message_id"]
            self.state.save()

    def handle_reaction(self, uid, r):
        """A thumbs up (or heart, fire, 100) on a card from an allowed participant backs that idea."""
        user = r.get("user") or {}
        chat = r.get("chat") or {}
        if user.get("is_bot") or user.get("id") not in self.users or chat.get("id") != self.chat:
            return
        if user.get("first_name"):
            self.state.data.setdefault("names", {})[str(user["id"])] = user["first_name"][:40]
        n = self.state.data.get("cards", {}).get(str(r.get("message_id")))
        if not n:
            return
        emojis = {x.get("emoji") for x in r.get("new_reaction", []) if x.get("type") == "emoji"}
        if not emojis & {"\U0001F44D", "\u2764\ufe0f", "\u2764", "\U0001F525", "\U0001F4AF", "\U0001F680"}:
            return
        self.protoss.call("POST", f"/huddle/{self.hid}/messages", {"sender": f"tg:{user['id']}", "text": f"protoss back {n}", "guid": f"tg-update:{uid}"})
        self.drain(reply_to=r.get("message_id"))

    def drain(self, reply_to=None):
        """Post what the backend has to say. reply_to is the message (or card) that caused it; timed posts have none."""
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
                if ((thesis.get("test") or {}).get("events") or {}).get("per_event"):
                    keyboard[0].append({"text": "Show the events", "callback_data": f"events:{thesis['n']}"})
                keyboard.append([{"text": f"I'm in for ${amount}", "callback_data": f"in:{thesis['n']}:{amount}"} for amount in (10, 20, 50)])
            elif row["kind"] == "result" and re.search(r"order filled| fired on ", row["text"]):
                keyboard = [[{"text": "My position", "callback_data": "mine"}]]
            elif row["kind"] == "mine":
                keyboard = [[{"text": "My positions", "url": "https://protoss.trade/app/"}]]
            # Older backends may still have private position details queued as
            # shared `mine` rows. Never relay those details into the group.
            shared_text = ("Your positions are private. Connect your own wallet to view them: https://protoss.trade/app/"
                           if row["kind"] == "mine" else row["text"])
            text = shared_text if row["kind"] == "mine" else tidy(friendly(shared_text), self.state.data.get("names"))
            if not self.wallet_review and huddle.get("mode") in ("sim", "paper"):
                text = "Paper demo. No real funds.\n" + text
            png = None
            if row["kind"] == "card" and thesis and len(text) <= 1024 and hasattr(self.telegram, "upload"):
                try:
                    png = self.protoss.get_bytes(f"/og/t/{thesis['id']}.png?format=phone")
                except (APIError, AttributeError):
                    png = None
            if png:
                self.send_card(self.chat, png, text, f"outbox:{row['id']}", keyboard, reply_to)
            else:
                self.send(self.chat, text, f"outbox:{row['id']}", keyboard, reply_to)
            if keyboard and row["kind"] == "card":
                mid = self.state.data["sent"].get(f"outbox:{row['id']}:0")
                if mid:
                    self.state.data.setdefault("cards", {})[str(mid)] = thesis["n"]
                    self.state.save()
            self.protoss.call("POST", f"/huddle/{self.hid}/delivered", {"ids": [row["id"]]})

    def handle(self, update):
        uid = update["update_id"]
        if "message_reaction" in update:
            return self.handle_reaction(uid, update["message_reaction"])
        callback = update.get("callback_query")
        message = callback.get("message", {}) if callback else update.get("message", {})
        user = callback.get("from", {}) if callback else message.get("from", {})
        chat = message.get("chat", {})
        user_id = user.get("id")
        private = chat.get("type") == "private" and chat.get("id") == user_id
        if user.get("is_bot") or not user_id:
            return
        # Preserve existing personal wallet-review links for invited users only.
        raw = message.get("text", "").strip()
        personal_link = (not callback and user_id in self.users and
                         (raw == f"/start join_{self.chat}" or
                          (self.wallet_review and re.fullmatch(r"/start trade_[a-f0-9]{32}", raw))))
        if private and not personal_link:
            return self.private_reply(update, user, message, callback)
        if user_id not in self.users:
            return
        if user.get("first_name") and self.state.data.setdefault("names", {}).get(str(user_id)) != user["first_name"][:40]:
            self.state.data["names"][str(user_id)] = user["first_name"][:40]  # shown instead of tg:<id>
            self.state.save()
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
            elif events := re.fullmatch(r"events:([1-9][0-9]*)", payload):
                text = f"protoss events {events[1]}"
            elif amount := re.fullmatch(r"in:([1-9][0-9]*):([1-9][0-9]{0,2})", payload):
                text = f"protoss in {amount[1]} for {amount[2]}"
            elif payload == "mine":
                text = "protoss mine"
            elif close := re.fullmatch(r"close:([1-9][0-9]*)", payload):
                text = f"protoss close {close[1]}"
            elif idea := next((said for _, data, said in IDEAS if data == payload), None):
                text = "protoss " + idea
            else:
                return
        else:
            raw = message.get("text", "").strip()
            if raw.lower() in ("hi", "hey", "hello", "yo", "test"):
                self.send(self.chat, "I'm here. Send /demo for the four ideas, or describe a strategy in this group. "
                          "You can also message me privately for research.", key)
                return
            match = re.fullmatch(r"/([a-z]+)(?:@([A-Za-z0-9_]+))?(?:\s+([\s\S]*))?", raw)
            if not match or (match[2] and match[2].lower() != self.username.lower()):
                # Plain chat. The engine decides whether it is a thesis ("let's buy unitree, robots are taking over"),
                # a backing ("in", "lfg", "in for 11", "$11 each") or nothing. Needs the bot to see group messages:
                # make it a group admin, or turn privacy mode off in BotFather and re-add it.
                if private or not raw or raw.startswith("/"):
                    return
                self.protoss.call("POST", f"/huddle/{self.hid}/messages", {"sender": f"tg:{user_id}", "text": raw[:2000], "guid": f"tg-update:{uid}"})
                self.drain(reply_to=message.get("message_id"))
                return
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
                intro = ("Pick one of the four. I'll post the backtest; thumbs up to back it, then each of you says \"in for 20\" with your own amount. "
                         "Each order leaves your own account. These are perpetual markets, not coins or shares."
                         if self.live else
                         "Choose a practice idea. You and your friend each choose your own amount. No real money moves. These examples use perpetual markets, not coin ownership.")
                self.send(self.chat, intro, key, [[{"text": label, "callback_data": data}] for label, data, _ in IDEAS])
                return
            if command == "join":
                url = f"https://t.me/{self.username}?start=join_{self.chat}"
                self.send(self.chat, "Open the bot privately to connect your own wallet. Each participant uses their own Telegram account. A verified wallet is not a verified deposit.", key,
                          [[{"text": "Connect my wallet privately", "url": url}]])
                return
            if command == "status":
                if not self.live:  # live accounts come from wallets.json, not /join, so this block would only confuse
                    connections = self.protoss.call("GET", f"/telegram/huddles/{self.hid}/connections")
                    lines = [f"tg:{r['telegram_user_id']}: wallet ownership verified ({r['wallet'][:8]}…{r['wallet'][-4:]}). Deposit not checked." for r in connections]
                    self.send(self.chat, "Wallet connections\n" + ("\n".join(lines) or "No verified wallets yet. Each participant can use /join."), key)
                text = "protoss status"
            elif command == "mine":
                text = "protoss mine"
            elif command == "close" and re.fullmatch(r"[1-9][0-9]*", argument):
                text = "protoss close " + argument
            elif command == "events":
                text = "protoss events" + (" " + argument if re.fullmatch(r"[1-9][0-9]*", argument) else "")
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
        self.drain(reply_to=message.get("message_id"))  # a command answers under it; a button tap answers under its card
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
    inspect = sub.add_parser("inspect", help="read bot/webhook status without polling or sending")
    inspect.add_argument("--pending", action="store_true", help="inspect pending chat IDs only while the bot is stopped")
    run = sub.add_parser("run", help="enable the demo bot in one allowlisted group")
    run.add_argument("--chat", required=True, type=int)
    run.add_argument("--users", required=True, help="exactly two numeric Telegram user IDs, comma separated")
    run.add_argument("--legion")
    run.add_argument("--state", help="local restart checkpoint; never store this in git")
    run.add_argument("--previous-chat", type=int, help="original group ID after a Telegram supergroup upgrade; preserve its huddle")
    args = parser.parse_args()
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        parser.error("set TELEGRAM_BOT_TOKEN locally; never paste it into chat")
    telegram = Telegram(token)
    lock = None
    try:
        me = telegram.call("getMe")
        webhook = telegram.call("getWebhookInfo")
        if args.command == "inspect":
            updates = []
            if args.pending and not webhook.get("url"):
                with acquire_poller_lock(me["id"]):
                    updates = telegram.call("getUpdates", timeout=0, allowed_updates=["message", "callback_query"])
            print(json.dumps({"bot": me["username"], "webhook_configured": bool(webhook.get("url")),
                "pending": [{"chat_id": u["message"]["chat"]["id"], "user_id": u["message"].get("from", {}).get("id"),
                             "chat_type": u["message"]["chat"]["type"]} for u in updates if "message" in u]}, indent=2))
            return
        lock = acquire_poller_lock(me["id"])
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
        if args.previous_chat is not None and args.previous_chat >= 0:
            parser.error("--previous-chat must be the original negative group ID")
        huddle_chat = args.previous_chat if args.previous_chat is not None else args.chat
        huddle = protoss.call("POST", "/huddle", {"chat_id": f"telegram:{huddle_chat}", "title": group.get("title", "Protoss demo"), "org_slug": args.legion, "quorum": 2})
        if args.legion and huddle.get("org_slug") != args.legion:
            parser.error("selected legion was not found; create it in Protoss before running")
        path = args.state or str(Path.home() / ".protoss" / f"telegram-{me['id']}-{args.chat}.json")
        state = State(path)
        identity = {"bot": me["id"], "chat": args.chat, "users": sorted(users)}
        bind_identity(state, identity, args.previous_chat)
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
        last_tick = 0.0
        while True:
            try:
                if wallet_review:
                    protoss.call("POST", f"/live/groups/{huddle['id']}/verify", {})
                if time.monotonic() - last_tick > 60:  # close finished holds, fire rules on new hacks and episodes
                    last_tick = time.monotonic()
                    protoss.call("POST", "/huddle/tick", {})  # a body keeps it a POST (no body sends GET)
                bridge.drain()
                updates = telegram.call("getUpdates", offset=state.data["offset"], timeout=20, allowed_updates=["message", "callback_query", "message_reaction"])
                for update in updates:
                    try:
                        bridge.handle(update)
                    except APIError as exc:
                        # retry a failing update a few times, then skip it: one bad message must not freeze the chat
                        tries = state.data.setdefault("failures", {})
                        key = str(update["update_id"])
                        tries[key] = tries.get(key, 0) + 1
                        state.save()
                        if tries[key] < 3:
                            raise
                        print(f"skipping update {key} after 3 failures: {exc}", flush=True)
                        bridge.send(args.chat, "That one failed on my side, so I skipped it. Try again in a minute.", f"skip:{key}")
                    state.data["offset"] = update["update_id"] + 1
                    state.data.get("failures", {}).pop(str(update["update_id"]), None)
                    state.save()
            except APIError as exc:
                if exc.status == 409:
                    raise APIError("Telegram reports a conflicting bot connection. Stopping this poller; inspect the other running connection.") from None
                print(f"{exc}; retrying in 3 seconds", flush=True)
                time.sleep(3)
    except APIError as exc:
        parser.exit(1, str(exc) + "\n")
    except KeyboardInterrupt:
        pass
    finally:
        if lock is not None:
            lock.close()


if __name__ == "__main__":
    main()
