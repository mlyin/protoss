#!/usr/bin/env python3
"""Place one order on Hyperliquid mainnet through the API, the way Protoss agents do: an API wallet (agent key) that
can trade but cannot withdraw, acting for a master account. No clicking. Keys come from environment variables and are
never printed.

One-time setup per account (a signature only the account owner can give):
  app.hyperliquid.xyz -> More -> API -> "Generate" an API wallet, name it protoss-demo, Authorize. Copy the private key
  it shows into your shell, never into chat:
      export HL_AGENT_KEY_SECOND=0x...        # the API wallet's private key
      export HL_ACCOUNT_SECOND=0x2222222222222222222222222222222222222222   # the master account it acts for
  Same for Lando with HL_AGENT_KEY_LANDO / HL_ACCOUNT_LANDO.

Then:
  python scripts/trade.py second --coin xyz:ANT --usd 20 --check            # balances, positions, what the order would be
  python scripts/trade.py second --coin xyz:ANT --usd 20 --leverage 1       # set 1x cross, market buy ~$20, print the fill
  python scripts/trade.py lando  --coin xyz:ANT --usd 20 --leverage 1
  python scripts/trade.py second --coin xyz:ANT --usd 20 --side sell --reduce-only   # close it later

HIP-3 markets (xyz:*) are margined in their own dex. Move collateral there in the app first (Portfolio -> Transfer
between perp DEXs); this SDK version has no call for that transfer and it must be signed by the master anyway.
Builder code: set HL_BUILDER_ADDRESS to route the fill through Protoss's builder code once that account has approved
the fee (scripts/builder.py approve); otherwise the order goes without one.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import sys
import time

from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

DEXS = ["xyz"]


def die(msg: str) -> None:
    sys.exit(f"trade.py: {msg}")


def load(name: str) -> tuple[str, str | None]:
    key = os.environ.get(f"HL_AGENT_KEY_{name.upper()}")
    master = os.environ.get(f"HL_ACCOUNT_{name.upper()}")
    if not master:
        die(f"set HL_ACCOUNT_{name.upper()} (the master address) in your shell")
    return master, key


def state(info: Info, master: str, coin: str) -> dict:
    dex = coin.split(":")[0] if ":" in coin else ""
    core = info.user_state(master)
    out = {"master": master, "core_value": core["marginSummary"]["accountValue"]}
    if dex:
        d = info.post("/info", {"type": "clearinghouseState", "user": master, "dex": dex})
        out[f"{dex}_value"] = d["marginSummary"]["accountValue"]
        out[f"{dex}_withdrawable"] = d["withdrawable"]
        pos = [p["position"] for p in d["assetPositions"] if p["position"]["coin"] == coin]
    else:
        pos = [p["position"] for p in core["assetPositions"] if p["position"]["coin"] == coin]
    out["position"] = {k: pos[0][k] for k in ("szi", "entryPx", "leverage", "liquidationPx")} if pos else None
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("account", help="name used in the env vars: second, lando, ...")
    ap.add_argument("--coin", default="xyz:ANT")
    ap.add_argument("--usd", type=float, default=20.0, help="notional in USD; size is rounded down to the market's step")
    ap.add_argument("--side", choices=["buy", "sell"], default="buy")
    ap.add_argument("--leverage", type=int, default=None, help="set this cross leverage on the market before ordering")
    ap.add_argument("--slippage", type=float, default=0.01, help="max slippage for the market order (0.01 = 1%%)")
    ap.add_argument("--reduce-only", action="store_true")
    ap.add_argument("--check", action="store_true", help="read-only: print balances, position and the planned order")
    a = ap.parse_args()

    master, key = load(a.account)
    info = Info(constants.MAINNET_API_URL, skip_ws=True, perp_dexs=DEXS)
    if a.coin not in info.name_to_coin:
        die(f"{a.coin} is not a market this client knows (dexs loaded: {DEXS})")
    mids = info.all_mids(dex=a.coin.split(":")[0]) if ":" in a.coin else info.all_mids()
    mid = float(mids.get(a.coin) or mids.get(a.coin.split(":")[-1]) or 0) or die(f"no mid price for {a.coin}")
    sz_dec = next(u["szDecimals"] for u in (info.post("/info", {"type": "meta", "dex": a.coin.split(":")[0]})["universe"] if ":" in a.coin else info.meta()["universe"]) if u["name"] == a.coin)
    size = math.floor(a.usd / mid * 10**sz_dec) / 10**sz_dec
    if size <= 0:
        die(f"${a.usd} is below one size step of {a.coin} at {mid}")
    before = state(info, master, a.coin)
    plan = {"account": a.account, **before, "coin": a.coin, "mid": mid, "side": a.side, "size": size, "notional_usd": round(size * mid, 2), "leverage": a.leverage, "reduce_only": a.reduce_only}
    print(json.dumps(plan, indent=2))
    if a.check:
        return
    if not key:
        die(f"set HL_AGENT_KEY_{a.account.upper()} (the API wallet's private key) to place orders")

    agent = Account.from_key(key)
    ex = Exchange(agent, constants.MAINNET_API_URL, account_address=master, perp_dexs=DEXS)
    if a.leverage:
        r = ex.update_leverage(a.leverage, a.coin, is_cross=True)
        print("leverage:", json.dumps(r))
        if r.get("status") != "ok":
            die("leverage update refused; nothing ordered")
    builder = None
    if os.environ.get("HL_BUILDER_ADDRESS"):
        builder = {"b": os.environ["HL_BUILDER_ADDRESS"].lower(), "f": int(os.environ.get("HL_BUILDER_FEE_TENTHS_BP", "30"))}
    t0 = int(time.time() * 1000)
    if a.reduce_only:
        px = mid * (1 + a.slippage) if a.side == "buy" else mid * (1 - a.slippage)
        px = round(float(f"{px:.5g}"), 6 - sz_dec)  # Hyperliquid: 5 significant figures, at most (6 - szDecimals) decimals
        r = ex.order(a.coin, a.side == "buy", size, px, {"limit": {"tif": "Ioc"}}, reduce_only=True, builder=builder)
    else:
        r = ex.market_open(a.coin, a.side == "buy", size, slippage=a.slippage, builder=builder)
    print("order:", json.dumps(r))
    statuses = r.get("response", {}).get("data", {}).get("statuses", []) if isinstance(r, dict) else []
    if r.get("status") != "ok" or any("error" in s for s in statuses):
        die("order was not accepted; see the response above")

    time.sleep(1.5)
    fills = [f for f in info.post("/info", {"type": "userFillsByTime", "user": master, "startTime": t0 - 5000}) if f["coin"] == a.coin]
    print("\nfills on Hyperliquid for", master)
    for f in fills:
        when = dt.datetime.fromtimestamp(f["time"] / 1000, dt.timezone.utc).astimezone()
        print(f"  {when:%Y-%m-%d %H:%M:%S %Z}  {f['dir']:<12} {f['side']}  {f['sz']} {f['coin']} @ {f['px']}  fee {f['fee']}  hash {f['hash']}")
    if not fills:
        print("  none yet; re-run with --check in a few seconds")
    print("\nafter:", json.dumps(state(info, master, a.coin), indent=2))


if __name__ == "__main__":
    main()
