#!/usr/bin/env python3
"""Protoss's Hyperliquid builder code — a dedicated wallet that earns a fee on every order we route.

    python scripts/builder.py keygen                       # make the builder wallet (prints it once)
    python scripts/builder.py status  [--testnet]          # eligibility (>=100 USDC, standard mode), approvals, revenue
    python scripts/builder.py approve [--testnet] [--max-fee 0.030%]
                                                           # sign approveBuilderFee from the MASTER wallet (backend/.env)
    python scripts/builder.py fills --date 20261030 [--testnet]
                                                           # download the day's builder fills CSV from Hyperliquid
    python scripts/builder.py set-standard [--testnet]     # force the builder wallet into standard mode (signs with its key)

Rules (docs: https://hyperliquid.gitbook.io/hyperliquid-docs/trading/builder-codes):
  * a builder is just an address; it must hold >= 100 USDC of perps account value and use the
    "standard" account abstraction mode
  * each user approves a max fee per builder with approveBuilderFee, signed by their MAIN wallet
    (not an agent/API wallet); up to 10 active approvals per user; revocable any time
  * fee caps: 0.1% on perps, 1% on spot; orders carry {"b": builder, "f": tenths_of_bp}
  * fees accrue on-chain and are claimed where referral rewards are claimed
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / "backend" / ".env"
WALLET = ROOT / ".builder-wallet.json"
MAINNET = "https://api.hyperliquid.xyz"
TESTNET = "https://api.hyperliquid-testnet.xyz"


def read_env() -> dict:
    out = {}
    if ENV.exists():
        for line in ENV.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"')
    return out


def builder_address(args) -> str:
    if args.builder:
        return args.builder
    env = read_env()
    if env.get("HL_BUILDER_ADDRESS"):
        return env["HL_BUILDER_ADDRESS"]
    if WALLET.exists():
        return json.loads(WALLET.read_text())["address"]
    sys.exit("no builder address: run `keygen`, or set HL_BUILDER_ADDRESS in backend/.env, or pass --builder")


def info(url):
    from hyperliquid.info import Info

    return Info(url, skip_ws=True)


def cmd_keygen(_args) -> None:
    from eth_account import Account

    if WALLET.exists():
        sys.exit(f"{WALLET.name} already exists ({json.loads(WALLET.read_text())['address']}); delete it first if you really want a new one")
    acct = Account.create()
    WALLET.write_text(json.dumps({"address": acct.address, "private_key": acct.key.hex()}, indent=2))
    WALLET.chmod(0o600)
    print("Protoss builder wallet")
    print("  address:     ", acct.address)
    print("  private key: ", acct.key.hex(), "   (also in .builder-wallet.json, gitignored — back it up)")
    print()
    print("Next:")
    print("  1. send >= 100 USDC to this address on Hyperliquid (Arbitrum USDC deposit, or an internal transfer)")
    print("     and leave the account in *standard* mode (not Unified / portfolio margin)")
    print("     testnet: https://app.hyperliquid-testnet.xyz/drip")
    print(f"  2. add to backend/.env:   HL_BUILDER_ADDRESS={acct.address}")
    print("  3. python scripts/builder.py status   — confirms eligibility; then `approve` from the master wallet")


def cmd_status(args) -> None:
    url = TESTNET if args.testnet else MAINNET
    b = builder_address(args)
    env = read_env()
    fee = int(env.get("HL_BUILDER_FEE_TENTHS_BP", "30"))
    i = info(url)
    print(f"builder {b} on {'testnet' if args.testnet else 'mainnet'}   fee {fee} tenths-bp = {fee / 1000:.3f}% per fill")

    st = i.user_state(b)
    acct_val = float(st.get("marginSummary", {}).get("accountValue", 0) or 0)
    print(f"  perps account value: {acct_val:,.2f} USDC  ->  {'ELIGIBLE' if acct_val >= 100 else 'NOT eligible (needs >= 100 USDC)'}")
    try:
        mode = i.query_user_abstraction_state(b)
        std = mode in ("disabled", "standard", None) or (isinstance(mode, dict) and mode.get("abstraction") in ("disabled", "standard", None))
        print(f"  account mode: {mode}   ->  {'standard, OK' if std else 'NOT standard — run `set-standard`'}")
    except Exception:
        pass

    users = [args.user] if args.user else []
    if env.get("HL_MASTER_PRIVATE_KEY"):
        from eth_account import Account

        users.append(Account.from_key(env["HL_MASTER_PRIVATE_KEY"]).address)
    for u in users:
        try:
            approved = int(i.post("/info", {"type": "maxBuilderFee", "user": u, "builder": b}))
        except Exception as e:
            approved = None
            print(f"  approval by {u}: query failed ({e})")
            continue
        ok = approved >= fee
        print(f"  approval by {u}: max {approved} tenths-bp ({approved / 1000:.3f}%)  ->  {'OK' if ok else 'INSUFFICIENT — run `approve`'}")

    try:
        ref = i.query_referral_state(b)
        keys = {k: v for k, v in ref.items() if any(t in k.lower() for t in ("builder", "unclaimed", "claimed", "reward"))}
        print("  revenue (referral state):", json.dumps(keys) if keys else json.dumps(ref)[:300])
    except Exception as e:
        print(f"  revenue: query failed ({e})")


def cmd_approve(args) -> None:
    """Sign approveBuilderFee from the master wallet in backend/.env (a main wallet, as required)."""
    from eth_account import Account
    from hyperliquid.exchange import Exchange

    url = TESTNET if args.testnet else MAINNET
    b = builder_address(args)
    env = read_env()
    key = os.environ.get(args.key_env) or env.get(args.key_env)
    if not key:
        sys.exit(f"{args.key_env} not set (backend/.env or environment). This must be a MAIN wallet key, not an API/agent wallet.")
    acct = Account.from_key(key)
    fee = int(env.get("HL_BUILDER_FEE_TENTHS_BP", "30"))
    max_fee = args.max_fee or f"{fee / 1000:.3f}%"
    print(f"approving builder {b} up to {max_fee} from {acct.address} on {'testnet' if args.testnet else 'mainnet'}")
    if not args.yes:
        if input("type 'yes' to sign: ").strip().lower() != "yes":
            sys.exit("aborted")
    res = Exchange(acct, url).approve_builder_fee(b, max_fee)
    print(json.dumps(res, indent=2))
    try:
        now = int(info(url).post("/info", {"type": "maxBuilderFee", "user": acct.address, "builder": b}))
        print(f"approved max fee is now {now} tenths-bp ({now / 1000:.3f}%)")
    except Exception:
        pass


def cmd_set_standard(args) -> None:
    """Builder wallets must be in standard mode ('disabled' abstraction on the wire). Signs with the builder key."""
    from eth_account import Account
    from hyperliquid.exchange import Exchange

    if not WALLET.exists():
        sys.exit("no .builder-wallet.json here; this signs with the builder wallet's own key")
    w = json.loads(WALLET.read_text())
    acct = Account.from_key(w["private_key"])
    url = TESTNET if args.testnet else MAINNET
    res = Exchange(acct, url).user_set_abstraction(acct.address, "disabled")
    print(json.dumps(res, indent=2))
    print("mode now:", info(url).query_user_abstraction_state(acct.address))


def cmd_fills(args) -> None:
    import httpx

    b = builder_address(args).lower()  # the URL is case-sensitive and wants lowercase
    net = "Testnet" if args.testnet else "Mainnet"
    url = f"https://stats-data.hyperliquid.xyz/{net}/builder_fills/{b}/{args.date}.csv.lz4"
    r = httpx.get(url, timeout=30)
    if r.status_code != 200:
        sys.exit(f"{r.status_code} for {url} (no fills that day, or the address has never been used as a builder)")
    try:
        import lz4.frame
    except ImportError:
        sys.exit("pip install lz4   (needed to decompress the fills file)")
    csv = lz4.frame.decompress(r.content).decode()
    out = ROOT / f"builder_fills_{args.date}.csv"
    out.write_text(csv)
    lines = csv.strip().splitlines()
    print(f"{len(lines) - 1} fills -> {out}")
    print("\n".join(lines[:6]))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--testnet", action="store_true")
    ap.add_argument("--builder", help="override the builder address")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("keygen").set_defaults(fn=cmd_keygen)
    s = sub.add_parser("status"); s.add_argument("--user", help="also check this user's approval"); s.set_defaults(fn=cmd_status)
    a = sub.add_parser("approve"); a.add_argument("--max-fee", help='e.g. "0.030%%"'); a.add_argument("--key-env", default="HL_MASTER_PRIVATE_KEY"); a.add_argument("--yes", action="store_true"); a.set_defaults(fn=cmd_approve)
    f = sub.add_parser("fills"); f.add_argument("--date", required=True, help="YYYYMMDD (UTC)"); f.set_defaults(fn=cmd_fills)
    sub.add_parser("set-standard").set_defaults(fn=cmd_set_standard)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
