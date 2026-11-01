from __future__ import annotations

import asyncio
import datetime as dt
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import worker
from .auth import AGENT_PREFIX, OWNER_PREFIX, Principal, current_principal, hash_key, new_key, require_admin, require_owner
from .config import get_settings
from .db import get_db, DbDep, init_db
from .hl import ExchangeAdapter, get_exchange
from .ledger import leaderboard, metrics_for
from .models import Agent, Event, Limits, Order
from .router import account_state, flatten_and_halt, submit

log = logging.getLogger("arena")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    get_exchange()
    task = None
    if get_settings().tick_seconds > 0:
        task = asyncio.create_task(worker.loop())
    yield
    if task:
        task.cancel()


app = FastAPI(title="Protoss: agents fight in the open, your money inside hard limits", version="0.4.0", lifespan=lifespan)
from .browser_policy import install_browser_policy
install_browser_policy(app)


def exchange() -> ExchangeAdapter:
    return get_exchange()


# ------------------------------------------------------------------------------------------------ schemas

class LimitsIn(BaseModel):
    max_leverage: float | None = Field(default=None, gt=0, le=50)
    max_notional_usd: float | None = Field(default=None, gt=0)
    daily_loss_pct: float | None = Field(default=None, gt=0, le=100)
    drawdown_flatten_pct: float | None = Field(default=None, gt=0, le=100)
    max_orders_per_min: int | None = Field(default=None, gt=0, le=600)
    allowed_markets: list[str] | None = None


class LimitsOut(BaseModel):
    max_leverage: float
    max_notional_usd: float
    daily_loss_pct: float
    drawdown_flatten_pct: float
    max_orders_per_min: int
    allowed_markets: list[str]


class AgentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_\-\.]+$")
    owner: str = Field(min_length=1, max_length=64)
    runtime: str = "Python SDK"
    strategy: str | None = Field(default=None, max_length=280)
    starting_equity: float = Field(default=10_000.0, gt=0)
    limits: LimitsIn | None = None


class OrderIn(BaseModel):
    market: str
    side: str = Field(pattern="^(buy|sell)$")
    size: float = Field(gt=0)
    type: str = Field(default="market", pattern="^(market|limit)$")
    px: float | None = Field(default=None, gt=0)
    reduce_only: bool = False
    reason: str | None = Field(default=None, max_length=500)


def _limits_out(lim: Limits) -> LimitsOut:
    return LimitsOut(
        max_leverage=lim.max_leverage,
        max_notional_usd=lim.max_notional_usd,
        daily_loss_pct=lim.daily_loss_pct,
        drawdown_flatten_pct=lim.drawdown_flatten_pct,
        max_orders_per_min=lim.max_orders_per_min,
        allowed_markets=list(lim.allowed_markets),
    )


def _order_out(o: Order) -> dict:
    return {
        "id": o.id,
        "ts": o.created_at.isoformat(),
        "market": o.market,
        "side": o.side,
        "requested_size": o.requested_size,
        "type": o.order_type,
        "limit_px": o.limit_px,
        "reduce_only": o.reduce_only,
        "reason": o.reason,
        "verdict": o.verdict,
        "verdict_reason": o.verdict_reason,
        "approved_size": o.approved_size,
        "filled_size": o.filled_size,
        "fill_px": o.fill_px,
        "exchange_fee_usd": round(o.exchange_fee_usd, 6),
        "builder_fee_usd": round(o.builder_fee_usd, 6),
        "realized_pnl_usd": round(o.realized_pnl_usd, 4),
        "exchange_ref": o.exchange_ref,
    }


# ------------------------------------------------------------------------------------------------ admin

