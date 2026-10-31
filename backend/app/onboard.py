"""Join with a card: fiat in, a stake in a legion out, with no trip through the Hyperliquid UI.

The flow is non-custodial end to end. Protoss never holds funds or keys.

 1. The browser creates a wallet the user controls (Privy embedded wallet, keyed to an email login).
    The private key lives on the user's device and in Privy's enclave shares, not with us.
 2. The user pays with card, Apple Pay or bank through an onramp partner. The partner delivers USDC to the
    user's own wallet address: straight onto HyperCore where the partner supports it (MoonPay Gateway lists
    USDC on HyperCore since May 2026), otherwise on Arbitrum, where the Hyperliquid bridge credits the
    depositing address.
 3. The browser signs `vaultTransfer` from the user's wallet into the legion's Hyperliquid vault. Leaving is
    the same action in reverse, signed by the user, any time the vault lock-up allows.

This module is the server side of that: which partners are configured, the hosted checkout URL for a
session, a record of the session so the UI can resume and poll, and a refusal for regions we do not
serve. It writes nothing to Hyperliquid and never sees a key.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import logging
import secrets
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, Float, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .config import Settings, get_settings
from .db import Base, DbDep
from .hl import ExchangeAdapter, get_exchange
from .models import Org, _now

log = logging.getLogger("protoss.onboard")
router = APIRouter()

SESSION_TTL = dt.timedelta(hours=2)
ADDRESS = r"^0x[0-9a-fA-F]{40}$"


def exchange() -> ExchangeAdapter:
    return get_exchange()


# ------------------------------------------------------------------------------------------------ model


class OnboardSession(Base):
    """One attempt to fund a wallet and stake it in a legion. Status moves created → redirected → funded → staked."""

    __tablename__ = "onboard_sessions"

    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    legion_slug: Mapped[str | None] = mapped_column(String(48), nullable=True)
    provider: Mapped[str] = mapped_column(String(16))
    amount_usd: Mapped[float] = mapped_column(Float)
    wallet: Mapped[str] = mapped_column(String(42))
    destination_kind: Mapped[str] = mapped_column(String(8))  # vault | wallet
    destination: Mapped[str] = mapped_column(String(42))
    region: Mapped[str | None] = mapped_column(String(2), nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="created")
    funded_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))


# ------------------------------------------------------------------------------------------------ providers


def providers(s: Settings) -> list[dict]:
    """Partners the UI may offer. `manual` is always there: the user sends USDC on Arbitrum themselves."""
    out = []
    if s.onramp_moonpay_key:
        out.append({
            "id": "moonpay", "name": "MoonPay", "rails": ["card", "apple_pay", "google_pay", "bank"],
            "regions": ["EU", "UK", "BR", "SG", "AU", "CA"], "min_usd": max(s.onboard_min_usd, 20.0),
            "fee_note": "MoonPay charges its own fee, shown before you pay. Protoss adds nothing on the way in.",
            "delivers": "hypercore" if s.onramp_moonpay_currency.endswith("hypercore") else "arbitrum",
        })
    if s.onramp_coinbase_app_id:
        out.append({
            "id": "coinbase", "name": "Coinbase Onramp", "rails": ["card", "bank", "coinbase_balance"],
            "regions": ["EU", "UK", "CA", "AU", "SG"], "min_usd": max(s.onboard_min_usd, 2.0),
            "fee_note": "Coinbase fees apply, shown before you pay. Delivered as USDC on Arbitrum.",
            "delivers": "arbitrum",
        })
    out.append({
        "id": "manual", "name": "Send USDC yourself", "rails": ["usdc_arbitrum"],
        "regions": ["*"], "min_usd": 5.0,
        "fee_note": "Only the Arbitrum gas you pay to send. The Hyperliquid bridge takes nothing.",
        "delivers": "arbitrum",
    })
    return out


def moonpay_url(s: Settings, *, wallet: str, amount_usd: float, session_id: str) -> str:
    """Hosted checkout. URLs that pin a wallet address must be signed with the secret (HMAC-SHA256 of the query)."""
    q = {
        "apiKey": s.onramp_moonpay_key,
        "currencyCode": s.onramp_moonpay_currency,
        "walletAddress": wallet,
        "baseCurrencyCode": "usd",
        "baseCurrencyAmount": f"{amount_usd:.2f}",
        "externalTransactionId": session_id,
        "redirectURL": f"{s.public_url}/#/join?session={session_id}",
    }
    url = "https://buy.moonpay.com?" + urlencode(q, quote_via=quote)
    if s.onramp_moonpay_secret:
        query = url[url.index("?"):]
        sig = base64.b64encode(hmac.new(s.onramp_moonpay_secret.encode(), query.encode(), hashlib.sha256).digest()).decode()
        url += "&signature=" + quote(sig, safe="")
    return url


def coinbase_url(s: Settings, *, wallet: str, amount_usd: float, session_id: str) -> str:
    """Coinbase Onramp. Since 2025 a production URL also needs a short-lived `sessionToken` minted server-side with
    the CDP secret; until that key is configured this URL is a preview and the UI says so."""
    q = {
        "appId": s.onramp_coinbase_app_id,
        "addresses": json.dumps({wallet: ["arbitrum"]}),
        "assets": json.dumps(["USDC"]),
        "presetFiatAmount": f"{amount_usd:.0f}",
        "fiatCurrency": "USD",
        "partnerUserId": session_id,
        "redirectUrl": f"{s.public_url}/#/join?session={session_id}",
    }
    return "https://pay.coinbase.com/buy/select-asset?" + urlencode(q, quote_via=quote)


def steps_for(provider: str, *, destination_kind: str, legion_name: str | None, delivers: str) -> list[str]:
    stake = f"Back in Protoss, sign one message to move the USDC into {legion_name}." if destination_kind == "vault" else \
        "Back in Protoss, pick a legion and sign one message to stake."
    if provider == "manual":
        return [
            "Send USDC on Arbitrum to your wallet address below. 5 USDC minimum.",
            "Hyperliquid credits the same address within a minute; the bridge takes no fee.",
            stake,
            "Leave any time: the reverse of that message, signed by you. Protoss cannot stop it.",
        ]
    arrive = "It lands on your Hyperliquid account directly." if delivers == "hypercore" else \
        "It arrives as USDC on Arbitrum; Hyperliquid credits your address within a minute."
    return [
        "Pay with card, Apple Pay or bank. The partner shows its fee before you confirm.",
        arrive,
        stake,
        "Leave any time: the reverse of that message, signed by you. Protoss cannot stop it.",
    ]


# ------------------------------------------------------------------------------------------------ schemas


class SessionIn(BaseModel):
    legion: str | None = Field(default=None, max_length=48)
    amount_usd: float = Field(gt=0, le=1_000_000)
    provider: str = Field(pattern=r"^[a-z_]{2,16}$")
    wallet: str | None = Field(default=None, pattern=ADDRESS)
    email: str | None = Field(default=None, max_length=120)  # not stored in v0; Privy owns the login
    region: str | None = Field(default=None, min_length=2, max_length=2)


# ------------------------------------------------------------------------------------------------ helpers


def _region(header: str | None, body: str | None) -> str | None:
    r = (header or body or "").strip().upper()
    return r if len(r) == 2 and r != "XX" else None


def _blocked(s: Settings, region: str | None) -> str | None:
    if region and region in {x.upper() for x in s.onboard_blocked_regions}:
        return f"Protoss does not offer perps in {region} yet. You can still follow legions and run the Lab."
    return None


def _destination(db: Session, slug: str | None) -> tuple[str, str | None, str | None]:
    """(kind, address, legion name). A legion with a Hyperliquid vault is the destination; otherwise the user's wallet."""
    if not slug:
        return "wallet", None, None
    org = db.scalar(select(Org).where(Org.slug == slug))
    if not org:
        raise HTTPException(404, "legion not found")
    if org.hl_vault:
        return "vault", org.hl_vault, org.name
    return "wallet", None, org.name


