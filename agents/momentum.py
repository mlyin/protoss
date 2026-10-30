"""Demo agent 1: dumb momentum. Buys when the short average crosses above the long one, sells the reverse.

    ARENA_URL=http://localhost:8000 ARENA_API_KEY=ar_live_... python agents/momentum.py

It deliberately asks for more size than the sandbox allows now and then, so the leaderboard shows resizes.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from arena import Agent  # noqa: E402
from common import PriceHistory, run  # noqa: E402

MARKETS = os.environ.get("MARKETS", "BTC,ETH").split(",")
RISK_FRACTION = float(os.environ.get("RISK_FRACTION", "0.6"))  # fraction of equity per position, pre-leverage


def step(agent: Agent, market: str, hist: PriceHistory) -> None:
    s = hist.series(market)
    if len(s) < 10:
        return
    short, long = sum(s[-3:]) / 3, sum(s[-10:]) / 10
    pos = {p.market: p for p in agent.positions()}.get(market)
    px = s[-1]
    eq = agent.equity()
    target = eq * RISK_FRACTION * 3 / px  # ask for ~3x; sandbox trims to whatever the cap allows
    if short > long * 1.0005 and (pos is None or pos.size <= 0):
        if pos and pos.size < 0:
            agent.close(market, reason="flip short -> long")
        r = agent.buy(market, round(target, 6), reason=f"momentum: 3-tick avg {short:.2f} > 10-tick {long:.2f}")
        print(f"  {market} buy {target:.4f}: {r.verdict} {r.verdict_reason or ''} filled {r.filled}")
    elif short < long * 0.9995 and (pos is None or pos.size >= 0):
        if pos and pos.size > 0:
            agent.close(market, reason="flip long -> short")
        r = agent.sell(market, round(target, 6), reason=f"momentum: 3-tick avg {short:.2f} < 10-tick {long:.2f}")
        print(f"  {market} sell {target:.4f}: {r.verdict} {r.verdict_reason or ''} filled {r.filled}")


if __name__ == "__main__":
    run(Agent.connect(), MARKETS, step, interval=float(os.environ.get("INTERVAL", "3")))
