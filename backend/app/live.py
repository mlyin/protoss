"""Independent mainnet buy intents. Only the user's browser signs and submits orders.

The server uses /info exclusively. A Telegram pledge creates a review request,
never an order. Quotes expire; one persisted client order ID identifies each intent.
"""
from __future__ import annotations

import datetime as dt
import json
import secrets
import time
import urllib.error
import urllib.request
from decimal import Decimal, ROUND_DOWN

from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import BigInteger, ForeignKey, Integer, JSON, String, UniqueConstraint, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from .auth import require_admin
from .config import get_settings
from .db import Base, DbDep
from .huddle import Huddle, say
from .telegram import WalletConnection, VerifyIn, bearer, digest

INFO = "https://api.hyperliquid.xyz/info"
MARKETS = {"ANT": "xyz:ANT", "ANTHROPIC": "xyz:ANT", "XYZ:ANT": "xyz:ANT", "BTC": "BTC", "ETH": "ETH"}


def enabled():
    if not get_settings().telegram_live_enabled:
        raise HTTPException(403, "Real-trade review is not enabled on this server.")


router = APIRouter(prefix="/live", tags=["live wallet review"], dependencies=[Depends(enabled)])


class LiveIdea(Base):
    __tablename__ = "live_ideas"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    huddle_id: Mapped[int] = mapped_column(ForeignKey("huddles.id"))
    request_id: Mapped[str] = mapped_column(String(100), unique=True)
    market: Mapped[str] = mapped_column(String(32))