def _aware(t: dt.datetime) -> dt.datetime:
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)  # SQLite hands back naive timestamps


def _public(sess: OnboardSession) -> dict:
    return {
        "session_id": sess.id, "status": sess.status, "provider": sess.provider, "legion": sess.legion_slug,
        "amount_usd": sess.amount_usd, "funded_usd": round(sess.funded_usd, 2), "wallet": sess.wallet,
        "destination": {"kind": sess.destination_kind, "address": sess.destination},
        "expires_at": _aware(sess.expires_at).isoformat(),
    }


# ------------------------------------------------------------------------------------------------ routes


@router.get("/onboard/options")
def options(legion: str | None = Query(default=None), cf_ipcountry: str | None = Header(default=None), db: Session = DbDep):
    s = get_settings()
    region = _region(cf_ipcountry, None)
    kind, address, name = _destination(db, legion)
    return {
        "providers": providers(s),
        "wallet_provider": {"id": "privy", "app_id": s.privy_app_id},
        "chain": "arbitrum", "asset": "USDC", "min_usd": s.onboard_min_usd,
        "destination": {"kind": kind, "address": address, "legion": name},
        "region": region, "blocked": _blocked(s, region),
        "notice": "Your money sits in a wallet only you control, then in a Hyperliquid vault you can leave at will. Protoss holds neither.",
        "us_notice": "Perps are not offered to US persons. Protoss checks your region at checkout.",
    }


