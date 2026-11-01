#!/usr/bin/env python3
"""iMessage bridge: one Messages.app group chat <-> one Protoss huddle. Runs on the Mac mini, stdlib only.

In:  reads new rows of ~/Library/Messages/chat.db for the chosen chat (texts and tapbacks) and posts each to
     POST {api}/huddle/{id}/messages. Needs Full Disk Access for the Python that runs it.
Out: drains GET {api}/huddle/{id}/outbox and sends each message into the chat with AppleScript
     (tell application "Messages" to send ... to chat id ...). Needs Automation permission for Messages.

  python3 scripts/imessage_bridge.py chats                       # list group chats: guid, name, members
  python3 scripts/imessage_bridge.py run --chat 'iMessage;+;chat123' --title 'the boys' [--legion hack-club] [--dry-run]

Env: PROTOSS_API (default http://127.0.0.1:8000), ADMIN_TOKEN (same as backend/.env), BRIDGE_ME (your name, default "me").
Names: ~/.protoss/names.json maps a handle (+15551234567 or email) to a first name, e.g. {"+15551234567": "Lee"}.
State: ~/.protoss/bridge-<chat>.json keeps the last chat.db row read, so restarts do not replay the chat.

Best with the mini signed into iMessage under its own Apple ID (the bot is then a member of the group like
anyone else). With your own Apple ID it still works: your messages and the bot's both come back as "from me",
and the bridge tells them apart by matching the text it just sent.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

CHAT_DB = Path.home() / "Library" / "Messages" / "chat.db"
STATE_DIR = Path.home() / ".protoss"
APPLE_EPOCH = 978307200  # 2001-01-01 in unix seconds
REACTIONS = {2000: "love", 2001: "like", 2002: "dislike", 2003: "laugh", 2004: "emphasize", 2005: "question"}
SEND_SCRIPT = ['-e', 'on run argv', '-e', 'tell application "Messages" to send (item 1 of argv) to chat id (item 2 of argv)', '-e', 'end run']


# ------------------------------------------------------------------------------------------------ chat.db

def decode_attributed_body(blob: bytes | None) -> str | None:
    """Text of a message whose `text` column is NULL (macOS 13+ stores it in an NSAttributedString typedstream).

    Layout after the class name: b"NSString" + 5 bytes of preamble (0x01 0x94 0x84 0x01 0x2b), then a length:
    one byte, or 0x81 + uint16 little endian, or 0x82 + uint32 little endian, then that many UTF-8 bytes."""
    if not blob:
        return None
    i = blob.find(b"NSString")
    if i < 0:
        return None
    j = i + len(b"NSString") + 5
    if j >= len(blob):
        return None
    n = blob[j]
    j += 1
    if n == 0x81:
        n, j = int.from_bytes(blob[j:j + 2], "little"), j + 2
    elif n == 0x82:
        n, j = int.from_bytes(blob[j:j + 4], "little"), j + 4
    return blob[j:j + n].decode("utf-8", errors="replace") or None


def reaction_of(kind: int | None) -> str | None:
    if not kind:
        return None
    if kind in REACTIONS:
        return REACTIONS[kind]
    if kind - 1000 in REACTIONS:  # 3000-3005: the tapback was removed
        return "-" + REACTIONS[kind - 1000]
    return None


def target_of(assoc: str | None) -> str | None:
    """associated_message_guid looks like 'p:0/<GUID>' (part 0 of a message) or 'bp:<GUID>'."""
    if not assoc:
        return None
    return assoc.split("/", 1)[1] if "/" in assoc else assoc.split(":", 1)[-1]


def connect(path: Path = CHAT_DB) -> sqlite3.Connection:
    try:
        return sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.OperationalError as e:
        sys.exit(f"cannot open {path}: {e}\nGive Full Disk Access to the Python running this (System Settings, Privacy & Security, Full Disk Access).")


def list_chats(db: sqlite3.Connection) -> list[dict]:
    rows = db.execute("""
        SELECT c.ROWID, c.guid, COALESCE(c.display_name, ''), GROUP_CONCAT(h.id, ', '),
               (SELECT MAX(m.date) FROM chat_message_join j JOIN message m ON m.ROWID = j.message_id WHERE j.chat_id = c.ROWID)
        FROM chat c LEFT JOIN chat_handle_join ch ON ch.chat_id = c.ROWID LEFT JOIN handle h ON h.ROWID = ch.handle_id
        GROUP BY c.ROWID ORDER BY 5 DESC""").fetchall()
    return [{"rowid": r[0], "guid": r[1], "name": r[2], "members": r[3] or "", "last": r[4]} for r in rows]


def chat_rowid(db: sqlite3.Connection, guid: str) -> int:
    r = db.execute("SELECT ROWID FROM chat WHERE guid = ?", (guid,)).fetchone()
    if not r:
        sys.exit(f"no chat with guid {guid}; run `chats` to list them")
    return r[0]


def new_rows(db: sqlite3.Connection, chat: int, after: int) -> list[dict]:
    rows = db.execute("""
        SELECT m.ROWID, m.guid, m.text, m.attributedBody, m.is_from_me, COALESCE(h.id, ''), m.associated_message_type,
               m.associated_message_guid, m.date
        FROM message m JOIN chat_message_join j ON j.message_id = m.ROWID LEFT JOIN handle h ON h.ROWID = m.handle_id
        WHERE j.chat_id = ? AND m.ROWID > ? ORDER BY m.ROWID""", (chat, after)).fetchall()
    out = []
    for rowid, guid, text, body, from_me, handle, assoc_type, assoc_guid, date in rows:
        text = text or decode_attributed_body(body) or ""
        text = text.replace("￼", "").strip()  # attachment placeholder
        out.append({"rowid": rowid, "guid": guid, "text": text, "from_me": bool(from_me), "handle": handle,
                    "reaction": reaction_of(assoc_type), "target": target_of(assoc_guid),
                    "ts": (date / 1e9 if date and date > 1e12 else (date or 0)) + APPLE_EPOCH})
    return out


# ------------------------------------------------------------------------------------------------ names and API

def load_names() -> dict:
    p = STATE_DIR / "names.json"
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return {}


def name_for(handle: str, names: dict, me: str, from_me: bool) -> str:
    if from_me:
        return me
    if handle in names:
        return names[handle]
    digits = re.sub(r"\D", "", handle)
    return f"…{digits[-4:]}" if len(digits) >= 4 else (handle.split("@")[0] or "someone")


class Api:
    def __init__(self, base: str, token: str):
        self.base, self.token = base.rstrip("/"), token

    def call(self, method: str, path: str, body: dict | None = None):
        req = urllib.request.Request(self.base + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"content-type": "application/json", "x-admin-token": self.token})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read() or b"null")


def send(text: str, chat_guid: str, dry: bool) -> bool:
    if dry:
        print(f"--> {text}\n")
        return True
    r = subprocess.run(["osascript", *SEND_SCRIPT, text, chat_guid], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        print(f"send failed: {r.stderr.strip()}\n(First run: allow Terminal/Python to control Messages in System Settings, Privacy & Security, Automation.)", file=sys.stderr)
    return r.returncode == 0


# ------------------------------------------------------------------------------------------------ loop

def run(args) -> None:
    api = Api(os.environ.get("PROTOSS_API", "http://127.0.0.1:8000"), os.environ.get("ADMIN_TOKEN", ""))
    me = os.environ.get("BRIDGE_ME", "me")
    body = {"chat_id": args.chat, "title": args.title}
    if args.legion:
        body["org_slug"] = args.legion
    hid = api.call("POST", "/huddle", body)["id"]
    STATE_DIR.mkdir(exist_ok=True)
    state_path = STATE_DIR / f"bridge-{re.sub(r'[^A-Za-z0-9]', '_', args.chat)}.json"
    db = connect(Path(args.db) if args.db else CHAT_DB)
    chat = chat_rowid(db, args.chat)
    try:
        last = json.loads(state_path.read_text())["last_rowid"]
    except (OSError, ValueError, KeyError):
        last = db.execute("SELECT COALESCE(MAX(message_id), 0) FROM chat_message_join WHERE chat_id = ?", (chat,)).fetchone()[0]  # start from now
    print(f"bridging {args.chat} <-> huddle {hid} at {api.base}, from chat.db row {last}{' (dry run)' if args.dry_run else ''}")
    names = load_names()
    while True:
        try:
            for row in new_rows(db, chat, last):
                if row["text"] or row["reaction"]:
                    api.call("POST", f"/huddle/{hid}/messages", {
                        "sender": name_for(row["handle"], names, me, row["from_me"]), "text": row["text"][:2000], "guid": row["guid"],
                        "reaction": row["reaction"], "target_guid": row["target"], "from_me": row["from_me"]})
                last = row["rowid"]
                state_path.write_text(json.dumps({"last_rowid": last}))
            sent = [m["id"] for m in api.call("GET", f"/huddle/{hid}/outbox") if send(m["text"], args.chat, args.dry_run)]
            if sent:
                api.call("POST", f"/huddle/{hid}/delivered", {"ids": sent})
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            print(f"api unreachable ({e}); retrying", file=sys.stderr)
        except sqlite3.OperationalError as e:  # Messages holds a write lock for a moment now and then
            print(f"chat.db busy ({e}); retrying", file=sys.stderr)
        if args.once:
            return
        time.sleep(args.every)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("chats", help="list chats in chat.db")
    c.add_argument("--db")
    r = sub.add_parser("run", help="bridge one chat")
    r.add_argument("--chat", required=True, help="chat guid from `chats`, e.g. iMessage;+;chat123456")
    r.add_argument("--title", default="group chat")
    r.add_argument("--legion", help="legion slug; pledges go into its paper pool")
    r.add_argument("--every", type=float, default=2.0, help="seconds between polls")
    r.add_argument("--dry-run", action="store_true", help="print outgoing messages instead of sending")
    r.add_argument("--once", action="store_true")
    r.add_argument("--db")
    a = p.parse_args(argv)
    if a.cmd == "chats":
        db = connect(Path(a.db) if a.db else CHAT_DB)
        for ch in list_chats(db)[:30]:
            print(f"{ch['guid']}\t{ch['name'] or '(no name)'}\t{ch['members']}")
        return
    run(a)


if __name__ == "__main__":
    main()
