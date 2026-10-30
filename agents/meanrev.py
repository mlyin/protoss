"""Demo agent 2: mean reversion with a hard stop. Fades moves beyond 1.5 standard deviations of the
recent window and exits when price comes back to the mean.

    ARENA_URL=http://localhost:8000 ARENA_API_KEY=ar_live_... python agents/meanrev.py
"""
from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from arena import Agent  # noqa: E402
from common import PriceHistory, run  # noqa: E402

MARKETS = os.environ.get("MARKETS", "ETH,SOL,HYPE").split(",")
RISK_FRACTION = float(os.environ.get("RISK_FRACTION", "0.4"))


def step(agent: Agent, market: str, hist: PriceHistory) -> None:
    s = hist.series(market)
    if len(s) < 20:
        return
    mean = sum(s[-20:]) / 20
    sd = math.sqrt(sum((x - mean) ** 2 for x in s[-20:]) / 19) or 1e-9
    z = (s[-1] - mean) / sd
    pos = {p.market: p for p in agent.positions()}.get(market)
    eq = agent.equity()
    size = round(eq * RISK_FRACTION / s[-1], 6)

    if pos is None or pos.size == 0:
        if z > 1.5:
            r = agent.sell(market, size, reason=f"fade: z={z:.2f} above 20-tick mean")
            print(f"  {market} sell {size}: {r.verdict} {r.verdict_reason or ''}")
        elif z < -1.5:
            r = agent.buy(market, size, reason=f"fade: z={z:.2f} below 20-tick mean")
            print(f"  {market} buy {size}: {r.verdict} {r.verdict_reason or ''}")
    else:
        back_to_mean = (pos.size > 0 and z >= 0) or (pos.size < 0 and z <= 0)
        stopped = abs(z) > 3.0
        if back_to_mean or stopped:
            r = agent.close(market, reason="reverted to mean" if back_to_mean else f"stop: z={z:.2f}")
            if r:
                print(f"  {market} close: {r.verdict} pnl {r.realized_pnl_usd:+.2f}")


if __name__ == "__main__":
    run(Agent.connect(), MARKETS, step, interval=float(os.environ.get("INTERVAL", "3")))