@router.post("/onboard/session")
def create_session(body: SessionIn, cf_ipcountry: str | None = Header(default=None), db: Session = DbDep):
    s = get_settings()
    region = _region(cf_ipcountry, body.region)
    kind, address, name = _destination(db, body.legion)
    blocked = _blocked(s, region)
    if blocked:
        return {"status": "unavailable", "reason": blocked, "steps": ["Follow legions and use the Lab for free.", "We will post when your region opens."]}
    if body.amount_usd < s.onboard_min_usd:
        raise HTTPException(422, f"minimum is {s.onboard_min_usd:.0f} USD")
    prov = next((p for p in providers(s) if p["id"] == body.provider), None)
    if not prov:
        raise HTTPException(422, "provider not offered")
    if not body.wallet:
        return {"status": "needs_wallet", "reason": "A wallet address is where the USDC lands. Sign in to create one, or paste yours.", "steps": []}

    sid = secrets.token_hex(12)
    sess = OnboardSession(
        id=sid, legion_slug=body.legion, provider=body.provider, amount_usd=body.amount_usd, wallet=body.wallet,
        destination_kind=kind, destination=address or body.wallet, region=region, status="created",
        expires_at=_now() + SESSION_TTL,
    )
    url = None
    if body.provider == "moonpay":
        url = moonpay_url(s, wallet=body.wallet, amount_usd=body.amount_usd, session_id=sid)
    elif body.provider == "coinbase":
        url = coinbase_url(s, wallet=body.wallet, amount_usd=body.amount_usd, session_id=sid)
    if url:
        sess.status = "redirected"
    db.add(sess)
    db.flush()
    log.info("onboard session %s %s %.2f via %s -> %s:%s", sid, body.legion, body.amount_usd, body.provider, kind, sess.destination)
    return {
        **_public(sess),
        "status": "ok", "session_status": sess.status, "url": url,
        "steps": steps_for(body.provider, destination_kind=kind, legion_name=name, delivers=prov["delivers"]),
    }


@router.get("/onboard/session/{session_id}")
def session_status(session_id: str, db: Session = DbDep, ex: ExchangeAdapter = Depends(exchange)):
    """Poll. On a live exchange we read the wallet's Hyperliquid equity and flip to `funded` when it covers 90% of
    the amount (partner fees eat the rest). `staked` is set by the UI after the vaultTransfer signature lands."""
    sess = db.get(OnboardSession, session_id)
    if not sess:
        raise HTTPException(404, "session not found")
    s = get_settings()
    if sess.status in {"created", "redirected"}:
        if _aware(sess.expires_at) < _now():
            sess.status = "expired"
        elif s.arena_mode == "sim":
            # No real rails in sim. Funds "arrive" 20 s after the session opens so the demo shows every state.
            if (_now() - _aware(sess.created_at)).total_seconds() >= 20:
                sess.funded_usd, sess.status = sess.amount_usd, "funded"
        elif hasattr(ex, "account_equity"):
            try:
                eq = float(ex.account_equity(sess.wallet) or 0.0)
            except Exception as e:  # network blip; keep polling
                log.debug("equity read failed for %s: %s", sess.wallet, e)
                eq = sess.funded_usd
            sess.funded_usd = eq
            if eq >= 0.9 * sess.amount_usd:
                sess.status = "funded"
    return _public(sess)


class StakedIn(BaseModel):
    tx: str | None = Field(default=None, max_length=200)  # the vaultTransfer response hash or nonce, for the record


@router.post("/onboard/session/{session_id}/staked")
def mark_staked(session_id: str, body: StakedIn, db: Session = DbDep):
    """The browser calls this after the user's wallet signed `vaultTransfer`. Informational: the vault's follower
    list on Hyperliquid is the source of truth, and the legion page reads it live."""
    sess = db.get(OnboardSession, session_id)
    if not sess:
        raise HTTPException(404, "session not found")
    if sess.status == "expired":
        raise HTTPException(409, "session expired")
    sess.status = "staked"
    return _public(sess)
