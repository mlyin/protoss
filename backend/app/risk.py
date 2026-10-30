"""The risk sandbox.

Pure functions over plain data so they are trivial to test and reason about. Every order an agent
submits goes through `evaluate` before it can reach the exchange; the worker calls `drawdown_breached`
on every tick to decide whether to flatten and halt an agent.

Order of checks (first failure wins):
  1. agent halted                 -> reject
  2. market not in allow-list     -> reject
  3. order-rate limit             -> reject
  4. daily loss limit hit         -> reject (reduce-only orders are still allowed)
  5. notional cap after the trade -> resize down to what fits (reduce-only exempt)
  6. leverage cap after the trade -> resize down to what fits (reduce-only exempt)
  7. nothing left after resizing  -> reject
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LimitSet:
    max_leverage: float
    max_notional_usd: float
    daily_loss_pct: float
    drawdown_flatten_pct: float
    max_orders_per_min: int
    allowed_markets: tuple[str, ...]


@dataclass
class AccountState:
    equity: float
    positions: dict[str, float]  # market -> signed size (base units)
    marks: dict[str, float]  # market -> mark price
    orders_last_minute: int
    day_start_equity: float
    peak_equity: float
    status: str = "live"
    extra: dict = field(default_factory=dict)

    def gross_notional(self) -> float:
        return sum(abs(sz) * self.marks.get(m, 0.0) for m, sz in self.positions.items())


@dataclass(frozen=True)
class Intent:
    market: str
    side: str  # buy | sell
    size: float
    reduce_only: bool = False

    @property
    def signed(self) -> float:
        return self.size if self.side == "buy" else -self.size


@dataclass(frozen=True)
class Verdict:
    decision: str  # approved | resized | rejected
    size: float
    reason: str

    @property
    def ok(self) -> bool:
        return self.decision != "rejected"


def _is_reducing(intent: Intent, current: float) -> bool:
    """True when the order shrinks the absolute position (and does not flip it)."""
    if current == 0:
        return False
    after = current + intent.signed
    return abs(after) < abs(current) and (after == 0 or (after > 0) == (current > 0))


def evaluate(intent: Intent, state: AccountState, limits: LimitSet) -> Verdict:
    if state.status != "live":
        return Verdict("rejected", 0.0, f"agent is {state.status}")
    if intent.size <= 0:
        return Verdict("rejected", 0.0, "size must be positive")
    if intent.market not in limits.allowed_markets:
        return Verdict("rejected", 0.0, f"{intent.market} is not in the allowed-market list")
    if state.orders_last_minute >= limits.max_orders_per_min:
        return Verdict("rejected", 0.0, f"order rate cap {limits.max_orders_per_min}/min reached")

    mark = state.marks.get(intent.market)
    if not mark or mark <= 0:
        return Verdict("rejected", 0.0, f"no mark price for {intent.market}")

    current = state.positions.get(intent.market, 0.0)
    reducing = intent.reduce_only or _is_reducing(intent, current)

    daily_loss = (state.day_start_equity - state.equity) / state.day_start_equity * 100 if state.day_start_equity else 0.0
    if daily_loss >= limits.daily_loss_pct and not reducing:
        return Verdict("rejected", 0.0, f"daily loss limit hit ({daily_loss:.2f}% >= {limits.daily_loss_pct}%)")

    if reducing:
        # Never block an agent from getting smaller; cap at the position so it cannot flip.
        size = min(intent.size, abs(current)) if intent.reduce_only else intent.size
        return Verdict("approved", size, "reducing position")

    # Capacity under the notional cap, accounting for the rest of the book.
    other_notional = sum(abs(sz) * state.marks.get(m, 0.0) for m, sz in state.positions.items() if m != intent.market)
    cap_by_notional = limits.max_notional_usd - other_notional
    cap_by_leverage = limits.max_leverage * state.equity - other_notional
    room_usd = max(0.0, min(cap_by_notional, cap_by_leverage))
    max_abs_size_in_market = room_usd / mark
    after = current + intent.signed
    if abs(after) <= max_abs_size_in_market + 1e-12:
        return Verdict("approved", intent.size, "within limits")

    # Resize so that |after| == max_abs_size_in_market (same direction as the intent).
    allowed_after = max_abs_size_in_market if intent.signed > 0 else -max_abs_size_in_market
    new_size = allowed_after - current
    new_size = new_size if intent.signed > 0 else -new_size
    if new_size <= 1e-9:
        binding = "notional" if cap_by_notional <= cap_by_leverage else "leverage"
        return Verdict("rejected", 0.0, f"{binding} cap leaves no room (${room_usd:,.0f} available)")
    lev_after = (other_notional + abs(after) * mark) / state.equity if state.equity else float("inf")
    binding = "notional" if cap_by_notional <= cap_by_leverage else "leverage"
    detail = (
        f"leverage would reach {lev_after:.1f}x (cap {limits.max_leverage:g}x)"
        if binding == "leverage"
        else f"notional would reach ${other_notional + abs(after) * mark:,.0f} (cap ${limits.max_notional_usd:,.0f})"
    )
    return Verdict("resized", round(new_size, 10), f"{detail}; resized {intent.size:g} -> {new_size:g}")


def drawdown_breached(state: AccountState, limits: LimitSet) -> tuple[bool, float]:
    """Returns (breached, drawdown_pct) against the agent's peak equity."""
    if state.peak_equity <= 0:
        return False, 0.0
    dd = (state.peak_equity - state.equity) / state.peak_equity * 100
    return dd >= limits.drawdown_flatten_pct, dd
