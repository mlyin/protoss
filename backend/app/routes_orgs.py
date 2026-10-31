"""Koinon (org) endpoints.

  POST /admin/orgs                     create an org -> one-time org owner key (ar_org_…)
  POST /orgs/{slug}/agents             org owner: add a member agent, allocating capital from the pool
  POST /orgs/{slug}/deposit            deposit (or withdraw with a negative amount) into the pool   [sim/paper: open]
  POST /orgs/{slug}/allocate           org owner: move pool cash to/from a member agent
  PUT  /orgs/{slug}/mandate            org owner: change the mandate limits
  POST /orgs/{slug}/halt | /resume     org owner: kill switch for the whole org / resume
  GET  /orgs                           public list
  GET  /orgs/{slug}                    public detail: mandate, members, depositors, recent decisions
"""
from __future__ import annotations

import re
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import orgs as O
from .auth import hash_key, new_key, require_admin
from .config import get_settings
from .db import get_db
from .hl import ExchangeAdapter, get_exchange
from .ledger import metrics_for
from .models import Agent, Event, Order, Org, OrgLimits
from .router import flatten_and_halt

router = APIRouter()
ORG_PREFIX = "ar_org_"


def exchange() -> ExchangeAdapter:
    return get_exchange()


class MandateIn(BaseModel):
    max_leverage: float | None = Field(default=None, gt=0, le=50)
    max_notional_usd: float | None = Field(default=None, gt=0)
    daily_loss_pct: float | None = Field(default=None, gt=0, le=100)
    drawdown_flatten_pct: float | None = Field(default=None, gt=0, le=100)
    max_orders_per_min: int | None = Field(default=None, gt=0, le=2000)
    allowed_markets: list[str] | None = None


class OrgCreate(BaseModel):
    name: str = Field(min_length=2, max_length=64)
    slug: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9\-]{1,46}$")
    leader: str = Field(min_length=1, max_length=64)
    mandate: str = Field(min_length=10, max_length=1000, description="plain-English description depositors sign up for")
    limits: MandateIn
    profit_share_pct: float = Field(default=10.0, ge=0, le=50)
    initial_deposit: float = Field(default=0.0, ge=0, description="leader's own first deposit (sim/paper)")


class MemberCreate(BaseModel):
    name: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_\-\.]+$")
    runtime: str = "Python SDK"
    strategy: str | None = Field(default=None, max_length=280)
    allocation_usd: float = Field(gt=0)
    limits: MandateIn | None = None


class DepositIn(BaseModel):
    depositor: str = Field(min_length=1, max_length=64)
    amount_usd: float = Field(description="negative to withdraw unallocated pool cash")


class AllocateIn(BaseModel):
    agent: str
    amount_usd: float


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:48] or secrets.token_hex(4)


def _org(db: Session, slug: str) -> Org:
    org = db.scalar(select(Org).where(Org.slug == slug)) or db.get(Org, slug)
    if not org:
        raise HTTPException(404, "no such org")
    return org


def require_org_owner(slug: str, authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> Org:
    org = _org(db, slug)
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "org owner key required")
    key = authorization.split(" ", 1)[1].strip()
    if not key.startswith(ORG_PREFIX) or hash_key(key) != org.owner_key_hash:
        raise HTTPException(403, "org owner key required")
    return org


def _mandate_out(l: OrgLimits) -> dict:
    return {
        "max_leverage": l.max_leverage,
        "max_notional_usd": l.max_notional_usd,
        "daily_loss_pct": l.daily_loss_pct,
        "drawdown_flatten_pct": l.drawdown_flatten_pct,
        "max_orders_per_min": l.max_orders_per_min,
        "allowed_markets": list(l.allowed_markets),
    }


def _summary(db: Session, ex: ExchangeAdapter, org: Org) -> dict:
    eq = O.org_equity(db, ex, org)
    mem = O.members(db, org)
    deps = O.shares(db, ex, org)
    return {
        "id": org.id,
        "slug": org.slug,
        "name": org.name,
        "leader": org.leader,
        "mandate": org.mandate,
        "status": org.status,
        "halted_reason": org.halted_reason,
        "profit_share_pct": org.profit_share_pct,
        "equity": round(eq, 2),
        "pool_cash": round(org.pool_cash, 2),
        "total_deposited": round(org.total_deposited, 2),
        "pnl_pct": round((eq / org.total_deposited - 1) * 100, 2) if org.total_deposited else 0.0,
        "members": len(mem),
        "members_live": sum(1 for a in mem if a.status == "live"),
        "depositors": len(deps),
        "limits": _mandate_out(org.limits),
        "created_at": org.created_at.isoformat(),
    }


