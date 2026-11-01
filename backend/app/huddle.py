"""Huddle: a legion's group chat, wired to the Lab and the sandbox.

Friends talk in a group chat (iMessage through the Mac bridge, or the web huddle at #/huddle/<name>). This
module reads that chat and does five things, in order of the conversation:

  1. thesis   "let's buy XMR every time a major company gets hacked"  -> Lab backtest, posted as a card
  2. back it  a thumbs up on the card (tapback), or "in" / "+1"        -> approval from that person
  3. stake    "$50 each" or "in for 80"                                -> pledges per person
  4. arm      quorum of approvals and at least one pledge              -> paper agent with the pledged capital
  5. fire     a matching event ("protoss hack: Coinbase breach")       -> order through the sandbox, then a
              close after the hold and the result posted back with the running score

Calls the Lab cannot test (sports, injuries, anything without a Hyperliquid market or history) are logged
as calls the group resolves with "protoss hit 4" / "protoss miss 4", so the score still counts them.

Money: pledges trade only in sim/paper, as a ledger. In testnet/live a pledge is a commitment and each
person stakes into the legion vault themselves; this module never moves funds or signs anything.

Transport: the bridge (scripts/imessage_bridge.py) posts every chat row to POST /huddle/{id}/messages and
sends whatever GET /huddle/{id}/outbox returns. Web huddles deliver in place.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
import secrets
import time
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .config import get_settings
from .db import Base, DbDep
from .hl import ExchangeAdapter, get_exchange
from .models import Agent, Org

log = logging.getLogger("protoss.huddle")
router = APIRouter(tags=["huddle"])
UTC = dt.timezone.utc


def _now() -> dt.datetime:
    return dt.datetime.now(UTC)


def _aware(t: dt.datetime | None) -> dt.datetime | None:
    return t.replace(tzinfo=UTC) if t is not None and t.tzinfo is None else t


# ------------------------------------------------------------------------------------------------ tables

class Huddle(Base):
    __tablename__ = "huddles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[str] = mapped_column(String(128), unique=True)  # "web:<name>" or the Messages chat guid
    title: Mapped[str] = mapped_column(String(80))
    org_slug: Mapped[str | None] = mapped_column(String(48), nullable=True)
    quorum: Mapped[int] = mapped_column(Integer, default=2)  # people backing a thesis (author included) before it arms
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    @property
    def is_web(self) -> bool:
        return self.chat_id.startswith("web:")


class HuddleMessage(Base):
    __tablename__ = "huddle_messages"
    __table_args__ = (Index("ix_huddle_messages_huddle", "huddle_id", "id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    huddle_id: Mapped[int] = mapped_column(ForeignKey("huddles.id", ondelete="CASCADE"))
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    guid: Mapped[str | None] = mapped_column(String(80), nullable=True)
    sender: Mapped[str] = mapped_column(String(64))
    text: Mapped[str] = mapped_column(Text, default="")
    from_bot: Mapped[bool] = mapped_column(Boolean, default=False)
    delivered: Mapped[bool] = mapped_column(Boolean, default=False)
    kind: Mapped[str] = mapped_column(String(12), default="text")  # text | reaction | card | result
    reaction: Mapped[str | None] = mapped_column(String(12), nullable=True)  # like | love | dislike | laugh | emphasize | question
    target_guid: Mapped[str | None] = mapped_column(String(80), nullable=True)
    thesis_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Thesis(Base):
    __tablename__ = "theses"
    __table_args__ = (UniqueConstraint("huddle_id", "n"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    huddle_id: Mapped[int] = mapped_column(ForeignKey("huddles.id", ondelete="CASCADE"))
    n: Mapped[int] = mapped_column(Integer)  # number inside the huddle, what people type
    author: Mapped[str] = mapped_column(String(64))
    text: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(8))  # rule (Lab spec) | call (no market or history; the group resolves it)
    label: Mapped[str] = mapped_column(String(160))
    spec: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    test: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # backtest summary shown on the card
    status: Mapped[str] = mapped_column(String(10), default="proposed")  # proposed | live | closed | dropped
    each_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(8), nullable=True)  # calls: hit | miss
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    armed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Backer(Base):
    __tablename__ = "thesis_backers"

    thesis_id: Mapped[int] = mapped_column(ForeignKey("theses.id", ondelete="CASCADE"), primary_key=True)
    who: Mapped[str] = mapped_column(String(64), primary_key=True)
    approved: Mapped[bool] = mapped_column(Boolean, default=True)
    pledge_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class HuddleEvent(Base):
    """Something a rule can fire on. Global when huddle_id is null (admin, feed); scoped when reported in a chat."""

    __tablename__ = "huddle_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(16), default="hack")
    label: Mapped[str] = mapped_column(String(200))
    source: Mapped[str | None] = mapped_column(String(400), nullable=True)
    huddle_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reported_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Trigger(Base):
    """One firing of a rule: the open, then the close after the hold."""

    __tablename__ = "thesis_triggers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thesis_id: Mapped[int] = mapped_column(ForeignKey("theses.id", ondelete="CASCADE"))
    event_id: Mapped[int] = mapped_column(Integer)
    market: Mapped[str] = mapped_column(String(32))
    side: Mapped[str] = mapped_column(String(5))  # long | short
    size: Mapped[float] = mapped_column(Float)
    entry_px: Mapped[float] = mapped_column(Float)
    opened_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    exit_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    exit_px: Mapped[float | None] = mapped_column(Float, nullable=True)
    pnl_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    closed: Mapped[bool] = mapped_column(Boolean, default=False)


# ------------------------------------------------------------------------------------------------ parsing

BOT = "Protoss"
ADDRESS = re.compile(r"^\s*(?:@?protoss\b[\s,:]*|p[,:]\s+)", re.I)
THESIS_CUE = re.compile(
    r"\b(every ?time|whenever|each time|what if|let'?s (?:buy|sell|short|long|go long|go short|bet|try|back|test)|"
    r"should we (?:buy|sell|short|long)|backtest|test this|thesis|bet (?:on|that)|i think)\b", re.I)
COPY_BASE = 1000  # per-person copies of an idea are numbered above this, out of the way of the ideas people talk about
CLOSE_ASK = re.compile(r"^\s*(?:close|exit|sell)\s+(?:my\s+)?(?:copy\s+of\s+)?idea\s+#?(\d+)\s*[.!]*\s*$", re.I)
EVENTS_ASK = re.compile(r"\b(show|list|see|what (?:are|were)|which (?:are|were))\b.{0,40}\b(events|hacks|episodes)\b", re.I)
CALL_CUE = re.compile(
    r"\b(injur\w*|injured list|IL|come[s]? off|coming off|return(?:s|ing)? from|win(?:s|ning)?|lose|playoffs?|"
    r"series|odds|championship|finals?|election|ceasefire|fed (?:cut|hike)s?|approve[sd]?|launch(?:es)?)\b", re.I)
EACH = re.compile(r"\$?\s?(\d[\d,]*(?:\.\d+)?)\s*(?:k\b)?\s*(?:dollars|bucks|usd|usdc)?\s*(?:each|a head|apiece|per (?:person|head))\b", re.I)
IN_FOR = re.compile(r"\b(?:i'?m in|in|count me in|me too|i'?ll do|i'?ll put(?: in)?)\s*(?:for)?\s*\$\s?(\d[\d,]*(?:\.\d+)?)|\bin for \$?\s?(\d[\d,]*(?:\.\d+)?)", re.I)
YES = re.compile(r"^\s*(\+1|yes|yep|yeah|ya|in|i'?m in|count me in|let'?s do it|do it|bet|send it|lfg|ok|sure|deal|agreed|same)\s*[.!]*\s*$", re.I)
NO = re.compile(r"^\s*(-1|no|nah|pass|i'?m out|out|hard pass)\s*[.!]*\s*$", re.I)
REACTIONS = {2000: "love", 2001: "like", 2002: "dislike", 2003: "laugh", 2004: "emphasize", 2005: "question"}
BACKING = {"like", "love", "emphasize"}
HELP = (
    "I turn a trade idea in this chat into a tested rule the group can back.\n"
    "Say an idea: \"let's buy XMR every time a major company gets hacked\", \"robots are going to take over the world\",\n"
    "\"the Anthropic bubble is going to pop\" or \"Dwarkesh is always right\"\n"
    "Back it: thumbs up my card, or say \"in\"\n"
    "Stake: \"$50 each\" or \"in for 80\"\n"
    "Also: protoss status, protoss score, protoss hack: <what happened>, protoss hit 4 / miss 4, protoss drop 4"
)


def _money(s: str) -> float:
    return float(s.replace(",", ""))


def _usd(v: float) -> str:
    return f"${v:,.0f}" if abs(v) >= 100 or float(v).is_integer() else f"${v:,.2f}"


def _px(v: float) -> str:
    return f"${v:,.2f}" if v >= 1 else f"${v:.4g}"


def _signed_usd(v: float) -> str:
    return ("+" if v >= 0 else "-") + _usd(abs(v))


# ------------------------------------------------------------------------------------------------ helpers

def get_or_create(db: Session, chat_id: str, title: str | None = None, org_slug: str | None = None) -> Huddle:
    h = db.scalar(select(Huddle).where(Huddle.chat_id == chat_id))
    if h:
        return h
    if org_slug and not db.scalar(select(Org).where(Org.slug == org_slug)):
        org_slug = None
    h = Huddle(chat_id=chat_id, title=(title or chat_id.split(":", 1)[-1])[:80], org_slug=org_slug, quorum=get_settings().huddle_quorum)
    db.add(h)
    db.flush()
    return h


def say(db: Session, h: Huddle, text: str, kind: str = "text", thesis_id: int | None = None) -> HuddleMessage:
    """Queue a bot message. Web huddles deliver in place; the bridge drains the outbox for iMessage."""
    m = HuddleMessage(huddle_id=h.id, sender=BOT, text=text, from_bot=True, kind=kind, thesis_id=thesis_id, delivered=h.is_web)
    db.add(m)
    db.flush()
    if h.is_web:
        m.guid = f"w{m.id}"
    return m


def _theses(db: Session, h: Huddle, statuses: tuple[str, ...] | None = None) -> list[Thesis]:
    q = select(Thesis).where(Thesis.huddle_id == h.id).order_by(Thesis.n)
    if statuses:
        q = q.where(Thesis.status.in_(statuses))
    return list(db.scalars(q).all())


def _latest_open(db: Session, h: Huddle) -> Thesis | None:
    rows = _theses(db, h, ("proposed",))
    return rows[-1] if rows else None


def _by_n(db: Session, h: Huddle, n: int) -> Thesis | None:
    return db.scalar(select(Thesis).where(Thesis.huddle_id == h.id, Thesis.n == n))


def backers(db: Session, t: Thesis) -> list[Backer]:
    return list(db.scalars(select(Backer).where(Backer.thesis_id == t.id).order_by(Backer.ts)).all())


def _backer(db: Session, t: Thesis, who: str) -> Backer:
    b = db.get(Backer, (t.id, who))
    if b is None:
        b = Backer(thesis_id=t.id, who=who, approved=False)
        db.add(b)
        db.flush()
    return b


def _pledged(bs: list[Backer]) -> float:
    return sum(b.pledge_usd or 0 for b in bs if b.approved)


def _who_line(bs: list[Backer]) -> str:
    on = [b for b in bs if b.approved]
    if not on:
        return "nobody yet"
    return ", ".join(f"{b.who} {_usd(b.pledge_usd)}" if b.pledge_usd else b.who for b in on)


def _name(t: Thesis) -> str:
    """How the chat refers to a rule: per-person copies by owner and the idea they came from, never by their 1001 number."""
    spec = t.spec or {}
    return f"{spec['_telegram_copy_owner']}'s copy of idea {spec['_parent_n']}" if spec.get("_telegram_copy_owner") and spec.get("_parent_n") else f"Idea {t.n}"


def _and(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1] if names else "nobody"


def _pledge_line(bs: list[Backer]) -> str:
    """'So far: Lando $11. Waiting on Matthew.' for a copy chat, where each person names their own amount."""
    on = [b for b in bs if b.approved]
    paid = [f"{b.who} {_usd(b.pledge_usd)}" for b in on if b.pledge_usd]
    waiting = [b.who for b in on if not b.pledge_usd]
    return (f"So far: {', '.join(paid)}." if paid else "Nobody has put in an amount yet.") + (f" Waiting on {_and(waiting)}." if waiting else "")


def _link(path: str) -> str:
    return f"{get_settings().app_url.rstrip('/')}{path}"


def is_copy_chat(h: Huddle) -> bool:
    return h.chat_id.startswith(("telegram:", "web:copies-"))


def _can_trade(ex: ExchangeAdapter) -> bool:
    return ex.name in ("sim", "paper", "copies")


def _real(ex: ExchangeAdapter) -> bool:
    return ex.name == "copies"


# ------------------------------------------------------------------------------------------------ the card

def _thin(points: list, n: int = 60) -> list:
    """About n points for the card chart, always ending on the last one so the chart ends where the result does."""
    kept = list(points[:: max(1, len(points) // n)])
    if points and kept[-1] is not points[-1]:
        kept.append(points[-1])
    return [[p[0].isoformat(), round(p[1], 2)] for p in kept]


def _test_summary(spec, res) -> dict:
    out = {
        "label": res.label, "market": res.market, "start": res.start.date().isoformat(), "end": res.end.date().isoformat(),
        "return_pct": round(res.return_pct, 2), "max_drawdown_pct": round(res.max_drawdown_pct, 2), "trades": res.trades,
        "bench_pct": round(res.benchmark_curve[-1][1] / res.starting_equity * 100 - 100, 2) if res.benchmark_curve else None,
        "real": not any("simulated" in n for n in res.notes),
        "source": res.notes[0] if res.notes else "",
        "curve": _thin(res.equity_curve),
        "bench": _thin(res.benchmark_curve or []),
    }
    if res.stats:
        out["events"] = res.stats
        out["hold_days"] = getattr(spec, "hold_days", None)
        out["event_set"] = getattr(spec, "event_set", None)
    return out


def _verdict(t: Thesis, s: dict) -> list[str]:
    """Plain words first: is there an edge, how did the plain market do, and how much history is behind it."""
    spec, mk = t.spec or {}, s.get("market", "")
    start, end = (dt.date.fromisoformat(s["start"]), dt.date.fromisoformat(s["end"])) if s.get("start") else (None, None)
    days = (end - start).days if start else 0
    since = (f"{start:%b %-d}" if start.year == end.year else f"{start:%b %-d, %Y}") if start and days < 365 else f"{start:%b %Y}" if start else ""
    out = []
    ev = s.get("events")
    if ev and ev.get("events"):
        what, many = {"major_hacks": ("a hack", "hacks"), "dwarkesh": ("an episode", "episodes")}.get(s.get("event_set"), ("an event", "events"))
        hold = s.get("hold_days") or 1
        after = f"the day after {what}" if hold == 1 else f"over the {hold} days after {what}"
        gap = ev["event_mean_pct"] - ev["any_mean_pct"]
        word = "No edge." if gap <= 0 else "Barely an edge." if gap < 0.5 else "Some edge."
        out.append(f"{word} {mk} averaged {ev['event_mean_pct']:+.1f}% {after}, {ev['any_mean_pct']:+.1f}% on any day. "
                   f"{ev['event_up']} of {ev['events']} were up.")
        hold_line = f" Just holding {mk}: {s['bench_pct']:+.1f}%." if s.get("bench_pct") is not None else ""
        out.append(f"As a rule since {since}: {s['return_pct']:+.1f}%, worst drop {s['max_drawdown_pct']:.1f}%.{hold_line}")
        if ev["events"] < 40:
            out.append(f"{ev['events']} {many} is a small sample.")
    elif spec.get("type") == "buy_hold" and spec.get("side") == "short":
        bench = s.get("bench_pct")
        out.append(f"Shorting {mk} since {since}: {s['return_pct']:+.1f}%" + (f", while {mk} moved {bench:+.1f}%." if bench is not None else "."))
    elif spec.get("type") == "buy_hold":
        out.append(f"Holding {mk} since {since}: {s['return_pct']:+.1f}%, with a {s['max_drawdown_pct']:.1f}% drop along the way.")
    else:
        bench = f", just holding {mk} {s['bench_pct']:+.1f}%" if s.get("bench_pct") is not None else ""
        out.append(f"As a rule since {since}: {s.get('return_pct', 0):+.1f}%{bench}, worst drop {s.get('max_drawdown_pct', 0):.1f}%, {s.get('trades', 0)} trades.")
    if start and days < 60:
        out.append(f"Only {days} days of price history ({mk} listed {start:%b %-d}), so this is a snapshot, not evidence.")
    return out


def card_text(t: Thesis) -> str:
    from .lab import theme

    why = (theme(t.text or "") or (None, ""))[1]
    lines = [f"Idea {t.n} from {t.author}", t.label] + ([why] if why else []) + [""]
    if t.kind == "call":
        lines += ["No Hyperliquid market or price history matches this, so I logged it as a call instead of a backtest.",
                  "Thumbs up to back it. When it plays out, say protoss hit " + str(t.n) + " or protoss miss " + str(t.n) + "."]
        return "\n".join(lines)
    s = t.test or {}
    if s.get("untested"):
        lines += [f"{s.get('market')} is listed on Hyperliquid; no price history here to test it, so this is a conviction trade.",
                  "", "Thumbs up to back it, then each of you says \"in for 20\" with your own amount.", _link(f"/t/{t.id}")]
        return "\n".join(lines)
    lines += _verdict(t, s)
    data = "Real Hyperliquid prices. Fees and slippage included, funding not." if s.get("real") else "Simulated prices: this shows the mechanics only."
    lines += [data, "", "Thumbs up to back it, then each of you says \"in for 20\" with your own amount.", _link(f"/t/{t.id}")]
    return "\n".join(lines)


def propose(db: Session, h: Huddle, author: str, text: str, addressed: bool) -> list[str]:
    """Plan the idea with the Lab. A spec gets a backtest card; a call gets logged; anything else is ignored
    unless the bot was addressed, in which case it asks the Lab's clarifying question."""
    from .backtest import NoEventsInWindow, SourceUnavailable, get_source, run_backtest
    from .lab import Clarify, LabError, plan, podcast_research_question

    s = get_settings()
    source = get_source(s)
    ex = get_exchange()
    tradeable = set(ex.markets())  # what can be traded here; the candle source may know fewer markets
    known = set(source.markets()) | tradeable
    try:
        planned = plan(text, 10_000.0, 365, known)
    except LabError as e:
        return [str(e)] if addressed else []
    n = (max((t.n for t in _theses(db, h) if t.n < COPY_BASE), default=0)) + 1
    if isinstance(planned, Clarify):
        if podcast_research_question(text, known):
            say(db, h, planned.question)
            return [planned.question]
        if CALL_CUE.search(text):
            t = Thesis(huddle_id=h.id, n=n, author=author, text=text, kind="call", label=f"Call: {text.strip()[:150]}")
            db.add(t)
            db.flush()
            _backer(db, t, author).approved = True
            say(db, h, card_text(t), "card", t.id)
            return ["call"]
        return [planned.question] if addressed else []
    market = getattr(planned, "market", None)
    markets = [market] if market else (getattr(planned, "markets", None) or [])
    missing = [name for name in markets if not source.has(name) and name not in tradeable]
    if missing:
        return [f"{', '.join(missing)} is not listed on Hyperliquid here, so I cannot test that basket."] if addressed else []
    untested = [name for name in markets if not source.has(name)]
    if untested:
        # tradeable but no price history on this source: the card still goes up, without a backtest
        t = Thesis(huddle_id=h.id, n=n, author=author, text=text, kind="rule", label=planned.label()[:160],
                   spec=planned.model_dump(mode="json"), test={"market": markets[0] if markets else None, "untested": True})
    else:
        try:
            res = run_backtest(planned, source)
        except (NoEventsInWindow, SourceUnavailable, ValueError) as e:
            return [f"Could not test that: {e}"] if addressed else []
        t = Thesis(huddle_id=h.id, n=n, author=author, text=text, kind="rule", label=res.label[:160],
                   spec=planned.model_dump(mode="json"), test=_test_summary(planned, res))
    db.add(t)
    db.flush()
    _backer(db, t, author).approved = True
    say(db, h, card_text(t), "card", t.id)
    return ["card"]


