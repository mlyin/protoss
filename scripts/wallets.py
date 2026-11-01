#!/usr/bin/env python3
"""Register a participant's own Hyperliquid account for live copies. Runs on the machine that runs the bridge.

    python scripts/wallets.py add tg:5727530056 --name lando --address 0x562B9081dF47193428a67b0885d9562eDE242c01
    python scripts/wallets.py list
    python scripts/wallets.py check tg:5727530056      # is the API wallet authorized on Hyperliquid for that account?

`add` asks for the API wallet's private key at a hidden prompt (the one the Hyperliquid app shows once under More, API,
after the account owner pressed Authorize) and writes ~/.protoss/wallets.json with mode 0600. The key never goes in a
command argument, in chat or in the repo. Pass --key-env NAME instead to reference a shell variable rather than storing it.
"""
from __future__ import annotations

import argparse
import getpass
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.copies import WALLETS_FILE, load_wallets, save_wallet  # noqa: E402

ADDR = re.compile(r"^0x[0-9a-fA-F]{40}$")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("who", help="tg:<telegram user id>")
    a.add_argument("--name", required=True)
    a.add_argument("--address", required=True, help="the participant's Hyperliquid account (master) address")
    a.add_argument("--key-env", help="name of a shell variable holding the API wallet key, instead of storing the key")
    sub.add_parser("list")
    c = sub.add_parser("check")
    c.add_argument("who")
    args = ap.parse_args()

    if args.cmd == "add":
        if not re.fullmatch(r"tg:\d+", args.who):
            sys.exit("who must look like tg:5727530056")
        if not ADDR.match(args.address):
            sys.exit("address must be 0x followed by 40 hex characters")
        entry = {"name": args.name, "address": args.address}
        if args.key_env:
            entry["agent_key_env"] = args.key_env
        else:
            key = getpass.getpass("API wallet private key (hidden): ").strip()
            if not re.fullmatch(r"(0x)?[0-9a-fA-F]{64}", key):
                sys.exit("that is not a 32-byte hex private key")
            entry["agent_key"] = key if key.startswith("0x") else "0x" + key
        save_wallet(args.who, entry)
        print(f"saved {args.who} -> {args.name} {args.address} in {WALLETS_FILE} (mode 600)")
        return
    wallets = load_wallets()
    if args.cmd == "list":
        for who, w in wallets.items():
            how = "key stored" if w.get("agent_key") else f"key from ${w.get('agent_key_env')}"
            print(f"{who:<16} {w['name']:<10} {w['address']}  {how}")
        if not wallets:
            print(f"no wallets in {WALLETS_FILE}")
        return
    if args.cmd == "check":
        from eth_account import Account
        from hyperliquid.info import Info
        from hyperliquid.utils import constants

        w = wallets.get(args.who) or sys.exit(f"{args.who} not registered")
        import os

        key = w.get("agent_key") or os.environ.get(w.get("agent_key_env") or "")
        if not key:
            sys.exit("no key loaded for that entry")
        mine = Account.from_key(key).address
        info = Info(constants.MAINNET_API_URL, skip_ws=True)
        agents = info.post("/info", {"type": "extraAgents", "user": w["address"]})
        ok = any(str(x.get("address", "")).lower() == mine.lower() for x in agents or [])
        print(f"{args.who} {w['name']} account {w['address']}\n  API wallet {mine}\n  authorized on Hyperliquid: {'yes' if ok else 'NO (More, API, Authorize in the app)'}")
        for dex in ("", "xyz"):
            st = info.post("/info", {"type": "clearinghouseState", "user": w["address"], **({"dex": dex} if dex else {})})
            print(f"  {dex or 'core'} account value: {st['marginSummary']['accountValue']} USDC")


if __name__ == "__main__":
    main()
