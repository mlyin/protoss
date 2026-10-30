from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx


class ArenaError(RuntimeError):
    def __init__(self, status: int, detail: Any):
        super().__init__(f"{status}: {detail}")
        self.status = status
        self.detail = detail


@dataclass(frozen=True)
class Book:
    market: str
    mid: float
    bid: float
    ask: float


@dataclass(frozen=True)
class Position:
    market: str
    size: float
    entry_px: float
    mark: float
    unrealized_pnl_usd: float
    notional_usd: float


@dataclass(frozen=True)
class OrderResult:
    id: str
    verdict: str  # approved | resized | rejected
    verdict_reason: str | None
    requested_size: float
    approved_size: float
    filled: float
    fill_px: float | None
    resized_to: float | None
    builder_fee_usd: float
    realized_pnl_usd: float

    @property
    def ok(self) -> bool:
        return self.verdict != "rejected"


class Agent:
    """Client for one agent. Works with either key: the agent key trades, the owner key also sets limits."""

    def __init__(self, api_key: str, base_url: str = "http://localhost:8000", timeout: float = 10.0):
        self._http = httpx.Client(base_url=base_url.rstrip("/"), headers={"authorization": f"Bearer {api_key}"}, timeout=timeout)

    @classmethod
    def connect(cls, api_key: str | None = None, base_url: str | None = None) -> "Agent":
        key = api_key or os.environ.get("ARENA_API_KEY")
        if not key:
            raise ValueError("pass api_key or set ARENA_API_KEY")
        return cls(key, base_url or os.environ.get("ARENA_URL", "http://localhost:8000"))

    # --- internals
    def _req(self, method: str, path: str, **kw) -> Any:
        r = self._http.request(method, path, **kw)
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail", r.text)
            except Exception:
                detail = r.text
            raise ArenaError(r.status_code, detail)
        return r.json()

    # --- account
    def me(self) -> dict:
        return self._req("GET", "/v1/me")

    def equity(self) -> float:
        return float(self.me()["equity"])

    def limits(self, **changes) -> dict:
        """Read limits, or set them (owner key only). Keys: max_leverage, max_notional_usd, daily_loss_pct,
        drawdown_flatten_pct, max_orders_per_min, markets (list)."""
        if not changes:
            return self._req("GET", "/v1/limits")
        if "markets" in changes:
            changes["allowed_markets"] = changes.pop("markets")
        return self._req("PUT", "/v1/limits", json=changes)

    def flatten(self) -> dict:
        """Kill switch: close everything and halt (owner key)."""
        return self._req("POST", "/v1/flatten")

    def resume(self) -> dict:
        return self._req("POST", "/v1/resume")

    # --- market data
    def markets(self) -> dict[str, float]:
        return self._req("GET", "/v1/markets")["markets"]

    def book(self, market: str) -> Book:
        d = self._req("GET", f"/v1/book/{market}")
        return Book(d["market"], d["mid"], d["bid"], d["ask"])

    # --- trading
    def order(self, market: str, side: str, size: float, type: str = "market", px: float | None = None, reduce_only: bool = False, reason: str | None = None) -> OrderResult:
        body = {"market": market, "side": side, "size": size, "type": type, "px": px, "reduce_only": reduce_only, "reason": reason}
        d = self._req("POST", "/v1/orders", json=body)
        return OrderResult(d["id"], d["verdict"], d["verdict_reason"], d["requested_size"], d["approved_size"], d["filled_size"], d["fill_px"], d.get("resized_to"), d["builder_fee_usd"], d["realized_pnl_usd"])

    def buy(self, market: str, size: float, **kw) -> OrderResult:
        return self.order(market, "buy", size, **kw)

    def sell(self, market: str, size: float, **kw) -> OrderResult:
        return self.order(market, "sell", size, **kw)

    def close(self, market: str, reason: str | None = None) -> OrderResult | None:
        pos = {p.market: p for p in self.positions()}.get(market)
        if not pos or pos.size == 0:
            return None
        return self.order(market, "sell" if pos.size > 0 else "buy", abs(pos.size), reduce_only=True, reason=reason)

    def positions(self) -> list[Position]:
        return [Position(**{k: p[k] for k in ("market", "size", "entry_px", "mark", "unrealized_pnl_usd", "notional_usd")}) for p in self._req("GET", "/v1/positions")]

    def orders(self, limit: int = 50) -> list[dict]:
        return self._req("GET", "/v1/orders", params={"limit": limit})