# ------------------------------------------------------------------------------------------------ backing, stakes, arming

def approve(db: Session, ex: ExchangeAdapter, h: Huddle, t: Thesis, who: str, on: bool = True, pledge: float | None = None) -> None:
    if t.status != "proposed":
        return
    b = _backer(db, t, who)
    was = b.approved
    b.approved = on
    cap = get_settings().huddle_max_pledge_usd
    if pledge is not None:
        b.pledge_usd = min(pledge, cap)
    elif on and b.pledge_usd is None and t.each_usd:
        b.pledge_usd = t.each_usd
    if not on:
        b.pledge_usd = None
    if on and not was:
        db.flush()
        _maybe_arm(db, ex, h, t, announce_backing=True)
    elif pledge is not None:
        db.flush()
        _maybe_arm(db, ex, h, t)


def set_each(db: Session, ex: ExchangeAdapter, h: Huddle, t: Thesis, who: str, amount: float) -> None:
    cap = get_settings().huddle_max_pledge_usd
    t.each_usd = min(amount, cap)
    me = _backer(db, t, who)
    me.approved = True
    for b in backers(db, t):
        if b.approved:
            b.pledge_usd = t.each_usd
    db.flush()
    bs = backers(db, t)
    capped = f" (capped at {_usd(cap)} a person{'' if _real(ex) else ' in paper mode'})" if amount > cap else ""
    if not _maybe_arm(db, ex, h, t):
        need = max(0, h.quorum - sum(b.approved for b in bs))
        more = f" Need {need} more to back it." if need else ""
        say(db, h, f"{_usd(t.each_usd)} each on thesis {t.n}{capped}. In: {_who_line(bs)}, {_usd(_pledged(bs))} total.{more} "
                   f"Thumbs up the card or say \"in\" to join.", thesis_id=t.id)


