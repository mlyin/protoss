from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _uuid() -> str:
    return uuid.uuid4().hex


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    owner: Mapped[str] = mapped_column(String(64))
    runtime: Mapped[str] = mapped_column(String(64), default="Python SDK")
    strategy: Mapped[str | None] = mapped_column(Text, nullable=True)  # one-line description shown on the leaderboard
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    # credentials: hashed; the plaintext is returned exactly once at creation
    owner_key_hash: Mapped[str] = mapped_column(String(64))
    agent_key_hash: Mapped[str] = mapped_column(String(64))
    key_prefix: Mapped[str] = mapped_column(String(16))

    status: Mapped[str] = mapped_column(String(16), default="live")  # live | halted
    halted_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    starting_equity: Mapped[float] = mapped_column(Float)
    cash: Mapped[float] = mapped_column(Float)  # sim/paper ledger cash (USDC)
    peak_equity: Mapped[float] = mapped_column(Float)
    day_start_equity: Mapped[float] = mapped_column(Float)
    day_start_date: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD UTC

    hl_subaccount: Mapped[str | None] = mapped_column(String(42), nullable=True)  # testnet mode
    org_id: Mapped[str | None] = mapped_column(ForeignKey("orgs.id", ondelete="SET NULL"), nullable=True)

    limits: Mapped["Limits"] = relationship(back_populates="agent", uselist=False, cascade="all, delete-orphan")
    positions: Mapped[list["Position"]] = relationship(back_populates="agent", cascade="all, delete-orphan")
    org: Mapped["Org | None"] = relationship(back_populates="agents")


class Org(Base):
    """A phalanx: friends' pooled capital under one mandate, traded by a set of agents.

    In sim/paper the pool is our own ledger (deposits -> pool_cash -> allocations to member agents).
    On testnet this maps onto a Hyperliquid vault (next step)."""

    __tablename__ = "orgs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    slug: Mapped[str] = mapped_column(String(48), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    mandate: Mapped[str] = mapped_column(Text)  # plain-English description depositors signed up for
    leader: Mapped[str] = mapped_column(String(64))
    owner_key_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    status: Mapped[str] = mapped_column(String(16), default="live")  # live | halted
    halted_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    profit_share_pct: Mapped[float] = mapped_column(Float, default=10.0)  # the vault leader's cut, Hyperliquid convention

    pool_cash: Mapped[float] = mapped_column(Float, default=0.0)  # deposited but not yet allocated to an agent
    total_deposited: Mapped[float] = mapped_column(Float, default=0.0)
    peak_equity: Mapped[float] = mapped_column(Float, default=0.0)
    day_start_equity: Mapped[float] = mapped_column(Float, default=0.0)
    day_start_date: Mapped[str] = mapped_column(String(10), default="")

    limits: Mapped["OrgLimits"] = relationship(back_populates="org", uselist=False, cascade="all, delete-orphan")
    agents: Mapped[list["Agent"]] = relationship(back_populates="org")
    deposits: Mapped[list["Deposit"]] = relationship(back_populates="org", cascade="all, delete-orphan")


class OrgLimits(Base):
    """The mandate as numbers. Every member agent's own limits nest inside these."""

    __tablename__ = "org_limits"

    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    max_leverage: Mapped[float] = mapped_column(Float)
    max_notional_usd: Mapped[float] = mapped_column(Float)
    daily_loss_pct: Mapped[float] = mapped_column(Float)
    drawdown_flatten_pct: Mapped[float] = mapped_column(Float)
    max_orders_per_min: Mapped[int] = mapped_column(Integer)
    allowed_markets: Mapped[list[str]] = mapped_column(JSON)

    org: Mapped[Org] = relationship(back_populates="limits")


class Deposit(Base):
    __tablename__ = "deposits"
    __table_args__ = (Index("ix_deposits_org", "org_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"))
    depositor: Mapped[str] = mapped_column(String(64))  # handle or wallet
    amount_usd: Mapped[float] = mapped_column(Float)  # negative for withdrawals
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    org: Mapped[Org] = relationship(back_populates="deposits")


class Limits(Base):
    __tablename__ = "limits"

    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True)
    max_leverage: Mapped[float] = mapped_column(Float)
    max_notional_usd: Mapped[float] = mapped_column(Float)
    daily_loss_pct: Mapped[float] = mapped_column(Float)
    drawdown_flatten_pct: Mapped[float] = mapped_column(Float)
    max_orders_per_min: Mapped[int] = mapped_column(Integer)
    allowed_markets: Mapped[list[str]] = mapped_column(JSON)

    agent: Mapped[Agent] = relationship(back_populates="limits")


class Position(Base):
    __tablename__ = "positions"

    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True)
    market: Mapped[str] = mapped_column(String(32), primary_key=True)
    size: Mapped[float] = mapped_column(Float)  # signed, base units
    entry_px: Mapped[float] = mapped_column(Float)

    agent: Mapped[Agent] = relationship(back_populates="positions")


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (Index("ix_orders_agent_created", "agent_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    market: Mapped[str] = mapped_column(String(32))
    side: Mapped[str] = mapped_column(String(4))  # buy | sell
    requested_size: Mapped[float] = mapped_column(Float)
    order_type: Mapped[str] = mapped_column(String(8))  # market | limit
    limit_px: Mapped[float | None] = mapped_column(Float, nullable=True)
    reduce_only: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    verdict: Mapped[str] = mapped_column(String(16))  # approved | resized | rejected
    verdict_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_size: Mapped[float] = mapped_column(Float, default=0.0)

    filled_size: Mapped[float] = mapped_column(Float, default=0.0)
    fill_px: Mapped[float | None] = mapped_column(Float, nullable=True)
    exchange_fee_usd: Mapped[float] = mapped_column(Float, default=0.0)
    builder_fee_usd: Mapped[float] = mapped_column(Float, default=0.0)
    realized_pnl_usd: Mapped[float] = mapped_column(Float, default=0.0)
    exchange_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)  # HL oid in testnet mode


class EquitySnapshot(Base):
    __tablename__ = "equity_snapshots"
    __table_args__ = (Index("ix_snap_agent_ts", "agent_id", "ts"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    equity: Mapped[float] = mapped_column(Float)


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (Index("ix_events_agent_ts", "agent_id", "ts"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), nullable=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    kind: Mapped[str] = mapped_column(String(32))  # halt | flatten | reject | resize | limits | info
    detail: Mapped[str] = mapped_column(Text)
