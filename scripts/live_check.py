#!/usr/bin/env python3
"""Read-only mainnet checks for Hyperliquid core and trade.xyz markets.

No SDK, private keys, signatures, deposits, or orders. Public addresses only.
"""
import argparse
import datetime as dt
import json
import re
import urllib.request

INFO = "https://api.hyperliquid.xyz/info"


def market_dex(market):
    """Core markets use the default DEX; HIP-3 markets carry a prefix."""
    if not re.fullmatch(r"(?:[a-zA-Z0-9_-]+:)?[a-zA-Z0-9_.-]+", market):
        raise ValueError("use a market symbol such as BTC, ETH, or xyz:ANT")
    return market.split(":", 1)[0] if ":" in market else ""


def info(body):
    req = urllib.request.Request(INFO, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as response:
        return json.load(response)


def market_snapshot(market, data):
    for asset, context in zip(data[0]["universe"], data[1], strict=True):
        if asset["name"] == market:
            if asset.get("isDelisted"):
                raise ValueError(f"{market} is delisted")
            return {"market": market, "asset": asset, "context": context}
    raise ValueError(f"{market} is not listed in this dex")


def account_snapshot(address, market, since_ms):
    dex = market_dex(market)
    state = info({"type": "clearinghouseState", "user": address, "dex": dex})
    fills = info({"type": "userFillsByTime", "user": address, "startTime": since_ms})
    return {
        "address": address,
        "dex_margin": state.get("marginSummary"),
        "withdrawable": state.get("withdrawable"),
        "positions": [p for p in state.get("assetPositions", []) if p["position"]["coin"] == market],
        "fills": [f for f in fills if f.get("coin") == market and f.get("time", 0) >= since_ms],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market", default="xyz:ANT")
    parser.add_argument("--account", action="append", default=[], help="public trading address; repeat for two accounts")
    parser.add_argument("--since-ms", type=int, help="start timestamp for fill verification; default last hour")
    parser.add_argument("--require-fill", action="store_true", help="exit 1 unless every supplied account has a matching fill")
    args = parser.parse_args()
    try:
        dex = market_dex(args.market)
    except ValueError as exc:
        parser.error(str(exc))
    if any(not re.fullmatch(r"0x[0-9a-fA-F]{40}", a) for a in args.account):
        parser.error("--account must be a public 0x address (40 hex characters)")
    if args.require_fill and not args.account:
        parser.error("--require-fill needs at least one --account")
    now = dt.datetime.now(dt.timezone.utc)
    since = args.since_ms if args.since_ms is not None else int(now.timestamp() * 1000) - 3_600_000
    if since < 0:
        parser.error("--since-ms must be nonnegative")
    try:
        snapshot = market_snapshot(args.market, info({"type": "metaAndAssetCtxs", "dex": dex}))
        snapshot.update(checked_at=now.isoformat(), since_ms=since, network="mainnet", read_only=True)
        snapshot["accounts"] = [account_snapshot(a, args.market, since) for a in args.account]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"check failed: {exc}\n")
    print(json.dumps(snapshot, indent=2))
    if args.require_fill and any(not a["fills"] for a in snapshot["accounts"]):
        parser.exit(1, "No matching fill for at least one account. A pledge or order submission is not a fill.\n")


if __name__ == "__main__":
    main()
