"""Shared bits for the demo agents: price history and a tiny run loop."""
from __future__ import annotations

import collections
import time

from arena import Agent


class PriceHistory:
    def __init__(self, n: int = 60):
        self.n = n
        self._h: dict[str, collections.deque[float]] = {}

    def push(self, market: str, px: float) -> None:
        self._h.setdefault(market, collections.deque(maxlen=self.n)).append(px)

    def series(self, market: str) -> list[float]:
        return list(self._h.get(market, []))


def run(agent: Agent, markets: list[str], step, interval: float = 3.0, iterations: int | None = None) -> None:
    """Call `step(agent, market, history)` for each market every `interval` seconds. Stops if the sandbox halts us."""
    hist = PriceHistory()
    i = 0
    while iterations is None or i < iterations:
        me = agent.me()
        if me["status"] != "live":
            print(f"[{me['name']}] halted by sandbox: {me['halted_reason']}")
            return
        marks = agent.markets()
        for m in markets:
            if m in marks:
                hist.push(m, marks[m])
                step(agent, m, hist)
        print(f"[{me['name']}] equity {me['equity']:,.2f}  lev {me['leverage']}")
        i += 1
        time.sleep(interval)