def _maybe_arm(db: Session, ex: ExchangeAdapter, h: Huddle, t: Thesis, announce_backing: bool = False) -> bool:
    bs = backers(db, t)
    approved = [b for b in bs if b.approved]
    total = _pledged(bs)
    if len(approved) < h.quorum or (t.kind == "rule" and total <= 0):
        if announce_backing and len(approved) >= h.quorum and t.kind == "rule":
            ask = "Now each of you says how much: \"in for 20\"." if is_copy_chat(h) else "How much each? Say \"$50 each\"."
            say(db, h, f"Idea {t.n} is backed by {_and([b.who for b in approved])}. {ask}", thesis_id=t.id)
        return False
    if is_copy_chat(h) and t.kind == "rule" and sum((b.pledge_usd or 0) > 0 for b in approved) < h.quorum:
        if announce_backing:
            kind = "real order from your own account" if _real(ex) else "paper pledge"
            say(db, h, f"Idea {t.n} needs an amount from each of you, one {kind} per person. {_pledge_line(bs)} Say \"in for 20\".", thesis_id=t.id)
        return False
    arm(db, ex, h, t)
    return True


def arm(db: Session, ex: ExchangeAdapter, h: Huddle, t: Thesis) -> None:
    from .main import AgentCreate, LimitsIn, create_agent_record  # late import: main imports this module's router

    bs = [b for b in backers(db, t) if b.approved]
    t.status, t.armed_at = "live", _now()
    if t.kind == "call":
        say(db, h, f"Call {t.n} is on the board, backed by {', '.join(b.who for b in bs)}. Say protoss hit {t.n} or protoss miss {t.n} when it resolves.", thesis_id=t.id)
        return
    total = _pledged(bs)
    spec = t.spec or {}
    market = spec.get("market")
    if not _can_trade(ex):
        if is_copy_chat(h):
            say(db, h, f"Thesis {t.n} is backed for separate accounts. No real order was sent. Each participant must authorize their own trade in their own wallet; this Telegram demo cannot execute mainnet copies.", thesis_id=t.id)
            return
        say(db, h, f"Thesis {t.n} is armed: {_usd(total)} pledged by {_who_line(bs)}. This server trades real money, so nothing moves "
                   f"from here: each of you stakes your own share into the legion yourself. {_link('/#/join' + (f'?legion={h.org_slug}' if h.org_slug else ''))}", thesis_id=t.id)
        return
    if is_copy_chat(h) and not spec.get("_telegram_copy_owner"):
        # Each copy gets its own thesis, agent, positions and risk ledger. Nothing is pooled.
        original_spec = dict(spec)
        copies = []
        next_n = max([row.n for row in _theses(db, h)] + [COPY_BASE]) + 1  # copies count from 1001 so ideas stay 1, 2, 3
        for backer in bs:
            if (backer.pledge_usd or 0) <= 0:
                continue
            child = Thesis(huddle_id=h.id, n=next_n, author=backer.who, text=t.text,
                           kind="rule", label=f"{t.label} ({backer.who} copy)"[:160], test=t.test,
                           spec={**original_spec, "_telegram_copy_owner": backer.who, "_parent_n": t.n})
            next_n += 1
            db.add(child)
            db.flush()
            db.add(Backer(thesis_id=child.id, who=backer.who, approved=True, pledge_usd=backer.pledge_usd))
            db.flush()
            try:
                arm(db, ex, h, child)
            except Exception as e:  # a copy that cannot trade (no authorized wallet, cap, exchange refusal) must not stop the others
                child.status = "halted"
                say(db, h, f"{backer.who}'s copy did not go out: {e}", "result", child.id)
                continue
            copies.append(child.id)
            for tr in db.scalars(select(Trigger).where(Trigger.thesis_id == child.id)).all():
                if _real(ex):
                    lf = getattr(ex, "last_fill", None) or {}
                    stamp = f", Hyperliquid fill {lf.get('hash', '')[:14]}" if lf.get("hash") else ""
                    acct = ex.wallets.get(backer.who, {}).get("address", "")
                    say(db, h, f"{backer.who}'s order filled: {tr.size:.6g} {tr.market} at {_px(tr.entry_px)}, {_usd(tr.size * tr.entry_px)} of their {_usd(backer.pledge_usd)}. "
                               f"From their own account {acct[:6]}...{acct[-4:]}{stamp}. Real order, real money.", "result", child.id)
                else:
                    say(db, h, f"{backer.who}'s separate paper copy filled: {tr.size:.6g} {tr.market} at {_px(tr.entry_px)}. "
                               f"Paper allocation {_usd(backer.pledge_usd)}. Agent {child.agent_id}. No real funds moved.", "result", child.id)
        t.spec = {**original_spec, "type": "telegram_copies", "copy_ids": copies}
        if _real(ex):
            filled = any(db.scalar(select(Trigger).where(Trigger.thesis_id == cid)) for cid in copies)
            what = "separate orders, one from each account" if filled else "separate copies armed, one per account; each order goes out from its own account when the rule fires"
            say(db, h, f"Idea {t.n} is live: {len(copies)} {what}. Each of you owns your position and can close it yourself any time. Nothing is pooled.", thesis_id=t.id)
        else:
            say(db, h, f"Thesis {t.n} created {len(copies)} separate paper accounts. Each participant owns their own copy and its result. No shared pot.", thesis_id=t.id)
        return
    name = f"huddle{h.id}-t{t.n}-{secrets.token_hex(2)}"
    org = db.scalar(select(Org).where(Org.slug == h.org_slug)) if h.org_slug else None
    in_org = bool(org and not spec.get("_telegram_copy_owner") and org.status == "live" and market in (org.limits.allowed_markets or []))
    holdings = spec.get("holdings") or []
    allowed = [item["market"] for item in holdings] if holdings else ([market] if market else None)
    lim = LimitsIn(max_leverage=1.0 if (holdings or _real(ex)) else 2.0, drawdown_flatten_pct=25.0, daily_loss_pct=20.0, allowed_markets=allowed)  # real money: 1x, always
    body = AgentCreate(name=name, owner=t.author, runtime="huddle rule", strategy=f"{t.label} (thesis {t.n}, {h.title})"[:280], starting_equity=total, limits=lim)
    if in_org:
        from . import orgs as O

        for b in bs:
            O.deposit(db, org, b.who, b.pledge_usd or 0)
        out = create_agent_record(db, ex, body, org_id=org.id, starting_equity=0.0)
        agent = db.get(Agent, out["id"])
        O.allocate(db, org, agent, total)
    else:
        out = create_agent_record(db, ex, body)
    t.agent_id = out["id"]
    where = f" inside {org.name}" if in_org else ""
    waiting = {"major_hacks": "Waiting for the next major hack.", "dwarkesh": "Waiting for the next Dwarkesh Podcast episode."}.get(spec.get("event_set"), "") if spec.get("type") == "event_buy" else ""
    if spec.get("type") == "basket_hold":
        # Reserve a small fee/slippage allowance. Each participant keeps their own positions.
        budget = total * 0.998
        for holding in holdings:
            _open(db, ex, h, t, None, f"idea {t.n}: basket copy", holding["market"], budget * holding["weight"])
    elif spec.get("type") == "buy_hold" and market:
        _open(db, ex, h, t, None, f"thesis {t.n}: buy and hold")
        waiting = ""
    elif spec.get("type") not in ("event_buy", "buy_hold"):
        waiting = "No live runtime for this rule type yet, so the agent holds the cash and the card keeps the backtest."
    money = "real money" if _real(ex) else "paper money"
    owner, parent = spec.get("_telegram_copy_owner"), spec.get("_parent_n")
    if owner and spec.get("type") == "buy_hold" and db.scalar(select(Trigger).where(Trigger.thesis_id == t.id)):
        return  # the fill message already says it went out; one line per person is enough
    head = f"{owner}'s copy of idea {parent} is armed: {_usd(total)} of {money}" if owner and parent else f"Thesis {t.n} is live{where}. {_usd(total)} in {money} from {_who_line(bs)}"
    say(db, h, " ".join(x for x in [f"{head}, max {int(lim.max_leverage)}x leverage, flattens at -25%.", waiting,
                                     "" if owner else f"Every fill is public: {_link('/#/feed')}"] if x), thesis_id=t.id)