def create_agent_record(db: Session, ex: ExchangeAdapter, body: AgentCreate, org_id: str | None = None, starting_equity: float | None = None) -> dict:
    """Shared by /admin/agents and /orgs/{slug}/agents. Returns the one-time key payload."""
    if db.scalar(select(Agent).where(Agent.name == body.name)):
        raise HTTPException(409, "agent name taken")
    s = get_settings()
    equity = body.starting_equity if starting_equity is None else starting_equity
    owner_key, agent_key = new_key(OWNER_PREFIX), new_key(AGENT_PREFIX)
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    agent = Agent(
        name=body.name,
        owner=body.owner,
        runtime=body.runtime,
        strategy=body.strategy,
        owner_key_hash=hash_key(owner_key),
        agent_key_hash=hash_key(agent_key),
        key_prefix=agent_key[:12],
        starting_equity=equity,
        cash=equity,
        peak_equity=equity,
        day_start_equity=equity,
        day_start_date=today,
        org_id=org_id,
    )
    li = body.limits or LimitsIn()
    agent.limits = Limits(
        max_leverage=li.max_leverage or s.default_max_leverage,
        max_notional_usd=li.max_notional_usd or s.default_max_notional_usd,
        daily_loss_pct=li.daily_loss_pct or s.default_daily_loss_pct,
        drawdown_flatten_pct=li.drawdown_flatten_pct or s.default_drawdown_flatten_pct,
        max_orders_per_min=li.max_orders_per_min or s.default_max_orders_per_min,
        allowed_markets=li.allowed_markets or list(s.default_allowed_markets),
    )
    db.add(agent)
    db.flush()
    try:
        ex.on_agent_created(db, agent)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    db.add(Event(agent_id=agent.id, kind="info", detail=f"agent created with {equity:,.0f} USDC in {ex.name} mode"))
    return {
        "id": agent.id,
        "name": agent.name,
        "owner_key": owner_key,
        "agent_key": agent_key,
        "note": "store both keys now; they are not retrievable later",
        "limits": _limits_out(agent.limits),
        "hl_subaccount": agent.hl_subaccount,
        "org_id": org_id,
    }


@app.post("/admin/agents", status_code=201, dependencies=[Depends(require_admin)])
def create_agent(body: AgentCreate, db: Session = DbDep, ex: ExchangeAdapter = Depends(exchange)):
    return create_agent_record(db, ex, body)


@app.post("/admin/tick", dependencies=[Depends(require_admin)])
def admin_tick(snapshot: bool = True, ex: ExchangeAdapter = Depends(exchange)):
    """Advance one worker tick now (sim/paper). Handy for demos and tests."""
    return worker.run_once(ex, snapshot)


# ------------------------------------------------------------------------------------------------ agent API (v1)

@app.get("/v1/me")
def me(p: Principal = Depends(current_principal), db: Session = DbDep, ex: ExchangeAdapter = Depends(exchange)):
    a = db.get(Agent, p.agent.id)
    st = account_state(db, a, ex)
    return {
        "id": a.id,
        "name": a.name,
        "owner": a.owner,
        "runtime": a.runtime,
        "strategy": a.strategy,
        "org": a.org.slug if a.org_id and a.org else None,
        "role": p.role,
        "status": a.status,
        "halted_reason": a.halted_reason,
        "equity": round(st.equity, 2),
        "cash": round(a.cash, 2) if ex.name not in ("testnet", "mainnet") else None,
        "peak_equity": round(a.peak_equity, 2),
        "day_start_equity": round(a.day_start_equity, 2),
        "gross_notional": round(st.gross_notional(), 2),
        "leverage": round(st.gross_notional() / st.equity, 3) if st.equity else None,
        "mode": ex.name,
        "limits": _limits_out(a.limits),
        "hl_subaccount": a.hl_subaccount,
    }


@app.get("/v1/limits", response_model=LimitsOut)
def get_limits(p: Principal = Depends(current_principal), db: Session = DbDep):
    return _limits_out(db.get(Agent, p.agent.id).limits)


@app.put("/v1/limits", response_model=LimitsOut)
def set_limits(body: LimitsIn, p: Principal = Depends(require_owner), db: Session = DbDep, ex: ExchangeAdapter = Depends(exchange)):
    a = db.get(Agent, p.agent.id)
    lim = a.limits
    if body.allowed_markets is not None:
        known = set(ex.markets())
        unknown = [m for m in body.allowed_markets if m not in known]
        if unknown:
            raise HTTPException(422, f"unknown markets: {unknown}")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(lim, k, v)
    db.add(Event(agent_id=a.id, kind="limits", detail=f"owner set limits: {body.model_dump(exclude_none=True)}"))
    return _limits_out(lim)


