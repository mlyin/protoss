"""Execution router: intent -> sandbox verdict -> exchange -> ledger row.

This is the only code path that can create an order on the exchange, and it always goes through
`risk.evaluate` first. Rejections and resizes are recorded as Order rows too, so the decision log the
leaderboard shows is complete.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .hl import ExchangeAdapter
from .models import Agent, Event, Order
from .risk import AccountState, Intent, LimitSet, Verdict, drawdown_breached, evaluate


def limit_set(agent: Agent) -> LimitSet:
    lim = agent.limits
    return LimitSet(
        max_leverage=lim.max_leverage,
        max_notional_usd=lim.max_notional_usd,
        daily_loss_pct=lim.daily_loss_pct,
        drawdown_flatten_pct=lim.drawdown_flatten_pct,
        max_orders_per_min=lim.max_orders_per_min,
        allowed_markets=tuple(lim.allowed_markets),
    )


def _orders_last_minute(db: Session, agent: Agent) -> int:
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)
    return db.scalar(select(func.count(Order.id)).where(Order.agent_id == agent.id, Order.created_at >= since)) or 0


def roll_day(agent: Agent, equity: float) -> None:
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    if agent.day_start_date != today:
        agent.day_start_date = today
        agent.day_start_equity = equity


def account_state(db: Session, agent: Agent, ex: ExchangeAdapter) -> AccountState:
    marks = ex.marks()
    equity = ex.equity(db, agent)
    roll_day(agent, equity)
    if equity > agent.peak_equity:
        agent.peak_equity = equity
    positions = {m: sz for m, (sz, _) in ex.positions(db, agent).items()}
    return AccountState(
        equity=equity,
        positions=positions,
        marks=marks,
        orders_last_minute=_orders_last_minute(db, agent),
        day_start_equity=agent.day_start_equity,
        peak_equity=agent.peak_equity,
        status=agent.status,
    )


def submit(
    db: Session,
    ex: ExchangeAdapter,
    agent: Agent,
    market: str,
    side: str,
    size: float,
    order_type: str = "market",
    limit_px: float | None = None,
    reduce_only: bool = False,
    reason: str | None = None,
) -> tuple[Order, Verdict]:
    state = account_state(db, agent, ex)
    verdict = evaluate(Intent(market, side, size, reduce_only), state, limit_set(agent))

    order = Order(
        agent_id=agent.id,
        market=market,
        side=side,
        requested_size=size,
        order_type=order_type,
        limit_px=limit_px,
        reduce_only=reduce_only,
        reason=reason,
        verdict=verdict.decision,
        verdict_reason=verdict.reason,
        approved_size=verdict.size,
    )
    db.add(order)

    if verdict.decision == "rejected":
        db.add(Event(agent_id=agent.id, kind="reject", detail=f"{side} {size:g} {market}: {verdict.reason}"))
        return order, verdict
    if verdict.decision == "resized":
        db.add(Event(agent_id=agent.id, kind="resize", detail=f"{side} {size:g} {market}: {verdict.reason}"))

    try:
        fill = ex.place(db, agent, market, side, verdict.size, order_type, limit_px, reduce_only)
    except Exception as e:  # exchange rejected it after we approved it (testnet): record, do not crash the agent
        order.verdict = "rejected"
        order.verdict_reason = f"exchange error: {e}"
        db.add(Event(agent_id=agent.id, kind="reject", detail=order.verdict_reason))
        return order, Verdict("rejected", 0.0, order.verdict_reason)

    if fill:
        order.filled_size = fill.size
        order.fill_px = fill.px
        order.exchange_fee_usd = fill.exchange_fee_usd
        order.builder_fee_usd = fill.builder_fee_usd
        order.realized_pnl_usd = fill.realized_pnl_usd
        order.exchange_ref = fill.exchange_ref
    else:
        order.verdict_reason = (order.verdict_reason or "") + " (limit not marketable; not filled)"
    return order, verdict


def flatten_and_halt(db: Session, ex: ExchangeAdapter, agent: Agent, reason: str) -> None:
    fills = ex.flatten(db, agent)
    for f in fills:
        db.add(
            Order(
                agent_id=agent.id,
                market=f.market,
                side=f.side,
                requested_size=f.size,
                order_type="market",
                reduce_only=True,
                reason="sandbox flatten",
                verdict="approved",
                verdict_reason=reason,
                approved_size=f.size,
                filled_size=f.size,
                fill_px=f.px,
                exchange_fee_usd=f.exchange_fee_usd,
                builder_fee_usd=f.builder_fee_usd,
                realized_pnl_usd=f.realized_pnl_usd,
                exchange_ref=f.exchange_ref,
            )
        )
    agent.status = "halted"
    agent.halted_reason = reason
    db.add(Event(agent_id=agent.id, kind="halt", detail=reason))


def check_drawdown(db: Session, ex: ExchangeAdapter, agent: Agent) -> bool:
    """Flatten and halt when the drawdown cap is hit. Returns True if it acted."""
    if agent.status != "live":
        return False
    state = account_state(db, agent, ex)
    breached, dd = drawdown_breached(state, limit_set(agent))
    if breached:
        flatten_and_halt(db, ex, agent, f"drawdown {dd:.1f}% hit the {agent.limits.drawdown_flatten_pct:g}% cap; book flattened")
        return True
    return False
