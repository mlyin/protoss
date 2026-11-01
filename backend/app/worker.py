"""Background loop: advance prices (sim), mark every agent, enforce the drawdown cap, snapshot equity."""
from __future__ import annotations

import asyncio
import logging
import time

from sqlalchemy import select

from .config import get_settings
from .db import session
from .hl import ExchangeAdapter, get_exchange
from .ledger import snapshot_equity
from .models import Agent
from .router import check_drawdown

log = logging.getLogger("arena.worker")


def run_once(ex: ExchangeAdapter, snapshot: bool) -> dict:
    """One tick. Returns a small summary (used by tests and the /admin/tick endpoint)."""
    ex.tick()
    halted, halted_orgs, snapped = [], [], 0
    with session() as db:
        from .models import Org
        from .orgs import check_org_drawdown
        from .router import flatten_and_halt

        for org in db.scalars(select(Org)).all():
            if check_org_drawdown(db, ex, org, flatten_and_halt):
                halted_orgs.append(org.slug)
        for agent in db.scalars(select(Agent)).all():
            if check_drawdown(db, ex, agent):
                halted.append(agent.name)
            if snapshot:
                snapshot_equity(db, ex, agent)
                snapped += 1
        from .huddle import tick as huddle_tick

        huddle_tick(db, ex)
    return {"halted": halted, "halted_orgs": halted_orgs, "snapshots": snapped}


async def loop() -> None:
    s = get_settings()
    ex = get_exchange()
    last_snapshot = 0.0
    while True:
        try:
            now = time.time()
            snap = now - last_snapshot >= s.snapshot_seconds
            out = run_once(ex, snap)
            if snap:
                last_snapshot = now
            if out["halted"]:
                log.warning("sandbox halted: %s", out["halted"])
        except Exception:  # keep the loop alive; a bad tick must not take the service down
            log.exception("worker tick failed")
        await asyncio.sleep(s.tick_seconds)