def _latest_live_rule(db: Session, h: Huddle) -> Thesis | None:
    rows = [t for t in _theses(db, h, ("live",)) if t.kind == "rule" and _aware(t.armed_at) > _now() - dt.timedelta(days=2)]
    return rows[-1] if rows else None


def join_live(db: Session, ex: ExchangeAdapter, h: Huddle, t: Thesis, who: str, amount: float | None) -> None:
    """Someone joins after the rule armed: their stake goes into the same pot (paper), or they stake themselves (live)."""
    b = _backer(db, t, who)
    add = min(amount or t.each_usd or 0, get_settings().huddle_max_pledge_usd - (b.pledge_usd or 0))
    if add <= 0:
        say(db, h, f"{who}, say how much, like \"in for 50\".", thesis_id=t.id)
        return
    b.approved, b.pledge_usd = True, (b.pledge_usd or 0) + add
    agent = db.get(Agent, t.agent_id) if t.agent_id else None
    if agent and _can_trade(ex):
        org = agent.org
        if org is not None:
            from . import orgs as O

            O.deposit(db, org, who, add)
            O.allocate(db, org, agent, add)
        else:
            agent.cash += add
            agent.starting_equity += add
            agent.peak_equity += add
            agent.day_start_equity += add
    db.flush()
    bs = backers(db, t)
    tail = "" if (agent and _can_trade(ex)) else f" Stake it yourself: {_link('/#/join' + (f'?legion={h.org_slug}' if h.org_slug else ''))}"
    say(db, h, f"{who} is in for {_usd(add)} on thesis {t.n}. Pot is {_usd(_pledged(bs))} from {_who_line(bs)}.{tail}", thesis_id=t.id)


# ------------------------------------------------------------------------------------------------ firing and settling