# ------------------------------------------------------------------------------------------------ admin

@router.post("/admin/orgs", status_code=201, dependencies=[Depends(require_admin)])
def create_org(body: OrgCreate, db: Session = Depends(get_db), ex: ExchangeAdapter = Depends(exchange)):
    slug = body.slug or _slugify(body.name)
    if db.scalar(select(Org).where(Org.slug == slug)):
        raise HTTPException(409, "slug taken")
    s = get_settings()
    known = set(ex.markets())
    markets = body.limits.allowed_markets or list(s.default_allowed_markets)
    unknown = [m for m in markets if m not in known]
    if unknown:
        raise HTTPException(422, f"unknown markets: {unknown}")
    key = new_key(ORG_PREFIX)
    org = Org(slug=slug, name=body.name, leader=body.leader, mandate=body.mandate, owner_key_hash=hash_key(key), profit_share_pct=body.profit_share_pct)
    org.limits = OrgLimits(
        max_leverage=body.limits.max_leverage or s.default_max_leverage,
        max_notional_usd=body.limits.max_notional_usd or s.default_max_notional_usd,
        daily_loss_pct=body.limits.daily_loss_pct or s.default_daily_loss_pct,
        drawdown_flatten_pct=body.limits.drawdown_flatten_pct or s.default_drawdown_flatten_pct,
        max_orders_per_min=body.limits.max_orders_per_min or s.default_max_orders_per_min * 4,
        allowed_markets=markets,
    )
    db.add(org)
    db.flush()
    if body.initial_deposit:
        O.deposit(db, org, body.leader, body.initial_deposit)
    db.add(Event(agent_id=None, kind="info", detail=f"[{slug}] org created by {body.leader}"))
    return {"org_key": key, "note": "store the org key now; it is not retrievable later", **_summary(db, ex, org)}


# ------------------------------------------------------------------------------------------------ org owner

@router.post("/orgs/{slug}/agents", status_code=201)
def add_member(slug: str, body: MemberCreate, org: Org = Depends(require_org_owner), db: Session = Depends(get_db), ex: ExchangeAdapter = Depends(exchange)):
    from .main import AgentCreate, LimitsIn, create_agent_record  # late import to avoid a cycle

    if org.status != "live":
        raise HTTPException(409, f"org is {org.status}")
    if body.allocation_usd > org.pool_cash + 1e-9:
        raise HTTPException(422, f"only ${org.pool_cash:,.2f} unallocated in the pool")
    lim = body.limits or MandateIn()
    # a member can never be allowed a market the mandate forbids
    markets = lim.allowed_markets or list(org.limits.allowed_markets)
    outside = [m for m in markets if m not in org.limits.allowed_markets]
    if outside:
        raise HTTPException(422, f"markets outside the mandate: {outside}")
    agent_body = AgentCreate(
        name=body.name,
        owner=org.leader,
        runtime=body.runtime,
        strategy=body.strategy,
        starting_equity=body.allocation_usd,
        limits=LimitsIn(
            max_leverage=min(lim.max_leverage or org.limits.max_leverage, org.limits.max_leverage),
            max_notional_usd=min(lim.max_notional_usd or org.limits.max_notional_usd, org.limits.max_notional_usd),
            daily_loss_pct=lim.daily_loss_pct or org.limits.daily_loss_pct,
            drawdown_flatten_pct=lim.drawdown_flatten_pct or org.limits.drawdown_flatten_pct,
            max_orders_per_min=lim.max_orders_per_min or get_settings().default_max_orders_per_min,
            allowed_markets=markets,
        ),
    )
    out = create_agent_record(db, ex, agent_body, org_id=org.id, starting_equity=0.0)
    agent = db.get(Agent, out["id"])
    O.allocate(db, org, agent, body.allocation_usd)
    out["allocation_usd"] = body.allocation_usd
    return out


