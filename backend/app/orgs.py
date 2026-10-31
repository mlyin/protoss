"""Koinon (org) logic: pooled capital, nested limits, org-level drawdown.

An org's state is the aggregate of its member agents plus the unallocated pool. An order from a member
agent must pass the agent's own sandbox AND the org's mandate; the smaller size wins. When the org's
equity falls through its drawdown cap, every member is flattened and the org halts.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .hl import ExchangeAdapter
from .models import Agent, Deposit, Event, Order, Org, OrgLimits
from .risk import AccountState, Intent, LimitSet, Verdict, drawdown_breached, evaluate


def org_limit_set(org: Org) -> LimitSet:
    l: OrgLimits = org.limits
    return LimitSet(l.max_leverage, l.max_notional_usd, l.daily_loss_pct, l.drawdown_flatten_pct, l.max_orders_per_min, tuple(l.allowed_markets))


def members(db: Session, org: Org) -> list[Agent]:
    return db.scalars(select(Agent).where(Agent.org_id == org.id)).all()


def org_equity(db: Session, ex: ExchangeAdapter, org: Org) -> float:
    return org.pool_cash + sum(ex.equity(db, a) for a in members(db, org))


def _orders_last_minute(db: Session, org: Org) -> int:
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)
    return db.scalar(select(func.count(Order.id)).join(Agent, Agent.id == Order.agent_id).where(Agent.org_id == org.id, Order.created_at >= since)) or 0


def roll_day(org: Org, equity: float) -> None:
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    if org.day_start_date != today:
        org.day_start_date = today
        org.day_start_equity = equity


def org_state(db: Session, ex: ExchangeAdapter, org: Org) -> AccountState:
    marks = ex.marks()
    positions: dict[str, float] = {}
    equity = org.pool_cash
    for a in members(db, org):
        equity += ex.equity(db, a)
        for m, (sz, _) in ex.positions(db, a).items():
            positions[m] = positions.get(m, 0.0) + sz  # net across agents: two agents long/short the same market offset
    roll_day(org, equity)
    if equity > org.peak_equity:
        org.peak_equity = equity
    return AccountState(
        equity=equity,
        positions=positions,
        marks=marks,
        orders_last_minute=_orders_last_minute(db, org),
        day_start_equity=org.day_start_equity,
        peak_equity=org.peak_equity,
        status=org.status,
    )


def evaluate_for_org(db: Session, ex: ExchangeAdapter, org: Org, intent: Intent) -> Verdict:
    return evaluate(intent, org_state(db, ex, org), org_limit_set(org))


def combine(agent_v: Verdict, org_v: Verdict) -> Verdict:
    """Nest the two verdicts: a rejection by either rejects; otherwise the smaller size, labelled with who bound it."""
    if not agent_v.ok:
        return agent_v
    if not org_v.ok:
        return Verdict("rejected", 0.0, f"org mandate: {org_v.reason}")
    if org_v.size + 1e-12 < agent_v.size:
        return Verdict("resized", org_v.size, f"org mandate: {org_v.reason}")
    return agent_v


def check_org_drawdown(db: Session, ex: ExchangeAdapter, org: Org, flatten_fn) -> bool:
    if org.status != "live":
        return False
    st = org_state(db, ex, org)
    breached, dd = drawdown_breached(st, org_limit_set(org))
    if not breached:
        return False
    reason = f"org drawdown {dd:.1f}% hit the {org.limits.drawdown_flatten_pct:g}% mandate cap; all members flattened"
    for a in members(db, org):
        if a.status == "live":
            flatten_fn(db, ex, a, reason)
    org.status = "halted"
    org.halted_reason = reason
    db.add(Event(agent_id=None, kind="halt", detail=f"[{org.slug}] {reason}"))
    return True


# ------------------------------------------------------------------ pool: deposits and allocations

def deposit(db: Session, org: Org, depositor: str, amount_usd: float) -> Deposit:
    if amount_usd == 0:
        raise ValueError("amount must be non-zero")
    if amount_usd < 0 and -amount_usd > org.pool_cash + 1e-9:
        raise ValueError(f"only ${org.pool_cash:,.2f} is unallocated; recall capital from an agent first")
    d = Deposit(org_id=org.id, depositor=depositor, amount_usd=amount_usd)
    db.add(d)
    org.pool_cash += amount_usd
    org.total_deposited += amount_usd
    if org.peak_equity == 0 and amount_usd > 0:
        org.peak_equity = amount_usd
        org.day_start_equity = amount_usd
        org.day_start_date = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    else:
        # a deposit is not performance: shift the peak and day-start by the same amount so drawdown math stays honest
        org.peak_equity += amount_usd
        org.day_start_equity += amount_usd
    return d


def allocate(db: Session, org: Org, agent: Agent, amount_usd: float) -> None:
    """Move pool cash into a member agent's account (or back, with a negative amount)."""
    if agent.org_id != org.id:
        raise ValueError("agent is not a member of this org")
    if amount_usd > org.pool_cash + 1e-9:
        raise ValueError(f"only ${org.pool_cash:,.2f} unallocated")
    if amount_usd < 0 and -amount_usd > agent.cash + 1e-9:
        raise ValueError("agent does not have that much free cash")
    org.pool_cash -= amount_usd
    agent.cash += amount_usd
    agent.starting_equity += amount_usd
    agent.peak_equity += amount_usd
    agent.day_start_equity += amount_usd
    db.add(Event(agent_id=agent.id, kind="info", detail=f"[{org.slug}] allocated {amount_usd:+,.2f} USDC"))


@dataclass
class DepositorShare:
    depositor: str
    deposited: float
    share_pct: float
    value_usd: float


def shares(db: Session, ex: ExchangeAdapter, org: Org) -> list[DepositorShare]:
    rows = db.execute(select(Deposit.depositor, func.sum(Deposit.amount_usd)).where(Deposit.org_id == org.id).group_by(Deposit.depositor)).all()
    total = sum(max(0.0, amt) for _, amt in rows) or 0.0
    eq = org_equity(db, ex, org)
    out = []
    for dep, amt in rows:
        pct = (amt / total * 100) if total else 0.0
        out.append(DepositorShare(dep, round(amt, 2), round(pct, 2), round(eq * pct / 100, 2)))
    return sorted(out, key=lambda s: -s.deposited)