def _open(db: Session, ex: ExchangeAdapter, h: Huddle, t: Thesis, ev: HuddleEvent | None, reason: str,
          market_override: str | None = None, allocation_usd: float | None = None) -> Trigger | None:
    from .router import submit

    agent = db.get(Agent, t.agent_id) if t.agent_id else None
    spec = t.spec or {}
    market = market_override or spec.get("market")
    if not agent or not market or agent.status != "live":
        return None
    side = spec.get("side", "long")
    mark = ex.mark(market)
    eq = ex.equity(db, agent)
    gross = sum(abs(sz) * ex.mark(m) for m, (sz, _) in ex.positions(db, agent).items())
    target = allocation_usd if allocation_usd is not None else float(spec.get("size_pct", 1.0)) * eq
    notional = min(target, max(0.0, eq - gross))
    if notional <= 1:
        say(db, h, f"Thesis {t.n} saw {ev.label if ev else 'its signal'} but its cash is already in a position, so it skipped this one.", thesis_id=t.id)
        return None
    order, verdict = submit(db, ex, agent, market, "buy" if side == "long" else "sell", notional / mark, reason=reason)
    if not order.filled_size:
        say(db, h, f"Thesis {t.n} tried to {('buy' if side == 'long' else 'short')} {market} and the sandbox said no: {verdict.reason}.", thesis_id=t.id)
        return None
    hold = int(spec.get("hold_days", 7)) if spec.get("type") == "event_buy" else 3650
    tr = Trigger(thesis_id=t.id, event_id=ev.id if ev else 0, market=market, side=side, size=order.filled_size, entry_px=order.fill_px,
                 exit_at=_now() + dt.timedelta(days=hold))
    db.add(tr)
    db.flush()
    return tr


EVENT_SETS = {"hack": "major_hacks", "podcast": "dwarkesh"}  # event kind -> the event_buy rules it fires


def fire(db: Session, ex: ExchangeAdapter, ev: HuddleEvent) -> int:
    """Run every live event rule this event reaches (hack rules on hacks, Dwarkesh rules on new episodes). Returns how many opened a position."""
    q = select(Thesis).where(Thesis.status == "live", Thesis.kind == "rule")
    if ev.huddle_id is not None:
        q = q.where(Thesis.huddle_id == ev.huddle_id)
    opened = 0
    for t in db.scalars(q).all():
        spec = t.spec or {}
        if spec.get("type") != "event_buy" or spec.get("event_set") != EVENT_SETS.get(ev.kind) or _aware(t.armed_at) > _aware(ev.created_at):
            continue
        if db.scalar(select(Trigger).where(Trigger.thesis_id == t.id, Trigger.event_id == ev.id)):
            continue
        h = db.get(Huddle, t.huddle_id)
        try:
            tr = _open(db, ex, h, t, ev, f"thesis {t.n}: {ev.label[:80]}")
        except Exception as e:  # one rule that cannot trade (no price, exchange refusal) must not stop the others
            log.warning("thesis %s could not fire on event %s: %s", t.id, ev.id, e)
            say(db, h, f"Idea {(t.spec or {}).get('_parent_n') or t.n} saw {ev.label} but could not trade: {str(e)[:120] or type(e).__name__}.", thesis_id=t.id)
            continue
        if tr:
            opened += 1
            verb = "bought" if tr.side == "long" else "shorted"
            src = f" ({ev.source})" if ev.source else ""
            whose = f"of their {_usd(_pledged(backers(db, t)))}" if (t.spec or {}).get("_telegram_copy_owner") else "of the pot"
            real = " Real order, from their own account." if _real(ex) and (t.spec or {}).get("_telegram_copy_owner") else ""
            say(db, h, f"{_name(t)} fired on {ev.label}{src}: {verb} {tr.size:.4g} {tr.market} at {_px(tr.entry_px)}, {_usd(tr.size * tr.entry_px)} {whose}. "
                       f"Closes {_aware(tr.exit_at):%b %-d}.{real}", "result", t.id)
    return opened


def score(db: Session, t: Thesis) -> tuple[int, int, float]:
    rows = db.scalars(select(Trigger).where(Trigger.thesis_id == t.id, Trigger.closed.is_(True))).all()
    return len(rows), sum(1 for r in rows if (r.pnl_usd or 0) > 0), sum(r.pnl_usd or 0 for r in rows)


def _close(db: Session, ex: ExchangeAdapter, t: Thesis, tr: Trigger, now: dt.datetime, why: str) -> bool:
    """Close one open position with a reduce-only order and post the result. False when the exchange did not fill it."""
    from .router import submit

    agent = db.get(Agent, t.agent_id) if t.agent_id else None
    if not agent:
        tr.closed = True
        return False
    order, _ = submit(db, ex, agent, tr.market, "sell" if tr.side == "long" else "buy", tr.size, reduce_only=True, reason=f"thesis {t.n}: {why}")
    if not order.filled_size:
        return False
    sign = 1 if tr.side == "long" else -1
    tr.exit_px, tr.closed = order.fill_px, True
    tr.pnl_usd = round(sign * (order.fill_px - tr.entry_px) * tr.size - order.exchange_fee_usd - order.builder_fee_usd, 2)
    pct = sign * (order.fill_px / tr.entry_px - 1) * 100
    db.flush()
    n, wins, pnl = score(db, t)
    h = db.get(Huddle, t.huddle_id)
    days = max(1, round((now - _aware(tr.opened_at)).total_seconds() / 86400))
    span = "1 day" if days == 1 else f"{days} days"
    say(db, h, f"{_name(t)} closed: {tr.market} {pct:+.1f}% over {span}, {_px(tr.size * tr.entry_px)} became {_px(tr.size * tr.entry_px + tr.pnl_usd)} ({_signed_usd(tr.pnl_usd)}). "
               f"Its record: {wins} of {n} up, {_signed_usd(pnl)}.", "result", t.id)
    return True


def settle(db: Session, ex: ExchangeAdapter, now: dt.datetime | None = None) -> int:
    """Close every position whose hold is over and post the result with the running score."""
    now = now or _now()
    closed = 0
    for tr in db.scalars(select(Trigger).where(Trigger.closed.is_(False))).all():
        if _aware(tr.exit_at) > now:
            continue
        t = db.get(Thesis, tr.thesis_id)
        if t and _close(db, ex, t, tr, now, "hold over"):
            closed += 1
        elif not t:
            tr.closed = True
    return closed


def close_mine(db: Session, ex: ExchangeAdapter, h: Huddle, sender: str, n: int) -> str | None:
    """'close 2': close the sender's own copy of idea 2 now. Each person closes only their own position."""
    mine = [t for t in _theses(db, h, ("live",)) if (t.spec or {}).get("_parent_n") == n and (t.spec or {}).get("_telegram_copy_owner") == sender]
    if not mine:
        return f"You have no open copy of idea {n} here."
    now, closed, held = _now(), 0, 0
    for t in mine:
        for tr in db.scalars(select(Trigger).where(Trigger.thesis_id == t.id, Trigger.closed.is_(False))).all():
            held += 1
            closed += _close(db, ex, t, tr, now, "closed by its owner")
        if not db.scalar(select(Trigger).where(Trigger.thesis_id == t.id, Trigger.closed.is_(False))):
            t.status = "closed"  # nothing open and nothing more to fire: this copy is done
    if not held:
        return f"Your copy of idea {n} had no open position, so it is stopped: it will not fire again."
    return None if closed == held else f"The exchange did not fill the close for {held - closed} of your positions on idea {n}. Try again, or close it in Hyperliquid."


def report_event(db: Session, ex: ExchangeAdapter, label: str, source: str | None = None, huddle_id: int | None = None, by: str | None = None,
                 kind: str = "hack") -> HuddleEvent:
    ev = HuddleEvent(kind=kind, label=label.strip()[:200], source=(source or None), huddle_id=huddle_id, reported_by=by)
    db.add(ev)
    db.flush()
    if kind in EVENT_SETS:
        fire(db, ex, ev)
    return ev


# ------------------------------------------------------------------------------------------------ commands