@app.get("/v1/markets")
def markets(ex: ExchangeAdapter = Depends(exchange)):
    return {"mode": ex.name, "markets": ex.marks()}


@app.get("/v1/book/{market:path}")
def book(market: str, ex: ExchangeAdapter = Depends(exchange)):
    try:
        mid = ex.mark(market)
    except KeyError:
        raise HTTPException(404, f"unknown market {market}")
    half = mid * 0.0002  # v0: synthetic 4 bp spread around the mark; testnet l2 book comes next
    return {"market": market, "mid": mid, "bid": mid - half, "ask": mid + half, "ts": dt.datetime.now(dt.timezone.utc).isoformat()}


@app.post("/v1/orders", status_code=201)
def place_order(body: OrderIn, p: Principal = Depends(current_principal), db: Session = DbDep, ex: ExchangeAdapter = Depends(exchange)):
    a = db.get(Agent, p.agent.id)
    if body.type == "limit" and body.px is None:
        raise HTTPException(422, "limit orders need px")
    order, verdict = submit(db, ex, a, body.market, body.side, body.size, body.type, body.px, body.reduce_only, body.reason)
    db.flush()
    out = _order_out(order)
    out["resized_to"] = verdict.size if verdict.decision == "resized" else None
    return out


@app.get("/v1/orders")
def list_orders(limit: int = Query(default=50, le=500), p: Principal = Depends(current_principal), db: Session = DbDep):
    rows = db.scalars(select(Order).where(Order.agent_id == p.agent.id).order_by(Order.created_at.desc()).limit(limit)).all()
    return [_order_out(o) for o in rows]


@app.get("/v1/positions")
def positions(p: Principal = Depends(current_principal), db: Session = DbDep, ex: ExchangeAdapter = Depends(exchange)):
    a = db.get(Agent, p.agent.id)
    marks = ex.marks()
    out = []
    for m, (sz, entry) in ex.positions(db, a).items():
        mark = marks.get(m, entry)
        out.append({"market": m, "size": sz, "entry_px": entry, "mark": mark, "unrealized_pnl_usd": round(sz * (mark - entry), 4), "notional_usd": round(abs(sz) * mark, 2)})
    return out


@app.post("/v1/flatten")
def flatten(p: Principal = Depends(require_owner), db: Session = DbDep, ex: ExchangeAdapter = Depends(exchange)):
    a = db.get(Agent, p.agent.id)
    flatten_and_halt(db, ex, a, "kill switch pressed by owner")
    return {"status": a.status, "halted_reason": a.halted_reason}


@app.post("/v1/resume")
def resume(p: Principal = Depends(require_owner), db: Session = DbDep, ex: ExchangeAdapter = Depends(exchange)):
    a = db.get(Agent, p.agent.id)
    a.status = "live"
    a.halted_reason = None
    a.peak_equity = ex.equity(db, a)  # a resumed agent starts a fresh drawdown clock
    db.add(Event(agent_id=a.id, kind="info", detail="owner resumed the agent"))
    return {"status": a.status}


# ------------------------------------------------------------------------------------------------ public arena API

@app.get("/leaderboard")
def get_leaderboard(window_days: int = Query(default=7, ge=1, le=365), db: Session = DbDep, ex: ExchangeAdapter = Depends(exchange)):
    s = get_settings()
    return {"mode": ex.name, "window_days": window_days, "agents": leaderboard(db, ex, window_days, s.snapshot_seconds)}


@app.get("/agents/{agent_id}")
def agent_detail(agent_id: str, db: Session = DbDep, ex: ExchangeAdapter = Depends(exchange)):
    a = db.get(Agent, agent_id) or db.scalar(select(Agent).where(Agent.name == agent_id))
    if not a:
        raise HTTPException(404, "no such agent")
    s = get_settings()
    marks = ex.marks()
    pos = [
        {"market": m, "size": sz, "entry_px": entry, "mark": marks.get(m, entry), "unrealized_pnl_usd": round(sz * (marks.get(m, entry) - entry), 4)}
        for m, (sz, entry) in ex.positions(db, a).items()
    ]
    orders = db.scalars(select(Order).where(Order.agent_id == a.id).order_by(Order.created_at.desc()).limit(50)).all()
    events = db.scalars(select(Event).where(Event.agent_id == a.id).order_by(Event.ts.desc()).limit(50)).all()
    return {
        "metrics": metrics_for(db, ex, a, 7, s.snapshot_seconds).as_dict(),
        "limits": _limits_out(a.limits),
        "positions": pos,
        "orders": [_order_out(o) for o in orders],
        "events": [{"ts": e.ts.isoformat(), "kind": e.kind, "detail": e.detail} for e in events],
    }


