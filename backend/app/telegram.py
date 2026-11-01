"""Private Telegram wallet ownership links. Chat approval is never spending authority."""
from __future__ import annotations

import datetime as dt
import hashlib
import secrets

from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from .auth import require_admin
from .config import get_settings
from .db import Base, DbDep
from .huddle import Huddle

router = APIRouter(prefix="/telegram", tags=["telegram"])
UTC = dt.timezone.utc


class WalletConnection(Base):
    __tablename__ = "telegram_wallet_connections"
    __table_args__ = (UniqueConstraint("huddle_id", "telegram_user_id"), UniqueConstraint("huddle_id", "wallet"))

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    huddle_id: Mapped[int] = mapped_column(ForeignKey("huddles.id"))
    telegram_user_id: Mapped[str] = mapped_column(String(24))
    display_name: Mapped[str] = mapped_column(String(80))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    challenge: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    wallet: Mapped[str | None] = mapped_column(String(42), nullable=True)


class LinkIn(BaseModel):
    huddle_id: int
    telegram_user_id: str = Field(pattern=r"^[1-9][0-9]{0,19}$")
    display_name: str = Field(min_length=1, max_length=80)


class VerifyIn(BaseModel):
    wallet: str = Field(pattern=r"^0x[0-9a-fA-F]{40}$")
    signature: str = Field(pattern=r"^0x[0-9a-fA-F]{130}$")


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def lookup(db, token):
    row = db.scalar(select(WalletConnection).where(WalletConnection.token_hash == digest(token)))
    if not row:
        raise HTTPException(404, "connection link not found")
    expires = row.expires_at.replace(tzinfo=UTC) if row.expires_at.tzinfo is None else row.expires_at
    if dt.datetime.now(UTC) >= expires:
        raise HTTPException(410, "connection link expired; request /join again in Telegram")
    return row


def bearer(header):
    if not header or not header.startswith("Bearer "):
        raise HTTPException(401, "private connection link required")
    return header[7:]


@router.post("/links", dependencies=[Depends(require_admin)], status_code=201)
def create_link(body: LinkIn, db: Session = DbDep):
    huddle = db.get(Huddle, body.huddle_id)
    if not huddle or not huddle.chat_id.startswith("telegram:"):
        raise HTTPException(404, "Telegram group not found")
    token = secrets.token_urlsafe(32)
    expires = dt.datetime.now(UTC) + dt.timedelta(minutes=15)
    row = db.scalar(select(WalletConnection).where(WalletConnection.huddle_id == huddle.id,
                                                 WalletConnection.telegram_user_id == body.telegram_user_id))
    if row is None:
        row = WalletConnection(huddle_id=huddle.id, telegram_user_id=body.telegram_user_id)
        db.add(row)
    row.display_name, row.token_hash, row.expires_at = body.display_name, digest(token), expires
    row.challenge = (f"Connect wallet to Protoss\nOrigin: {get_settings().app_url}\n"
                     f"Telegram user: {body.telegram_user_id}\nGroup: {huddle.id}\n"
                     f"Nonce: {secrets.token_hex(24)}\nExpires: {expires.isoformat()}\n"
                     "This signature proves wallet ownership only. It does not authorize a deposit or trade.")
    return {"url": get_settings().app_url.rstrip("/") + "/#/telegram/connect?token=" + token,
            "expires_at": expires.isoformat()}


@router.get("/connect")
def connection(response: Response, authorization: str | None = Header(default=None), db: Session = DbDep):
    response.headers["Cache-Control"] = "no-store"
    row = lookup(db, bearer(authorization))
    huddle = db.get(Huddle, row.huddle_id)
    mode = get_settings().arena_mode
    # Telegram copies are independent accounts. Never send them into a shared vault.
    vault_url = None
    return {"display_name": row.display_name, "telegram_user_id": row.telegram_user_id,
            "group": huddle.title, "challenge": row.challenge, "wallet": row.wallet,
            "expires_at": row.expires_at, "mode": mode, "vault_url": vault_url,
            "deposit_verified": False}


@router.post("/connect")
def verify_connection(body: VerifyIn, authorization: str | None = Header(default=None), db: Session = DbDep):
    row = lookup(db, bearer(authorization))
    try:
        recovered = Account.recover_message(encode_defunct(text=row.challenge), signature=body.signature)
    except (ValueError, TypeError, OverflowError) as exc:
        raise HTTPException(422, "invalid wallet signature") from exc
    wallet = body.wallet.lower()
    if recovered.lower() != wallet:
        raise HTTPException(422, "signature does not match this wallet")
    if row.wallet and row.wallet != wallet:
        raise HTTPException(409, "this Telegram account already connected a different wallet")
    other = db.scalar(select(WalletConnection).where(WalletConnection.huddle_id == row.huddle_id,
                                                    WalletConnection.wallet == wallet, WalletConnection.id != row.id))
    if other:
        raise HTTPException(409, "this wallet is already connected to the other participant")
    row.wallet = wallet
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "wallet connection conflicts with an existing participant") from exc
    return {"wallet": row.wallet, "ownership_verified": True, "deposit_verified": False}


@router.get("/huddles/{hid}/connections", dependencies=[Depends(require_admin)])
def connections(hid: int, db: Session = DbDep):
    rows = db.scalars(select(WalletConnection).where(WalletConnection.huddle_id == hid, WalletConnection.wallet.is_not(None))).all()
    return [{"telegram_user_id": r.telegram_user_id, "display_name": r.display_name, "wallet": r.wallet,
             "ownership_verified": True, "deposit_verified": False} for r in rows]