def _status(db: Session, h: Huddle, ex: ExchangeAdapter | None = None) -> str:
    """Where each idea stands, in a sentence each. A copy chat's per-person copies roll up under the idea."""
    rows = [t for t in _theses(db, h) if t.status != "dropped" and not (t.spec or {}).get("_telegram_copy_owner")]
    if not rows:
        return "Nothing yet. Say an idea, or tap /demo for the four."
    out = []
    for t in rows[-6:]:
        bs = backers(db, t)
        label = t.label if len(t.label) <= 60 else t.label[:57].rsplit(" ", 1)[0] + "…"
        if t.kind == "call":
            out.append(f"{t.n}. {label}: {t.outcome or ('open' if t.status == 'live' else 'needs backing')}, backed by {sum(b.approved for b in bs)}.")
            continue
        ids = (t.spec or {}).get("copy_ids") or [t.id]
        trigs = db.scalars(select(Trigger).where(Trigger.thesis_id.in_(ids))).all()
        held = [r for r in trigs if not r.closed]
        done = [r for r in trigs if r.closed]
        money = ", ".join(f"{b.who} {_usd(b.pledge_usd)}" for b in bs if b.approved and b.pledge_usd)
        if t.status == "proposed":
            state = f"waiting for backing ({sum(b.approved for b in bs)} of {h.quorum})"
        elif held:
            cost = sum(r.entry_px * r.size for r in held)
            try:
                pnl = sum((1 if r.side == "long" else -1) * (ex.mark(r.market) - r.entry_px) * r.size for r in held) if ex else None
            except Exception:  # a mark we cannot read right now is left out, not guessed
                pnl = None
            state = f"{pnl / cost * 100:+.1f}% so far ({_signed_usd(pnl)})" if pnl is not None and cost else "open"
        elif t.status == "live":
            ev = {"major_hacks": "the next hack", "dwarkesh": "the next episode"}.get((t.spec or {}).get("event_set"), "its signal")
            state = f"armed, waiting for {ev}"
        else:
            state = t.status
        if done:
            state += f"; closed {sum(1 for r in done if (r.pnl_usd or 0) > 0)} of {len(done)} up, {_signed_usd(sum(r.pnl_usd or 0 for r in done))}"
        out.append(f"{t.n}. {label}: {state}." + (f" In: {money}." if money else ""))
    return "Here's where things stand:\n" + "\n".join(out)


def _events(db: Session, h: Huddle, n: int | None) -> str:
    """The events an event rule was tested on, each with the market's move over the hold after it."""
    from .backtest import load_events

    rules = [t for t in _theses(db, h) if ((t.test or {}).get("events") or {}).get("per_event")]
    t = _by_n(db, h, n) if n else (rules[-1] if rules else None)
    per = ((t.test or {}).get("events") or {}).get("per_event") if t else None
    if not per:
        return f"Idea {n} is not tested on events." if n else "No event idea here yet. Try \"let's buy XMR every time a major company gets hacked\"."
    s = t.test
    names: dict[str, list[str]] = {}
    for r in load_events(s.get("event_set") or "major_hacks") if s.get("event_set") != "custom" else []:
        names.setdefault(r["date"].isoformat(), []).append(r.get("company") or r.get("title") or "")
    hold = s.get("hold_days") or 1
    what = {"major_hacks": "hacks", "dwarkesh": "Dwarkesh episodes"}.get(s.get("event_set"), "dates")
    up = sum(1 for _, m in per if m > 0)
    lines = [f"Idea {t.n} was tested on {len(per)} {what}. {s['market']} over the {hold}d after each ({up} up):"]
    lines += [f"{d}  {m:+.1f}%  {' / '.join(names.get(d, []))[:60]}".rstrip() for d, m in per]
    ev = s["events"]
    lines.append(f"Average {ev['event_mean_pct']:+.1f}% after an event, {ev['any_mean_pct']:+.1f}% after any day.")
    return "\n".join(lines)


def _score_board(db: Session, h: Huddle) -> str:
    people: dict[str, list[float]] = {}
    for t in _theses(db, h):
        if t.status == "dropped":
            continue
        if t.kind == "call" and t.outcome:
            people.setdefault(t.author, [0, 0, 0.0])
            people[t.author][0] += 1
            people[t.author][1] += t.outcome == "hit"
        elif t.kind == "rule":
            n, wins, pnl = score(db, t)
            parent = _by_n(db, h, (t.spec or {}).get("_parent_n")) if (t.spec or {}).get("_parent_n") else None
            if n:
                p = people.setdefault(parent.author if parent else t.author, [0, 0, 0.0])
                p[0] += n
                p[1] += wins
                p[2] += pnl
    if not people:
        return "No results yet. A trade counts once it closes; a hold counts when you close it."
    rows = sorted(people.items(), key=lambda kv: (-(kv[1][1] / kv[1][0]), -kv[1][2]))
    return "Score, by whose idea it was:\n" + "\n".join(f"{who}: {int(w)} of {int(n)} right" + (f", {_signed_usd(p)}" if p else "") for who, (n, w, p) in rows)


def command(db: Session, ex: ExchangeAdapter, h: Huddle, sender: str, body: str) -> bool:
    """Handle 'protoss <command>'. True when it was one."""
    low = body.strip().lower()
    if low in ("", "help", "?", "what can you do", "commands"):
        say(db, h, HELP)
        return True
    if low in ("status", "theses", "board", "what's live", "whats live"):
        say(db, h, _status(db, h, ex))
        return True
    if m := re.fullmatch(r"(?:show\s+(?:me\s+)?(?:the\s+)?)?events?(?:\s+(?:for\s+)?(?:idea\s+)?#?(\d+))?", low):
        say(db, h, _events(db, h, int(m.group(1)) if m.group(1) else None))
        return True
    if low in ("score", "scoreboard", "leaderboard", "who's right", "whos right"):
        say(db, h, _score_board(db, h))
        return True
    if m := re.fullmatch(r"(?:close|exit|sell)\s+(?:my\s+)?(?:copy\s+of\s+)?(?:idea\s+)?#?(\d+)", low):
        if (note := close_mine(db, ex, h, sender, int(m.group(1)))) is not None:
            say(db, h, note)
        return True
    if m := re.fullmatch(r"back\s+#?(\d+)", low):
        t = _by_n(db, h, int(m.group(1)))
        if not t or t.status != "proposed":
            say(db, h, f"Thesis {m.group(1)} is not open for backing.")
        else:
            approve(db, ex, h, t, sender, True)
        return True
    if m := re.match(r"^(?:hack|breach|event)\s*[:\-]?\s*(.+)$", body.strip(), re.I):
        rest = m.group(1).strip()
        url = re.search(r"https?://\S+", rest)
        label = rest.replace(url.group(0), "").strip(" .,-") if url else rest
        ev = report_event(db, ex, label or "a hack", url.group(0) if url else None, h.id, sender)
        live = [t for t in _theses(db, h, ("live",)) if (t.spec or {}).get("type") == "event_buy"]
        if not db.scalar(select(Trigger).where(Trigger.event_id == ev.id)):
            say(db, h, f"Logged: {ev.label}. " + ("No live hack rule in this chat to fire." if not live else "Nothing fired; see above."))
        return True
    if m := re.match(r"^(hit|miss|right|wrong)\s+#?(\d+)$", low):
        t = _by_n(db, h, int(m.group(2)))
        if not t or t.kind != "call":
            say(db, h, f"There is no call {m.group(2)} here.")
            return True
        t.outcome, t.status = ("hit" if m.group(1) in ("hit", "right") else "miss"), "closed"
        say(db, h, f"Call {t.n} from {t.author}: {t.outcome}, marked by {sender}.\n{_score_board(db, h)}", "result", t.id)
        return True
    if m := re.match(r"^(drop|cancel|kill)\s+#?(\d+)$", low):
        t = _by_n(db, h, int(m.group(2)))
        if not t:
            say(db, h, f"There is no thesis {m.group(2)} here.")
            return True
        if t.status == "live" and t.kind == "rule":
            say(db, h, f"Thesis {t.n} is live with money in it; the legion leader halts it from the legion page.")
            return True
        t.status = "dropped"
        say(db, h, f"Dropped thesis {t.n}.")
        return True
    return False


# ------------------------------------------------------------------------------------------------ the entry point