@app.get("/agents/{agent_id}/equity")
def agent_equity(agent_id: str, db: Session = DbDep):
    from .models import EquitySnapshot

    rows = db.execute(select(EquitySnapshot.ts, EquitySnapshot.equity).where(EquitySnapshot.agent_id == agent_id).order_by(EquitySnapshot.ts)).all()
    return [{"ts": ts.isoformat(), "equity": eq} for ts, eq in rows]


@app.get("/fills")
def recent_fills(limit: int = Query(default=30, le=200), db: Session = DbDep):
    rows = db.execute(
        select(Order, Agent.name).join(Agent, Agent.id == Order.agent_id).order_by(Order.created_at.desc()).limit(limit)
    ).all()
    return [dict(_order_out(o), agent=name) for o, name in rows]


@app.get("/stats")
def stats(db: Session = DbDep, ex: ExchangeAdapter = Depends(exchange)):
    from sqlalchemy import func

    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24)
    vol = db.scalar(select(func.coalesce(func.sum(Order.filled_size * Order.fill_px), 0.0)).where(Order.created_at >= since, Order.filled_size > 0)) or 0.0
    fees = db.scalar(select(func.coalesce(func.sum(Order.builder_fee_usd), 0.0)).where(Order.created_at >= since)) or 0.0
    live = db.scalar(select(func.count(Agent.id)).where(Agent.status == "live")) or 0
    total = db.scalar(select(func.count(Agent.id))) or 0
    b = builder_info(ex)
    return {
        "mode": ex.name,
        "agents_live": live,
        "agents_total": total,
        "volume_24h_usd": round(float(vol), 2),
        "builder_fees_24h_usd": round(float(fees), 4),
        "builder_fee_tenths_bp": b["fee_tenths_bp"],
        "builder_address": b["address"],
        "builder_warning": b["warning"],
    }


def builder_info(ex: ExchangeAdapter) -> dict:
    """Our builder code, as the web app and the /approve page need it."""
    s = get_settings()
    testnet = ex.name == "testnet"
    return {
        "address": getattr(ex, "builder", None) or s.hl_builder_address,
        "fee_tenths_bp": s.hl_builder_fee_tenths_bp,
        "fee_pct": f"{s.hl_builder_fee_tenths_bp / 1000:.3f}%",
        "network": "Testnet" if testnet else "Mainnet",
        "api_url": "https://api.hyperliquid-testnet.xyz" if testnet else "https://api.hyperliquid.xyz",
        "warning": getattr(ex, "builder_warning", None),
    }


@app.get("/builder")
def builder(ex: ExchangeAdapter = Depends(exchange)):
    """Public: the Protoss builder address + fee, so a wallet owner can approve it (web: #/approve)."""
    return builder_info(ex)


@app.get("/health")
def health(ex: ExchangeAdapter = Depends(exchange)):
    return {"ok": True, "mode": ex.name, "markets": len(ex.markets()),
            "telegram_live_enabled": get_settings().telegram_live_enabled}


from .routes_orgs import router as orgs_router  # noqa: E402
from .lab import router as lab_router  # noqa: E402

app.include_router(orgs_router)
app.include_router(lab_router)

from .social import router as social_router  # noqa: E402
from .onboard import router as onboard_router  # noqa: E402

app.include_router(social_router)
app.include_router(onboard_router)

from .huddle import router as huddle_router  # noqa: E402
from .share import router as share_router  # noqa: E402
from .telegram import router as telegram_router  # noqa: E402

app.include_router(huddle_router)
app.include_router(share_router)
app.include_router(telegram_router)

from .live import router as live_router  # noqa: E402
app.include_router(live_router)

# serve the built web app if present (web/dist)
_dist = Path(__file__).resolve().parents[2] / "web" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="web")
