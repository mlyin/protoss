"""Credentials.

Each agent has two keys, issued once at creation and stored hashed:
  ar_owner_<...>  the human owner: can set limits, flatten, read everything
  ar_live_<...>   the agent runtime: can read and trade, cannot touch limits or withdraw

The Hyperliquid signing key never leaves the backend.
"""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import Agent

OWNER_PREFIX = "ar_owner_"
AGENT_PREFIX = "ar_live_"


def new_key(prefix: str) -> str:
    return prefix + secrets.token_urlsafe(24)


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


@dataclass
class Principal:
    agent: Agent
    role: str  # owner | agent

    @property
    def is_owner(self) -> bool:
        return self.role == "owner"


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    return authorization.split(" ", 1)[1].strip()


def current_principal(
    authorization: str | None = Header(default=None), db: Session = Depends(get_db)
) -> Principal:
    key = _bearer(authorization)
    h = hash_key(key)
    if key.startswith(OWNER_PREFIX):
        agent = db.scalar(select(Agent).where(Agent.owner_key_hash == h))
        role = "owner"
    elif key.startswith(AGENT_PREFIX):
        agent = db.scalar(select(Agent).where(Agent.agent_key_hash == h))
        role = "agent"
    else:
        agent, role = None, ""
    if agent is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid api key")
    return Principal(agent=agent, role=role)


def require_owner(p: Principal = Depends(current_principal)) -> Principal:
    if not p.is_owner:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "owner key required: agents cannot change their own limits")
    return p


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    if not x_admin_token or not secrets.compare_digest(x_admin_token, get_settings().admin_token):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin token required")