def ingest(db: Session, ex: ExchangeAdapter, h: Huddle, sender: str, text: str = "", guid: str | None = None, reaction: str | None = None,
           target_guid: str | None = None, from_me: bool = False, ts: dt.datetime | None = None) -> HuddleMessage | None:
    """One chat row in. Side effects (bot replies) land in the outbox. Returns the stored row, or None for an echo."""
    text = (text or "").strip()
    if guid and db.scalar(select(HuddleMessage).where(HuddleMessage.huddle_id == h.id, HuddleMessage.guid == guid)):
        return None  # bridge retried
    if from_me:
        # our own send coming back through chat.db: attach its guid so tapbacks on the card resolve
        echo = db.scalars(select(HuddleMessage).where(HuddleMessage.huddle_id == h.id, HuddleMessage.from_bot.is_(True), HuddleMessage.guid.is_(None))
                          .order_by(HuddleMessage.id.desc()).limit(20)).all()
        norm = lambda s: re.sub(r"\s+", " ", s or "").strip()  # noqa: E731
        hit = next((m for m in echo if norm(m.text) == norm(text)), None)
        if hit:
            hit.guid, hit.delivered = guid, True
            return None
    kind = "reaction" if reaction else "text"
    row = HuddleMessage(huddle_id=h.id, sender=sender, text=text, guid=guid, kind=kind, reaction=reaction, target_guid=target_guid,
                        delivered=True, ts=ts or _now())
    db.add(row)
    db.flush()
    if h.is_web and not guid:
        row.guid = f"w{row.id}"

    if reaction:
        removed = reaction.startswith("-")
        r = reaction.lstrip("-")
        card = db.scalar(select(HuddleMessage).where(HuddleMessage.huddle_id == h.id, HuddleMessage.guid == target_guid)) if target_guid else None
        t = db.get(Thesis, card.thesis_id) if card and card.thesis_id else None
        if t and t.status == "proposed" and (r in BACKING or r == "dislike"):
            row.thesis_id = t.id
            approve(db, ex, h, t, sender, on=(r in BACKING and not removed))
        return row

    addressed = bool(ADDRESS.match(text))
    body = ADDRESS.sub("", text, count=1) if addressed else text
    if not addressed and (m := CLOSE_ASK.match(text)):  # "close my idea 2"
        addressed, body = True, f"close {m.group(1)}"
    if not addressed and EVENTS_ASK.search(text):  # "can you show me what the 25 events are"
        addressed, body = True, "events" + (f" {m.group(1)}" if (m := re.search(r"idea\s+#?(\d+)", text, re.I)) else "")
    if addressed and command(db, ex, h, sender, body):
        return row
    t = _latest_open(db, h)
    if t and (m := EACH.search(body)):
        row.thesis_id = t.id
        set_each(db, ex, h, t, sender, _money(m.group(1)) * (1000 if re.search(r"\d\s*k\b", m.group(0), re.I) else 1))
        return row
    if t and (m := IN_FOR.search(body)):
        row.thesis_id = t.id
        approve(db, ex, h, t, sender, True, _money(m.group(1) or m.group(2)))
        bs = backers(db, t)
        if t.status == "proposed":
            say(db, h, f"{sender} is in for {_usd(_backer(db, t, sender).pledge_usd or 0)} on idea {t.n}. {_pledge_line(bs)}", thesis_id=t.id)
        return row
    if t and YES.match(body):
        row.thesis_id = t.id
        approve(db, ex, h, t, sender, True)
        return row
    if t and NO.match(body):
        row.thesis_id = t.id
        approve(db, ex, h, t, sender, False)
        return row
    live = _latest_live_rule(db, h) if not t else None
    if live and (YES.match(body) or IN_FOR.search(body)):
        if is_copy_chat(h):
            say(db, h, "These separate demo copies are already live. Start a new /idea to change the allocation. No additional funds moved.")
            return row
        m = IN_FOR.search(body)
        row.thesis_id = live.id
        join_live(db, ex, h, live, sender, _money(m.group(1) or m.group(2)) if m else None)
        return row
    from .lab import theme  # lab imports nothing from here; resolved lazily like the planner in propose

    if addressed or THESIS_CUE.search(body) or theme(body):  # one of the demo ideas said plainly is a proposal too
        propose(db, h, sender, body, addressed)
        return row
    if addressed:
        say(db, h, HELP)
    return row


# ------------------------------------------------------------------------------------------------ hack feed (optional)

def parse_feed(xml_text: str) -> list[dict]:
    """RSS 2.0 or Atom items -> [{title, link, ts}]. Tolerant: bad items are skipped."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    out = []
    atom = "{http://www.w3.org/2005/Atom}"
    for it in root.iter():
        tag = it.tag.split("}")[-1]
        if tag not in ("item", "entry"):
            continue
        title = (it.findtext("title") or it.findtext(f"{atom}title") or "").strip()
        link = (it.findtext("link") or "").strip()
        if not link:
            el = it.find(f"{atom}link")
            link = el.get("href", "") if el is not None else ""
        when = it.findtext("pubDate") or it.findtext(f"{atom}updated") or it.findtext(f"{atom}published")
        ts = None
        if when:
            try:
                ts = parsedate_to_datetime(when) if "," in when else dt.datetime.fromisoformat(when.replace("Z", "+00:00"))
            except (TypeError, ValueError):
                ts = None
        if title:
            out.append({"title": title, "link": link, "ts": ts})
    return out


HACK_WORDS = re.compile(r"\b(hack(?:ed|ers?)?|breach(?:ed)?|exploit(?:ed)?|ransomware|drained|stolen|cyberattack|compromised)\b", re.I)
_last_feed_poll = 0.0


def poll_feeds(db: Session, ex: ExchangeAdapter, fetch=None) -> int:
    """Read HUDDLE_HACK_FEEDS (RSS/Atom URLs) and report new hack headlines as global events. Off when unset."""
    s = get_settings()
    added = 0
    for url in s.huddle_hack_feeds:
        try:
            body = fetch(url) if fetch else httpx.get(url, timeout=10.0, follow_redirects=True).text
        except Exception as e:  # a dead feed must not stop the others
            log.warning("hack feed %s failed: %s", url, e)
            continue
        for it in parse_feed(body):
            if not HACK_WORDS.search(it["title"]) or (it["ts"] and _aware(it["ts"]) < _now() - dt.timedelta(days=2)):
                continue
            key = it["link"] or it["title"]
            if db.scalar(select(HuddleEvent).where((HuddleEvent.source == key) | (HuddleEvent.label == it["title"][:200]))):
                continue
            report_event(db, ex, it["title"], key, None, "feed")
            added += 1
    return added


def poll_podcasts(db: Session, ex: ExchangeAdapter, fetch=None) -> int:
    """Read HUDDLE_PODCAST_FEEDS and report each episode published in the last 2 days once, as a podcast event."""
    added = 0
    for url in get_settings().huddle_podcast_feeds:
        try:
            body = fetch(url) if fetch else httpx.get(url, timeout=10.0, follow_redirects=True).text
        except Exception as e:
            log.warning("podcast feed %s failed: %s", url, e)
            continue
        for it in parse_feed(body):
            if not it["ts"] or _aware(it["ts"]) < _now() - dt.timedelta(days=2):
                continue
            key = it["link"] or it["title"]
            if db.scalar(select(HuddleEvent).where(HuddleEvent.kind == "podcast", HuddleEvent.source == key)):
                continue
            report_event(db, ex, f"New Dwarkesh Podcast episode: {it['title']}", key, None, "feed", kind="podcast")
            added += 1
    return added


def tick(db: Session, ex: ExchangeAdapter) -> dict:
    """Worker hook: close finished holds, and read the hack and podcast feeds every few minutes."""
    import time

    global _last_feed_poll
    out = {"settled": settle(db, ex), "feed_events": 0}
    s = get_settings()
    if (s.huddle_hack_feeds or (s.huddle_podcast_feeds and s.arena_mode != "sim")) and time.monotonic() - _last_feed_poll > 600:
        _last_feed_poll = time.monotonic()
        out["feed_events"] = poll_feeds(db, ex) + (poll_podcasts(db, ex) if s.arena_mode != "sim" else 0)
    return out


# ------------------------------------------------------------------------------------------------ API

def exchange() -> ExchangeAdapter:
    return get_exchange()


def _require_admin(token: str | None) -> None:
    if not token or not secrets.compare_digest(token, get_settings().admin_token):
        raise HTTPException(403, "admin token required")


def _guard(h: Huddle, token: str | None) -> None:
    """Web huddles are open in sim/paper (a demo of the flow). Real chats only through the bridge's admin token."""
    if h.is_web and get_settings().arena_mode in ("sim", "paper"):
        return
    _require_admin(token)


