"""Per-agent performance metrics for the leaderboard, computed from equity snapshots and orders."""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import asdict, dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .hl import ExchangeAdapter
from .models import Agent, EquitySnapshot, Order


@dataclass
class AgentMetrics:
    id: str
    name: str
    owner: str
    runtime: str
    strategy: str | None
    org: str | None
    status: str
    halted_reason: str | None
    equity: float
    starting_equity: float
    pnl_total_pct: float
    pnl_window_pct: float
    max_drawdown_pct: float
    sharpe: float | None
    fills: int
    win_rate: float | None
    markets: list[str]
    builder_fees_usd: float
    created_at: str

    def as_dict(self) -> dict:
        return asdict(self)


def snapshot_equity(db: Session, ex: ExchangeAdapter, agent: Agent) -> float:
    eq = ex.equity(db, agent)
    db.add(EquitySnapshot(agent_id=agent.id, equity=eq))
    if eq > agent.peak_equity:
        agent.peak_equity = eq
    return eq


def _series(db: Session, agent_id: str, since: dt.datetime | None = None) -> list[tuple[dt.datetime, float]]:
    q = select(EquitySnapshot.ts, EquitySnapshot.equity).where(EquitySnapshot.agent_id == agent_id).order_by(EquitySnapshot.ts)
    if since is not None:
        q = q.where(EquitySnapshot.ts >= since)
    return [(ts, eq) for ts, eq in db.execute(q).all()]


def max_drawdown_pct(values: list[float]) -> float:
    peak, worst = -math.inf, 0.0
    for v in values:
        peak = max(peak, v)
        if peak > 0:
            worst = max(worst, (peak - v) / peak * 100)
    return worst


def sharpe(values: list[float], seconds_between: float) -> float | None:
    """Annualized Sharpe of snapshot-to-snapshot returns. Needs at least 6 points; clipped to +/-50 so a
    handful of lucky ticks in sim mode cannot print a nonsense number."""
    if len(values) < 6 or seconds_between <= 0:
        return None
    rets = [(b - a) / a for a, b in zip(values, values[1:]) if a > 0]
    if len(rets) < 5:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    sd = math.sqrt(var)
    if sd == 0:
        return None
    periods_per_year = 365 * 24 * 3600 / max(seconds_between, 60.0)  # never annualize finer than 1-minute bars
    return max(-50.0, min(50.0, mean / sd * math.sqrt(periods_per_year)))


def metrics_for(db: Session, ex: ExchangeAdapter, agent: Agent, window_days: int = 7, snapshot_seconds: float = 60.0) -> AgentMetrics:
    now = dt.datetime.now(dt.timezone.utc)
    equity = ex.equity(db, agent)
    all_series = _series(db, agent.id)
    window = _series(db, agent.id, now - dt.timedelta(days=window_days))
    values_all = [e for _, e in all_series] + [equity]
    values_win = ([e for _, e in window] or [agent.starting_equity]) + [equity]

    fills_q = select(Order).where(Order.agent_id == agent.id, Order.filled_size > 0)
    fills = db.scalars(fills_q).all()
    closes = [o.realized_pnl_usd for o in fills if o.realized_pnl_usd != 0]
    win_rate = (sum(1 for p in closes if p > 0) / len(closes) * 100) if closes else None
    markets = sorted({o.market for o in fills})
    builder_fees = db.scalar(select(func.coalesce(func.sum(Order.builder_fee_usd), 0.0)).where(Order.agent_id == agent.id)) or 0.0

    return AgentMetrics(
        id=agent.id,
        name=agent.name,
        owner=agent.owner,
        runtime=agent.runtime,
        strategy=agent.strategy,
        org=agent.org.slug if agent.org_id and agent.org else None,
        status=agent.status,
        halted_reason=agent.halted_reason,
        equity=round(equity, 2),
        starting_equity=agent.starting_equity,
        pnl_total_pct=round((equity / agent.starting_equity - 1) * 100, 2) if agent.starting_equity else 0.0,
        pnl_window_pct=round((values_win[-1] / values_win[0] - 1) * 100, 2) if values_win[0] else 0.0,
        max_drawdown_pct=round(max_drawdown_pct(values_all), 2),
        sharpe=(round(s, 2) if (s := sharpe(values_win, snapshot_seconds)) is not None else None),
        fills=len(fills),
        win_rate=(round(win_rate, 1) if win_rate is not None else None),
        markets=markets,
        builder_fees_usd=round(float(builder_fees), 4),
        created_at=agent.created_at.isoformat(),
    )


def leaderboard(db: Session, ex: ExchangeAdapter, window_days: int = 7, snapshot_seconds: float = 60.0) -> list[dict]:
    agents = db.scalars(select(Agent)).all()
    rows = [metrics_for(db, ex, a, window_days, snapshot_seconds).as_dict() for a in agents]
    # risk-adjusted first: live agents by Sharpe (None last), then halted
    rows.sort(key=lambda r: (r["status"] != "live", -(r["sharpe"] if r["sharpe"] is not None else -1e9), -r["pnl_window_pct"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows
