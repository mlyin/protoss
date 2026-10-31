#!/usr/bin/env python3
"""Run a Lab question from the command line against real Hyperliquid data. No server needed.

    python scripts/lab.py "what if I bought XMR every time a major institution got hacked and held 7 days"
    python scripts/lab.py "tail 0x... with $10k" --days 90
    python scripts/lab.py --markets          # which markets Hyperliquid lists right now (perps + HIP-3 dexs)

Needs internet access to api.hyperliquid.xyz (run it on your own machine, not in a sandbox). Prints the
resolved market, the result, every trade, and the same reply the dashboard would show. Add --sim to run on
seeded synthetic prices instead (mechanics only).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("ARENA_MODE", "paper")  # paper = real prices from Hyperliquid mainnet


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="?")
    ap.add_argument("--equity", type=float, default=10_000)
    ap.add_argument("--days", type=int, default=180)
    ap.add_argument("--sim", action="store_true")
    ap.add_argument("--markets", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if args.sim:
        os.environ["ARENA_MODE"] = "sim"

    from app.config import get_settings
    from app import backtest as B
    from app import lab as L

    get_settings.cache_clear()
    source = B.get_source(get_settings())
    if source.name != "hyperliquid" and not args.sim:
        print("Hyperliquid is not reachable from here; falling back to simulated prices. Run this on a machine with internet, or pass --sim on purpose.\n")
    known = set(source.markets())
    if args.markets:
        for m in sorted(known):
            print(m)
        return
    if not args.question:
        sys.exit(__doc__)

    planned = L.plan(args.question, args.equity, args.days, known)
    if isinstance(planned, L.Clarify):
        sys.exit(f"clarify: {planned.question}")
    market = getattr(planned, "market", None)
    if market and not source.has(market):
        import difflib

        near = difflib.get_close_matches(market, sorted(known), n=3, cutoff=0.5)
        sys.exit(f"{market} is not listed on Hyperliquid right now. Closest listed: {', '.join(near) or 'none'}. Rephrase with one of those, e.g. a market that moves with it.")
    print(f"spec: {json.dumps(planned.model_dump(mode='json'))}\nsource: {source.name}\n")
    try:
        res = B.run_backtest(planned, source)
    except B.NoEventsInWindow as e:
        sys.exit(f"clarify: {e}")
    if args.json:
        print(json.dumps(res.as_dict(), indent=2))
        return
    print(L._reply(planned, res, source.name != "hyperliquid"))
    print()
    print(f"{res.label}  |  {res.market}  |  {res.start:%Y-%m-%d} -> {res.end:%Y-%m-%d}  |  {res.bars} bars")
    print(f"return {res.return_pct:+.2f}%   buy&hold {((res.benchmark_curve[-1][1] / res.starting_equity - 1) * 100) if res.benchmark_curve else float('nan'):+.2f}%   max drawdown {res.max_drawdown_pct:.1f}%   sharpe {res.sharpe}   win rate {res.win_rate_pct}   trades {res.trades}")
    print(f"${res.starting_equity:,.0f} -> ${res.final_equity:,.2f}")
    print("\ntrades (first/last 20):")
    for t in res.trades_sample:
        print(f"  {t['ts'][:10]}  {t['side']:<4} {t['size']:>12.4f} @ {t['px']:>12,.2f}  {t['reason']}")
    print("\nnotes:")
    for n in res.notes:
        print(f"  - {n}")


if __name__ == "__main__":
    main()
