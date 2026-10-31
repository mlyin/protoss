"""The social layer: profiles, follows, and the activity feed.

Coliseum is public by design: every fill, every rejected order, every halt is visible. The feed is
derived from the ledger (orders, events, deposits) rather than stored twice; profiles and follows are
the only new state. v0 has no auth on profiles — a handle is whatever a depositor or owner called
themselves. Wallet auth replaces that later.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from . import orgs as O
from .db import Base, DbDep
from .hl import ExchangeAdapter, get_exchange
from .ledger import metrics_for
from .models import Agent, Deposit, Event, Order, Org, _now

router = APIRouter()


def exchange() -> ExchangeAdapter:
    return get_exchange()


# ------------------------------------------------------------------------------------------------ models


class Profile(Base):
    __tablename__ = "profiles"

    handle: Mapped[str] = mapped_column(String(32), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(64))
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Follow(Base):
    """`handle` follows a target: another user, an agent (by id) or a phalanx (by slug)."""

    __tablename__ = "follows"
    __table_args__ = (Index("ix_follows_handle", "handle"),)

    handle: Mapped[str] = mapped_column(ForeignKey("profiles.handle", ondelete="CASCADE"), primary_key=True)
    target_type: Mapped[str] = mapped_column(String(8), primary_key=True)  # user | agent | org
    target_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


# ------------------------------------------------------------------------------------------------ schemas


class ProfileIn(BaseModel):
    handle: str = Field(min_length=2, max_length=32, pattern=r"^[a-z0-9_]+$")
    display_name: str = Field(min_length=1, max_length=64)
    bio: str | None = Field(default=None, max_length=280)


class FollowIn(BaseModel):
    handle: str = Field(min_length=2, max_length=32)
    target_type: str = Field(pattern=r"^(user|agent|org)$")
    target_id: str = Field(min_length=1, max_length=64)


@dataclass
class FeedItem:
    ts: str
    kind: str  # fill | reject | resize | halt | deposit | new_agent | new_org | follow
    actor: str  # agent name, depositor handle, leader
    text: str
    agent_id: str | None = None
    org_slug: str | None = None
    market: str | None = None
    amount_usd: float | None = None


# ------------------------------------------------------------------------------------------------ helpers


def _ensure_profile(db: Session, handle: str) -> Profile:
    p = db.get(Profile, handle)
    if not p:
        p = Profile(handle=handle, display_name=handle)
        db.add(p)
        db.flush()
    return p


def _iso(t: dt.datetime) -> str:
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    return t.isoformat()


def build_feed(db: Session, limit: int = 50, agent_ids: set[str] | None = None, org_ids: set[str] | None = None,
               since: dt.datetime | None = None) -> list[FeedItem]:
    """Merge the ledger into one chronological stream. Filters narrow to a follow graph."""
    items: list[FeedItem] = []
    agents = {a.id: a for a in db.scalars(select(Agent)).all()}
    orgs = {o.id: o for o in db.scalars(select(Org)).all()}
    slug_of = lambda a: (orgs[a.org_id].slug if a.org_id in orgs else None)  # noqa: E731

    def want(agent: Agent | None, org_id: str | None = None) -> bool:
        if agent_ids is None and org_ids is None:
            return True
        if agent and agent_ids and agent.id in agent_ids:
            return True
        oid = org_id or (agent.org_id if agent else None)
        return bool(org_ids and oid in org_ids)

    q = select(Order).order_by(Order.created_at.desc()).limit(limit * 3)
    if since:
        q = q.where(Order.created_at >= since)
    for o in db.scalars(q).all():
        a = agents.get(o.agent_id)
        if not a or not want(a):
            continue
        if o.filled_size > 0:
            items.append(FeedItem(_iso(o.created_at), "fill", a.name, f"{o.side} {o.filled_size:g} {o.market} @ {o.fill_px:,.2f}" + (f" · {o.reason}" if o.reason else ""), a.id, slug_of(a), o.market, round(o.filled_size * (o.fill_px or 0), 2)))
        elif o.verdict == "rejected":
            items.append(FeedItem(_iso(o.created_at), "reject", a.name, f"sandbox rejected {o.side} {o.requested_size:g} {o.market}: {(o.verdict_reason or '').split(' (')[0]}", a.id, slug_of(a), o.market))
        elif o.verdict == "resized":
            items.append(FeedItem(_iso(o.created_at), "resize", a.name, f"asked {o.requested_size:g}, sandbox allowed {o.approved_size:g} {o.market}", a.id, slug_of(a), o.market))

    q = select(Event).where(Event.kind.in_(["halt", "info"])).order_by(Event.ts.desc()).limit(limit * 2)
    if since:
        q = q.where(Event.ts >= since)
    for e in db.scalars(q).all():
        a = agents.get(e.agent_id) if e.agent_id else None
        if e.kind == "halt" and a and want(a):
            items.append(FeedItem(_iso(e.ts), "halt", a.name, e.detail, a.id, slug_of(a)))
        elif e.kind == "info" and a and want(a) and e.detail.startswith("agent created"):
            items.append(FeedItem(_iso(e.ts), "new_agent", a.name, f"{a.name} joined" + (f" {slug_of(a)}" if slug_of(a) else " the arena") + (f": {a.strategy}" if a.strategy else ""), a.id, slug_of(a)))

    q = select(Deposit).order_by(Deposit.ts.desc()).limit(limit * 2)
    if since:
        q = q.where(Deposit.ts >= since)
    for d in db.scalars(q).all():
        o = orgs.get(d.org_id)
        if not o or not want(None, o.id):
            continue
        verb = "deposited" if d.amount_usd >= 0 else "withdrew"
        items.append(FeedItem(_iso(d.ts), "deposit", d.depositor, f"{d.depositor} {verb} ${abs(d.amount_usd):,.0f} into {o.name}", None, o.slug, None, d.amount_usd))

    for o in orgs.values():
        if want(None, o.id) and (since is None or o.created_at >= since):
            items.append(FeedItem(_iso(o.created_at), "new_org", o.leader, f"{o.leader} opened {o.name}: “{o.mandate[:120]}{'…' if len(o.mandate) > 120 else ''}”", None, o.slug))

    items.sort(key=lambda i: i.ts, reverse=True)
    return items[:limit]


# ------------------------------------------------------------------------------------------------ routes


@router.post("/social/profiles", status_code=201)
def create_profile(body: ProfileIn, db: Session = DbDep):
    if db.get(Profile, body.handle):
        raise HTTPException(409, "handle taken")
    p = Profile(handle=body.handle, display_name=body.display_name, bio=body.bio)
    db.add(p)
    return {"handle": p.handle, "display_name": p.display_name, "bio": p.bio}


@router.get("/u/{handle}")
def profile_page(handle: str, db: Session = DbDep, ex: ExchangeAdapter = Depends(exchange)):
    """A person: what they put into which phalanxes (and what it's worth now), the agents they run, who they follow."""
    p = db.get(Profile, handle)
    deposits = db.scalars(select(Deposit).where(Deposit.depositor == handle)).all()
    agents = db.scalars(select(Agent).where(Agent.owner == handle)).all()
    led = db.scalars(select(Org).where(Org.leader == handle)).all()
    if not p and not deposits and not agents and not led:
        raise HTTPException(404, "no such person")
    stakes = []
    for org in {d.org_id for d in deposits}:
        o = db.get(Org, org)
        if not o:
            continue
        mine = next((s for s in O.shares(db, ex, o) if s.depositor == handle), None)
        if mine:
            stakes.append({"org": o.slug, "org_name": o.name, "deposited": round(mine.deposited, 2), "value_usd": round(mine.value_usd, 2), "share_pct": round(mine.share_pct, 2), "status": o.status})
    follows = db.scalars(select(Follow).where(Follow.handle == handle)).all()
    followers = db.scalar(select(func.count()).select_from(Follow).where(Follow.target_type == "user", Follow.target_id == handle)) or 0
    return {
        "handle": handle,
        "display_name": p.display_name if p else handle,
        "bio": p.bio if p else None,
        "stakes": stakes,
        "total_deposited": round(sum(s["deposited"] for s in stakes), 2),
        "total_value_usd": round(sum(s["value_usd"] for s in stakes), 2),
        "agents": [asdict(metrics_for(db, ex, a)) for a in agents],
        "leads": [{"slug": o.slug, "name": o.name, "status": o.status} for o in led],
        "following": [{"type": f.target_type, "id": f.target_id} for f in follows],
        "followers": followers,
    }


@router.post("/social/follow", status_code=201)
def follow(body: FollowIn, db: Session = DbDep):
    _ensure_profile(db, body.handle)
    if body.target_type == "agent" and not db.get(Agent, body.target_id):
        raise HTTPException(404, "no such agent")
    if body.target_type == "org" and not db.scalar(select(Org).where(Org.slug == body.target_id)):
        raise HTTPException(404, "no such phalanx")
    if db.get(Follow, (body.handle, body.target_type, body.target_id)):
        return {"ok": True, "already": True}
    db.add(Follow(handle=body.handle, target_type=body.target_type, target_id=body.target_id))
    return {"ok": True}


@router.delete("/social/follow")
def unfollow(body: FollowIn, db: Session = DbDep):
    f = db.get(Follow, (body.handle, body.target_type, body.target_id))
    if f:
        db.delete(f)
    return {"ok": True}


@router.get("/feed")
def feed(handle: str | None = Query(default=None), limit: int = Query(default=50, le=200), db: Session = DbDep):
    """Everything, newest first. With `handle`, only what that person follows plus their own stakes and agents."""
    agent_ids = org_ids = None
    if handle:
        follows = db.scalars(select(Follow).where(Follow.handle == handle)).all()
        agent_ids = {f.target_id for f in follows if f.target_type == "agent"}
        slugs = {f.target_id for f in follows if f.target_type == "org"}
        users = {f.target_id for f in follows if f.target_type == "user"} | {handle}
        org_ids = {o.id for o in db.scalars(select(Org).where(Org.slug.in_(slugs))).all()} if slugs else set()
        # a person's own stakes and agents, and those of people they follow
        org_ids |= {d.org_id for d in db.scalars(select(Deposit).where(Deposit.depositor.in_(users))).all()}
        org_ids |= {o.id for o in db.scalars(select(Org).where(Org.leader.in_(users))).all()}
        agent_ids |= {a.id for a in db.scalars(select(Agent).where(Agent.owner.in_(users))).all()}
    return [asdict(i) for i in build_feed(db, limit, agent_ids, org_ids)]