class LiveIntent(Base):
    __tablename__ = "live_intents"
    __table_args__ = (UniqueConstraint("idea_id", "user_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    idea_id: Mapped[int] = mapped_column(ForeignKey("live_ideas.id"))
    user_id: Mapped[str] = mapped_column(String(24))
    display_name: Mapped[str] = mapped_column(String(80))
    budget: Mapped[str] = mapped_column(String(32))
    wallet: Mapped[str | None] = mapped_column(String(42), nullable=True)
    token_hash: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    token_expires: Mapped[int] = mapped_column(BigInteger, default=0)
    challenge: Mapped[str] = mapped_column(String(1500), default="")
    status: Mapped[str] = mapped_column(String(24), default="draft")
    quote: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    quote_nonce: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    receipt: Mapped[dict | None] = mapped_column(JSON, nullable=True)


def info(body):
    request = urllib.request.Request(INFO, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.load(response)
    except (OSError, ValueError) as exc:
        raise HTTPException(503, "Hyperliquid could not be reached. No substitute prices were used.") from exc


def now_ms():
    return int(time.time() * 1000)


def group(db, hid):
    h = db.get(Huddle, hid)
    if not h or not h.chat_id.startswith("telegram:"):
        raise HTTPException(404, "Telegram group not found.")
    return h


def public_intent(row):
    return {"id": row.id, "idea_id": row.idea_id, "participant": row.display_name, "telegram_user_id": row.user_id,
            "budget": row.budget, "wallet": row.wallet, "status": row.status, "receipt": row.receipt}


class IdeaIn(BaseModel):
    huddle_id: int
    request_id: str = Field(min_length=1, max_length=100)
    market: str = Field(max_length=32)


class IntentIn(BaseModel):
    idea_id: int
    telegram_user_id: str = Field(pattern=r"^[1-9][0-9]{0,19}$")
    display_name: str = Field(min_length=1, max_length=80)
    budget: Decimal = Field(ge=12, le=100, decimal_places=2, allow_inf_nan=False)


class LinkIn(BaseModel):
    telegram_user_id: str
    huddle_id: int


@router.post("/ideas", dependencies=[Depends(require_admin)])
def create_idea(body: IdeaIn, db=DbDep):
    group(db, body.huddle_id)
    market = MARKETS.get(body.market.upper())
    if not market:
        raise HTTPException(422, "Start with ANT, BTC, or ETH. One market per real-trade idea.")
    row = db.scalar(select(LiveIdea).where(LiveIdea.request_id == body.request_id))
    if row is None:
        row = LiveIdea(huddle_id=body.huddle_id, request_id=body.request_id, market=market)
        db.add(row)
        db.flush()
    return {"id": row.id, "market": row.market}


@router.post("/intents", dependencies=[Depends(require_admin)])
def create_intent(body: IntentIn, db=DbDep):
    if not db.get(LiveIdea, body.idea_id):
        raise HTTPException(404, "Idea not found.")
    row = db.scalar(select(LiveIntent).where(LiveIntent.idea_id == body.idea_id, LiveIntent.user_id == body.telegram_user_id))
    if row is not None:
        if Decimal(row.budget) != body.budget:
            raise HTTPException(409, "This request already has a fixed amount. Start a new idea to change it.")
        return public_intent(row)
    row = LiveIntent(id=secrets.token_hex(16), idea_id=body.idea_id, user_id=body.telegram_user_id,
                     display_name=body.display_name, budget=str(body.budget))
    db.add(row)
    db.flush()
    return public_intent(row)


@router.post("/intents/{iid}/link", dependencies=[Depends(require_admin)])
def private_link(iid: str, body: LinkIn, db=DbDep):
    row = db.get(LiveIntent, iid)
    if not row or row.user_id != body.telegram_user_id or db.get(LiveIdea, row.idea_id).huddle_id != body.huddle_id:
        raise HTTPException(404, "This trade request belongs to another participant or group.")
    token = secrets.token_urlsafe(32)
    row.token_hash, row.token_expires = digest(token), now_ms() + 3_600_000
    row.challenge = (f"Connect to Protoss real-trade review\nOrigin: {get_settings().app_url}\n"
                     f"Telegram user: {row.user_id}\nRequest: {row.id}\nNonce: {secrets.token_hex(24)}\n"
                     f"Expires: {row.token_expires}\nThis proves ownership only. No trade or transfer is authorized.")
    return {"url": get_settings().app_url.rstrip("/") + "/#/trade?token=" + token}


def lookup(db, authorization):
    row = db.scalar(select(LiveIntent).where(LiveIntent.token_hash == digest(bearer(authorization))))
    if not row:
        raise HTTPException(404, "Private trade request not found.")
    if row.token_expires <= now_ms():
        raise HTTPException(410, "Private link expired. Open your review button in Telegram again.")
    return row


@router.get("/review")
def review(response: Response, authorization: str | None = Header(default=None), db=DbDep):
    response.headers["Cache-Control"] = "no-store"
    row = lookup(db, authorization)
    return {**public_intent(row), "market": db.get(LiveIdea, row.idea_id).market, "challenge": row.challenge,
            "network": "mainnet", "side": "buy", "leverage": 1,
            "quote": row.quote, "signing_in_browser": True}


@router.post("/wallet")
def connect_wallet(body: VerifyIn, authorization: str | None = Header(default=None), db=DbDep):
    row = lookup(db, authorization)
    try:
        recovered = Account.recover_message(encode_defunct(text=row.challenge), signature=body.signature).lower()
    except (ValueError, TypeError, OverflowError) as exc:
        raise HTTPException(422, "Invalid ownership signature.") from exc
    if recovered != body.wallet.lower() or (row.wallet and row.wallet != recovered):
        raise HTTPException(409, "Wallet does not match this request.")
    hid = db.get(LiveIdea, row.idea_id).huddle_id
    connection = db.scalar(select(WalletConnection).where(WalletConnection.huddle_id == hid,
                                                         WalletConnection.telegram_user_id == row.user_id))
    if connection and connection.wallet and connection.wallet != recovered:
        raise HTTPException(409, "This Telegram account already connected another wallet.")
    if not connection:
        connection = WalletConnection(huddle_id=hid, telegram_user_id=row.user_id, display_name=row.display_name,
            token_hash=digest(secrets.token_urlsafe(32)), challenge=row.challenge,
            expires_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1))
        db.add(connection)
    connection.wallet = recovered
    row.wallet = recovered
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "The other participant already connected this wallet.") from exc
    return public_intent(row)


def wire(value):
    return format(value, "f").rstrip("0").rstrip(".") if "." in format(value, "f") else format(value, "f")


def live_quote(market, budget, wallet, cloid):
    dex = market.split(":")[0] if ":" in market else ""
    meta, contexts = info({"type": "metaAndAssetCtxs", "dex": dex})
    idx = next((i for i, a in enumerate(meta["universe"]) if a["name"] == market and not a.get("isDelisted")), None)
    if idx is None:
        raise HTTPException(422, "Market is not available.")
    asset, context = meta["universe"][idx], contexts[idx]
    offset = 0
    if dex:
        dexs = info({"type": "perpDexs"})
        offset = next((110000 + i * 10000 for i, d in enumerate(dexs[1:]) if d and d["name"] == dex), None)
        if offset is None:
            raise HTTPException(503, "Could not resolve the market identifier.")
    book = info({"type": "l2Book", "coin": market})
    if abs(now_ms() - int(book.get("time", 0))) > 30_000 or not book.get("levels", [[], []])[1]:
        raise HTTPException(503, "No fresh sell quote is available. Try again later.")
    ask = Decimal(book["levels"][1][0]["px"])
    if not ask.is_finite() or ask <= 0:
        raise HTTPException(503, "Invalid market price.")
    decimals = int(asset["szDecimals"])
    # Maximum 0.5% above the current ask, rounded DOWN to HL's tick precision.
    raw_limit = ask * Decimal("1.005")
    tick_places = min(6 - decimals, 4 - raw_limit.adjusted())
    limit = raw_limit.quantize(Decimal(10) ** -tick_places, rounding=ROUND_DOWN)
    size = (Decimal(budget) / limit).quantize(Decimal(10) ** -decimals, rounding=ROUND_DOWN)
    if limit < ask or size <= 0 or size * ask < 10:
        raise HTTPException(422, "This amount is too small after market size rounding.")
    state = info({"type": "clearinghouseState", "user": wallet, "dex": dex})
    if any(p["position"]["coin"] == market and Decimal(p["position"]["szi"]) != 0 for p in state.get("assetPositions", [])):
        raise HTTPException(409, "You already have a position in this market. This first version only opens new positions.")
    mode = info({"type": "userAbstraction", "user": wallet})
    if mode == "portfolioMargin":
        raise HTTPException(409, "Portfolio margin accounts are not supported in this first version.")
    account = {"mode": mode, "market_withdrawable": state.get("withdrawable"), "margin": state.get("marginSummary")}
    if mode == "unifiedAccount":
        account["spot_balances"] = info({"type": "spotClearinghouseState", "user": wallet}).get("balances", [])
    elif mode != "disabled":
        raise HTTPException(409, "This account mode is not supported in this first version.")
    elif Decimal(state.get("withdrawable", "0")) < size * limit * Decimal("1.002"):
        raise HTTPException(409, "Not enough collateral in this market account for a 1× trade plus fees. Review funding in Hyperliquid.")
    nonce = now_ms()
    if abs(nonce - int(book["time"])) > 30_000:
        raise HTTPException(503, "Market quote became stale while checking the account. Request a fresh quote.")
    return {"market": market, "wallet": wallet, "ask": str(ask), "mark": context.get("markPx"),
            "size": wire(size), "limit_price": wire(limit), "max_position_usd": str(size * limit),
            "budget": str(budget), "fee_note": "Exchange fees are additional. Protoss adds no builder fee on this flow.",
            "account": account, "observed_at": int(book["time"]), "nonce": nonce, "expires_after": nonce + 120_000, "cloid": cloid,
            "leverage_action": {"type": "updateLeverage", "asset": offset + idx, "isCross": True, "leverage": 1},
            "order_action": {"type": "order", "orders": [{"a": offset + idx, "b": True, "p": wire(limit),
                 "s": wire(size), "r": False, "t": {"limit": {"tif": "Ioc"}}, "c": cloid}], "grouping": "na"}}


@router.post("/quote")
def quote(authorization: str | None = Header(default=None), db=DbDep):
    row = lookup(db, authorization)
    if not row.wallet:
        raise HTTPException(409, "Connect and verify your wallet first.")
    if row.status != "draft":
        raise HTTPException(409, "This request is already prepared. Check its result before starting another trade.")
    q = live_quote(db.get(LiveIdea, row.idea_id).market, row.budget, row.wallet, "0x" + row.id)
    result = db.execute(update(LiveIntent).where(LiveIntent.id == row.id, LiveIntent.status == "draft").values(quote=q, quote_nonce=q["nonce"]))
    if result.rowcount != 1:
        raise HTTPException(409, "This request has already been prepared in another tab.")
    return q


class PrepareIn(BaseModel):
    nonce: int


@router.post("/prepare")
def prepare(body: PrepareIn, authorization: str | None = Header(default=None), db=DbDep):
    row = lookup(db, authorization)
    if row.status != "draft" or not row.quote or row.quote["nonce"] != body.nonce:
        raise HTTPException(409, "Request changed or was already prepared. Reload and check its result.")
    if row.quote["expires_after"] < now_ms() + 15_000:
        raise HTTPException(409, "Quote is too old. Refresh it and review the new amounts.")
    # Compare the persisted quote as well as status to close concurrent refresh/prepare races.
    result = db.execute(update(LiveIntent).where(LiveIntent.id == row.id, LiveIntent.status == "draft",
                        LiveIntent.quote_nonce == body.nonce).values(status="prepared"))
    if result.rowcount != 1:
        raise HTTPException(409, "Request changed in another tab. Reload before proceeding.")
    return row.quote


def reconcile(db, row):
    if row.status != "prepared" or not row.wallet or not row.quote:
        return public_intent(row)
    q = row.quote
    status = info({"type": "orderStatus", "user": row.wallet, "oid": q["cloid"]})
    if status.get("status") == "unknownOid":
        return public_intent(row)  # unknown is never described as filled or safe to retry
    order = status.get("order", {}).get("order", {})
    if order.get("cloid") != q["cloid"] or order.get("coin") != q["market"] or order.get("side") != "B":
        raise HTTPException(502, "Exchange order did not match this request.")
    if Decimal(order.get("origSz", "0")) != Decimal(q["size"]) or Decimal(order.get("limitPx", "0")) != Decimal(q["limit_price"]):
        raise HTTPException(502, "Exchange order size or price did not match this request.")
    fills = info({"type": "userFillsByTime", "user": row.wallet, "startTime": q["nonce"]})
    fills = [f for f in fills if f.get("oid") == order.get("oid") and f.get("coin") == q["market"]
             and f.get("side") == "B" and q["nonce"] <= f.get("time", 0) <= q["expires_after"] + 30_000]
    terminal = status.get("order", {}).get("status")
    if not fills or terminal in ("open", "triggered"):
        return public_intent(row)
    # Deduplicate individual executions, then aggregate partial fills honestly.
    fills = list({(f.get("tid"), f.get("hash"), f.get("time"), f["sz"], f["px"]): f for f in fills}.values())
    size = sum((Decimal(f["sz"]) for f in fills), Decimal(0))
    cost = sum((Decimal(f["sz"]) * Decimal(f["px"]) for f in fills), Decimal(0))
    if terminal == "filled" and size < Decimal(q["size"]):
        return public_intent(row)  # the fills endpoint may lag behind order status
    if size <= 0 or size > Decimal(q["size"]) or any(Decimal(f["px"]) > Decimal(q["limit_price"]) for f in fills):
        raise HTTPException(502, "Fill amounts did not match the reviewed order.")
    receipt = {"market": q["market"], "wallet": row.wallet, "side": "buy", "size": str(size),
               "average_price": str(cost / size), "position_value": str(cost), "order_id": order["oid"],
               "fees": [{"amount": f.get("fee"), "token": f.get("feeToken", "USDC")} for f in fills],
               "verified_at": now_ms(), "fill_times": [f["time"] for f in fills]}
    next_status = "filled" if size == Decimal(q["size"]) else "partial"
    changed = db.execute(update(LiveIntent).where(LiveIntent.id == row.id, LiveIntent.status == "prepared").values(status=next_status, receipt=receipt))
    if changed.rowcount == 1:
        idea = db.get(LiveIdea, row.idea_id)
        say(db, group(db, idea.huddle_id), f"Verified on Hyperliquid: {row.display_name} (tg:{row.user_id}) bought "
            f"{size} {q['market']} at ${cost / size:.4f}. Position ${cost:.2f}, exchange fees additional. "
            f"{'Partial fill. ' if next_status == 'partial' else ''}Wallet {row.wallet[:8]}…{row.wallet[-4:]}. Order {order['oid']}.", "result")
    db.refresh(row)
    return public_intent(row)


@router.post("/verify")
def verify(authorization: str | None = Header(default=None), db=DbDep):
    return reconcile(db, lookup(db, authorization))


@router.get("/groups/{hid}", dependencies=[Depends(require_admin)])
def group_status(hid: int, db=DbDep):
    group(db, hid)
    ideas = db.scalars(select(LiveIdea).where(LiveIdea.huddle_id == hid).order_by(LiveIdea.id.desc()).limit(10)).all()
    return [{"id": i.id, "market": i.market, "participants": [public_intent(r) for r in db.scalars(
        select(LiveIntent).where(LiveIntent.idea_id == i.id)).all()]} for i in ideas]


@router.post("/groups/{hid}/verify", dependencies=[Depends(require_admin)])
def verify_group(hid: int, db=DbDep):
    group(db, hid)
    rows = db.scalars(select(LiveIntent).join(LiveIdea).where(LiveIdea.huddle_id == hid, LiveIntent.status == "prepared").limit(20)).all()
    return [reconcile(db, row) for row in rows]