@router.post("/orgs/{slug}/allocate")
def allocate(slug: str, body: AllocateIn, org: Org = Depends(require_org_owner), db: Session = Depends(get_db), ex: ExchangeAdapter = Depends(exchange)):
    agent = db.scalar(select(Agent).where(Agent.name == body.agent, Agent.org_id == org.id)) or db.get(Agent, body.agent)
    if not agent or agent.org_id != org.id:
        raise HTTPException(404, "no such member")
    try:
        O.allocate(db, org, agent, body.amount_usd)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"pool_cash": round(org.pool_cash, 2), "agent": agent.name, "agent_cash": round(agent.cash, 2)}


@router.put("/orgs/{slug}/mandate")
def set_mandate(slug: str, body: MandateIn, org: Org = Depends(require_org_owner), db: Session = Depends(get_db), ex: ExchangeAdapter = Depends(exchange)):
    if body.allowed_markets is not None:
        known = set(ex.markets())
        unknown = [m for m in body.allowed_markets if m not in known]
        if unknown:
            raise HTTPException(422, f"unknown markets: {unknown}")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(org.limits, k, v)
    db.add(Event(agent_id=None, kind="limits", detail=f"[{org.slug}] mandate changed: {body.model_dump(exclude_none=True)}"))
    return _mandate_out(org.limits)


@router.post("/orgs/{slug}/halt")
def halt_org(slug: str, org: Org = Depends(require_org_owner), db: Session = Depends(get_db), ex: ExchangeAdapter = Depends(exchange)):
    reason = "org kill switch pressed by leader"
    for a in O.members(db, org):
        if a.status == "live":
            flatten_and_halt(db, ex, a, reason)
    org.status, org.halted_reason = "halted", reason
    db.add(Event(agent_id=None, kind="halt", detail=f"[{org.slug}] {reason}"))
    return {"status": org.status}


@router.post("/orgs/{slug}/resume")
def resume_org(slug: str, org: Org = Depends(require_org_owner), db: Session = Depends(get_db), ex: ExchangeAdapter = Depends(exchange)):
    org.status, org.halted_reason = "live", None
    org.peak_equity = O.org_equity(db, ex, org)
    for a in O.members(db, org):
        a.status, a.halted_reason = "live", None
        a.peak_equity = ex.equity(db, a)
    db.add(Event(agent_id=None, kind="info", detail=f"[{org.slug}] resumed by leader"))
    return {"status": org.status}


# ------------------------------------------------------------------------------------------------ depositors (sim/paper: open; testnet: the vault handles it)

@router.post("/orgs/{slug}/deposit", status_code=201)
def deposit(slug: str, body: DepositIn, db: Session = Depends(get_db), ex: ExchangeAdapter = Depends(exchange)):
    org = _org(db, slug)
    if ex.name == "testnet":
        raise HTTPException(501, "on testnet deposits go through the Hyperliquid vault, not this endpoint")
    try:
        O.deposit(db, org, body.depositor, body.amount_usd)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"pool_cash": round(org.pool_cash, 2), "total_deposited": round(org.total_deposited, 2), "shares": [s.__dict__ for s in O.shares(db, ex, org)]}


# ------------------------------------------------------------------------------------------------ public

@router.get("/orgs")
def list_orgs(db: Session = Depends(get_db), ex: ExchangeAdapter = Depends(exchange)):
    rows = [_summary(db, ex, o) for o in db.scalars(select(Org)).all()]
    rows.sort(key=lambda r: (r["status"] != "live", -r["pnl_pct"]))
    return rows


@router.get("/orgs/{slug}")
def org_detail(slug: str, db: Session = Depends(get_db), ex: ExchangeAdapter = Depends(exchange)):
    org = _org(db, slug)
    s = get_settings()
    mem = O.members(db, org)
    orders = db.scalars(select(Order).join(Agent, Agent.id == Order.agent_id).where(Agent.org_id == org.id).order_by(Order.created_at.desc()).limit(40)).all()
    names = {a.id: a.name for a in mem}
    return {
        **_summary(db, ex, org),
        "members_detail": [metrics_for(db, ex, a, 7, s.snapshot_seconds).as_dict() | {"allocated": round(a.starting_equity, 2)} for a in mem],
        "depositors_detail": [d.__dict__ for d in O.shares(db, ex, org)],
        "decisions": [
            {"ts": o.created_at.isoformat(), "agent": names.get(o.agent_id), "market": o.market, "side": o.side, "requested_size": o.requested_size, "verdict": o.verdict, "verdict_reason": o.verdict_reason, "filled_size": o.filled_size, "fill_px": o.fill_px, "reason": o.reason}
            for o in orders
        ],
    }