def _msg_out(m: HuddleMessage) -> dict:
    return {"id": m.id, "ts": _aware(m.ts).isoformat(), "guid": m.guid, "sender": m.sender, "text": m.text, "from_bot": m.from_bot,
            "kind": m.kind, "reaction": m.reaction, "target_guid": m.target_guid, "thesis_id": m.thesis_id}


def thesis_out(db: Session, t: Thesis) -> dict:
    bs = backers(db, t)
    n, wins, pnl = score(db, t)
    trig = db.scalars(select(Trigger).where(Trigger.thesis_id == t.id).order_by(Trigger.id)).all()
    spec = t.spec or {}
    holdings = spec.get("holdings") or ([{"market": spec["market"], "weight": 1.0}] if spec.get("market") else [])
    return {
        "id": t.id, "n": t.n, "author": t.author, "text": t.text, "kind": t.kind, "label": t.label, "status": t.status, "outcome": t.outcome,
        "each_usd": t.each_usd, "agent_id": t.agent_id, "test": t.test, "created_at": _aware(t.created_at).isoformat(),
        "backers": [{"who": b.who, "approved": b.approved, "pledge_usd": b.pledge_usd} for b in bs],
        "pledged_usd": round(_pledged(bs), 2), "record": {"closed": n, "up": wins, "pnl_usd": round(pnl, 2)},
        "proposal": {"version": 1, "holdings": holdings, "instrument": "perpetual", "automatic_updates": False},
        "triggers": [{"market": r.market, "side": r.side, "size": r.size, "entry_px": r.entry_px, "exit_px": r.exit_px, "pnl_usd": r.pnl_usd,
                      "opened_at": _aware(r.opened_at).isoformat(), "exit_at": _aware(r.exit_at).isoformat(), "closed": r.closed} for r in trig],
    }


def huddle_out(db: Session, h: Huddle, limit: int = 200) -> dict:
    msgs = db.scalars(select(HuddleMessage).where(HuddleMessage.huddle_id == h.id).order_by(HuddleMessage.id.desc()).limit(limit)).all()
    people = sorted({m.sender for m in db.scalars(select(HuddleMessage).where(HuddleMessage.huddle_id == h.id, HuddleMessage.from_bot.is_(False))).all()})
    return {"id": h.id, "chat_id": h.chat_id if h.is_web else ("telegram" if h.chat_id.startswith("telegram:") else "imessage"), "title": h.title, "org_slug": h.org_slug, "quorum": h.quorum,
            "mode": get_settings().arena_mode,
            "people": people, "messages": [_msg_out(m) for m in reversed(msgs)], "theses": [thesis_out(db, t) for t in _theses(db, h)]}


class HuddleIn(BaseModel):
    chat_id: str = Field(min_length=3, max_length=128)
    title: str | None = Field(default=None, max_length=80)
    org_slug: str | None = None
    quorum: int | None = Field(default=None, ge=1, le=20)


class MessageIn(BaseModel):
    sender: str = Field(min_length=1, max_length=64)
    text: str = Field(default="", max_length=2000)
    guid: str | None = Field(default=None, max_length=80)
    reaction: str | None = Field(default=None, pattern=r"^-?(like|love|dislike|laugh|emphasize|question)$")
    target_guid: str | None = Field(default=None, max_length=80)
    from_me: bool = False


class EventIn(BaseModel):
    label: str = Field(min_length=3, max_length=200)
    source: str | None = Field(default=None, max_length=400)
    huddle_id: int | None = None


@router.post("/huddle", status_code=201)
def create_huddle(body: HuddleIn, x_admin_token: str | None = Header(default=None), db: Session = DbDep):
    if not body.chat_id.startswith("web:") or get_settings().arena_mode in ("testnet", "mainnet"):
        _require_admin(x_admin_token)
    h = get_or_create(db, body.chat_id, body.title, body.org_slug)
    if body.quorum:
        h.quorum = body.quorum
    if body.org_slug is not None:
        h.org_slug = body.org_slug if db.scalar(select(Org).where(Org.slug == body.org_slug)) else None
    return huddle_out(db, h)


@router.get("/huddle/web/{name}")
def web_huddle(name: str, db: Session = DbDep):
    name = re.sub(r"[^a-z0-9-]", "", name.lower())[:40] or "demo"
    h = db.scalar(select(Huddle).where(Huddle.chat_id == f"web:{name}"))
    if h is None:
        org = db.scalar(select(Org).where(Org.slug == name))
        h = get_or_create(db, f"web:{name}", org.name if org else name.replace("-", " ").capitalize(), org.slug if org else None)
        say(db, h, "This chat is wired to the Lab. Say a trade idea and I test it on Hyperliquid history; thumbs up to back it, \"$50 each\" to stake. Say protoss help for the rest.")
    return huddle_out(db, h)


@router.get("/huddle/{hid}")
def get_huddle(hid: int, x_admin_token: str | None = Header(default=None), db: Session = DbDep):
    h = db.get(Huddle, hid)
    if not h:
        raise HTTPException(404, "no such huddle")
    _guard(h, x_admin_token)
    return huddle_out(db, h)


@router.post("/huddle/{hid}/messages", status_code=201)
def post_message(hid: int, body: MessageIn, x_admin_token: str | None = Header(default=None), db: Session = DbDep, ex: ExchangeAdapter = Depends(exchange)):
    h = db.get(Huddle, hid)
    if not h:
        raise HTTPException(404, "no such huddle")
    _guard(h, x_admin_token)
    sender = body.sender.strip()
    if sender.lower() == BOT.lower():
        raise HTTPException(422, "that name is the bot's")
    row = ingest(db, ex, h, sender, body.text, body.guid, body.reaction, body.target_guid, body.from_me)
    return {"stored": row is not None, "id": row.id if row else None}


@router.get("/huddle/{hid}/outbox")
def outbox(hid: int, x_admin_token: str | None = Header(default=None), db: Session = DbDep):
    _require_admin(x_admin_token)
    rows = db.scalars(select(HuddleMessage).where(HuddleMessage.huddle_id == hid, HuddleMessage.from_bot.is_(True), HuddleMessage.delivered.is_(False))
                      .order_by(HuddleMessage.id)).all()
    return [_msg_out(m) for m in rows]


class DeliveredIn(BaseModel):
    ids: list[int]


@router.post("/huddle/{hid}/delivered")
def delivered(hid: int, body: DeliveredIn, x_admin_token: str | None = Header(default=None), db: Session = DbDep):
    _require_admin(x_admin_token)
    n = 0
    for m in db.scalars(select(HuddleMessage).where(HuddleMessage.huddle_id == hid, HuddleMessage.id.in_(body.ids))).all():
        m.delivered = True
        n += 1
    return {"delivered": n}


@router.post("/huddle/tick")
def huddle_tick_route(x_admin_token: str | None = Header(default=None), db: Session = DbDep, ex: ExchangeAdapter = Depends(exchange)):
    """Close holds whose time is up and read the event feeds. Only this, so a bridge can drive it without the full
    worker (which also marks and snapshots every agent)."""
    _require_admin(x_admin_token)
    return tick(db, ex)


@router.post("/huddle/events", status_code=201)
def post_event(body: EventIn, x_admin_token: str | None = Header(default=None), db: Session = DbDep, ex: ExchangeAdapter = Depends(exchange)):
    _require_admin(x_admin_token)
    ev = report_event(db, ex, body.label, body.source, body.huddle_id, "admin")
    return {"id": ev.id, "fired": len(db.scalars(select(Trigger).where(Trigger.event_id == ev.id)).all())}


@router.get("/theses/{tid}")
def get_thesis(tid: int, db: Session = DbDep):
    t = db.get(Thesis, tid)
    if not t:
        raise HTTPException(404, "no such thesis")
    h = db.get(Huddle, t.huddle_id)
    return thesis_out(db, t) | {"huddle": {"id": h.id, "title": h.title, "web": h.chat_id.split(":", 1)[1] if h.is_web else None, "org_slug": h.org_slug}}
