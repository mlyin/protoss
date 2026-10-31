"""Exchange adapters.

All three implement the same small interface so the router, ledger and worker do not care which
one is live:

  SimExchange      synthetic prices (random walk from seed prices), simulated fills. No network.
  PaperExchange    real Hyperliquid mark prices from the Info API, simulated fills in our ledger.
  TestnetExchange  real orders on Hyperliquid testnet. One master wallet (the only key that exists)
                   owns one sub-account per agent; orders are signed by the master with the
                   sub-account as vaultAddress and carry the builder code.

Positions, cash and equity for sim/paper live in our DB (Position rows + Agent.cash). For testnet the
exchange is the source of truth and we read it back through Info.user_state.
"""
from __future__ import annotations

import logging
import math
import random
import threading
import time
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .models import Agent, Position

log = logging.getLogger("coliseum.hl")


@dataclass
class Fill:
    market: str
    side: str
    size: float
    px: float
    exchange_fee_usd: float
    builder_fee_usd: float
    realized_pnl_usd: float
    exchange_ref: str | None = None


class ExchangeAdapter(Protocol):
    name: str

    def markets(self) -> list[str]: ...
    def mark(self, market: str) -> float: ...
    def marks(self) -> dict[str, float]: ...
    def tick(self) -> None: ...
    def on_agent_created(self, db: Session, agent: Agent) -> None: ...
    def place(self, db: Session, agent: Agent, market: str, side: str, size: float, order_type: str, limit_px: float | None, reduce_only: bool) -> Fill | None: ...
    def flatten(self, db: Session, agent: Agent) -> list[Fill]: ...
    def positions(self, db: Session, agent: Agent) -> dict[str, tuple[float, float]]: ...
    def equity(self, db: Session, agent: Agent) -> float: ...


# ----------------------------------------------------------------------------- ledger helpers (sim/paper)

def _apply_fill_to_ledger(db: Session, agent: Agent, market: str, side: str, size: float, px: float, settings: Settings) -> Fill:
    """Update Position + Agent.cash for a simulated fill and return the Fill with fees and realized P&L."""
    signed = size if side == "buy" else -size
    pos = db.get(Position, (agent.id, market))
    current = pos.size if pos else 0.0
    entry = pos.entry_px if pos else 0.0

    realized = 0.0
    after = current + signed
    if current != 0 and (signed > 0) != (current > 0):
        closing = min(abs(signed), abs(current))
        realized = closing * (px - entry) * (1 if current > 0 else -1)
    if after == 0:
        new_entry = 0.0
    elif current == 0 or (signed > 0) == (current > 0):
        new_entry = (abs(current) * entry + abs(signed) * px) / abs(after)  # adding: weighted entry
    elif abs(signed) > abs(current):
        new_entry = px  # flipped: new position at fill price
    else:
        new_entry = entry  # reduced: entry unchanged

    notional = size * px
    exchange_fee = notional * settings.taker_fee_bps / 10_000
    builder_fee = notional * settings.hl_builder_fee_tenths_bp / 1_000_000  # tenths of a bp
    agent.cash += realized - exchange_fee - builder_fee

    if pos is None:
        pos = Position(agent_id=agent.id, market=market, size=after, entry_px=new_entry)
        db.add(pos)
    else:
        pos.size, pos.entry_px = after, new_entry
    if after == 0:
        db.delete(pos)
    return Fill(market, side, size, px, exchange_fee, builder_fee, realized)


def _ledger_positions(db: Session, agent: Agent) -> dict[str, tuple[float, float]]:
    rows = db.scalars(select(Position).where(Position.agent_id == agent.id)).all()
    return {p.market: (p.size, p.entry_px) for p in rows if p.size != 0}


def _ledger_equity(db: Session, agent: Agent, marks: dict[str, float]) -> float:
    unreal = 0.0
    for m, (sz, entry) in _ledger_positions(db, agent).items():
        mark = marks.get(m)
        if mark:
            unreal += sz * (mark - entry)
    return agent.cash + unreal


class _LedgerExchange:
    """Shared behaviour for the two simulated-fill adapters."""

    name = "ledger"

    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = threading.Lock()

    def marks(self) -> dict[str, float]:  # pragma: no cover - overridden
        raise NotImplementedError

    def mark(self, market: str) -> float:
        px = self.marks().get(market)
        if px is None:
            raise KeyError(f"unknown market {market}")
        return px

    def markets(self) -> list[str]:
        return sorted(self.marks().keys())

    def on_agent_created(self, db: Session, agent: Agent) -> None:
        return None

    def _fill_px(self, market: str, side: str, order_type: str, limit_px: float | None) -> float | None:
        mark = self.mark(market)
        slip = mark * 0.0003  # 3 bp of simulated impact
        taker_px = mark + slip if side == "buy" else mark - slip
        if order_type == "market" or limit_px is None:
            return taker_px
        # a marketable limit fills at the better of the limit and the taker price; otherwise it rests (we drop it in v0)
        if side == "buy" and limit_px >= taker_px:
            return min(limit_px, taker_px)
        if side == "sell" and limit_px <= taker_px:
            return max(limit_px, taker_px)
        return None

    def place(self, db, agent, market, side, size, order_type, limit_px, reduce_only) -> Fill | None:
        with self._lock:
            px = self._fill_px(market, side, order_type, limit_px)
            if px is None:
                return None
            return _apply_fill_to_ledger(db, agent, market, side, size, px, self.settings)

    def flatten(self, db, agent) -> list[Fill]:
        fills = []
        for m, (sz, _) in list(_ledger_positions(db, agent).items()):
            side = "sell" if sz > 0 else "buy"
            f = self.place(db, agent, m, side, abs(sz), "market", None, True)
            if f:
                fills.append(f)
        return fills

    def positions(self, db, agent):
        return _ledger_positions(db, agent)

    def equity(self, db, agent) -> float:
        return _ledger_equity(db, agent, self.marks())


class SimExchange(_LedgerExchange):
    name = "sim"

    def __init__(self, settings: Settings, seed: int | None = None):
        super().__init__(settings)
        self._rng = random.Random(seed)
        self._prices = dict(settings.sim_markets)
        self._drift: dict[str, float] = {m: 0.0 for m in self._prices}

    def marks(self) -> dict[str, float]:
        return dict(self._prices)

    def tick(self) -> None:
        vol = self.settings.sim_vol_per_tick
        for m in self._prices:
            # mildly mean-reverting drift keeps the sim from trending forever
            self._drift[m] = 0.9 * self._drift[m] + self._rng.gauss(0, vol * 0.2)
            self._prices[m] *= math.exp(self._drift[m] + self._rng.gauss(0, vol))

    def shock(self, market: str, pct: float) -> None:
        """Test hook: move a price by pct (e.g. -0.12 for a 12% drop)."""
        self._prices[market] *= 1 + pct


class PaperExchange(_LedgerExchange):
    name = "paper"

    def __init__(self, settings: Settings):
        super().__init__(settings)
        from hyperliquid.info import Info
        from hyperliquid.utils import constants

        url = settings.hl_api_url or constants.MAINNET_API_URL
        self._info = Info(url, skip_ws=True)
        self._dexs = [""] + list(settings.hl_perp_dexs)
        self._cache: dict[str, float] = {}
        self._cache_ts = 0.0
        self.tick()

    def marks(self) -> dict[str, float]:
        if time.time() - self._cache_ts > 2.0:
            self.tick()
        return dict(self._cache)

    def tick(self) -> None:
        out: dict[str, float] = {}
        for dex in self._dexs:
            try:
                mids = self._info.all_mids(dex)
            except Exception:  # network hiccup: keep the last cache
                continue
            for coin, px in mids.items():
                if coin.startswith("@"):  # spot pairs by index; skip for v0
                    continue
                out[coin] = float(px)
        if out:
            self._cache, self._cache_ts = out, time.time()


class TestnetExchange:
    """Real orders on Hyperliquid testnet. Not exercised by the test-suite (needs network and funds)."""

    name = "testnet"

    def __init__(self, settings: Settings):
        from eth_account import Account
        from hyperliquid.exchange import Exchange
        from hyperliquid.info import Info
        from hyperliquid.utils import constants

        if not settings.hl_master_private_key:
            raise RuntimeError("ARENA_MODE=testnet needs HL_MASTER_PRIVATE_KEY (run `python -m app.keygen`)")
        self.settings = settings
        self.url = settings.hl_api_url or constants.TESTNET_API_URL
        self.master = Account.from_key(settings.hl_master_private_key)
        self.builder = settings.hl_builder_address or self.master.address
        self.info = Info(self.url, skip_ws=True)
        self._dexs = [""] + list(settings.hl_perp_dexs)
        self._exchange_cls = Exchange
        self._ex_cache: dict[str | None, Exchange] = {}
        self._cache: dict[str, float] = {}
        self._cache_ts = 0.0
        self.builder_warning: str | None = None
        self.tick()
        self.ensure_builder_approved()

    # --- prices
    def marks(self) -> dict[str, float]:
        if time.time() - self._cache_ts > 2.0:
            self.tick()
        return dict(self._cache)

    def mark(self, market: str) -> float:
        return self.marks()[market]

    def markets(self) -> list[str]:
        return sorted(self.marks().keys())

    def tick(self) -> None:
        out: dict[str, float] = {}
        for dex in self._dexs:
            try:
                for coin, px in self.info.all_mids(dex).items():
                    if not coin.startswith("@"):
                        out[coin] = float(px)
            except Exception:
                continue
        if out:
            self._cache, self._cache_ts = out, time.time()

    # --- accounts
    def _exchange(self, vault: str | None):
        if vault not in self._ex_cache:
            self._ex_cache[vault] = self._exchange_cls(
                self.master, self.url, vault_address=vault, perp_dexs=list(self.settings.hl_perp_dexs)
            )
        return self._ex_cache[vault]

    def on_agent_created(self, db: Session, agent: Agent) -> None:
        ex = self._exchange(None)
        res = ex.create_sub_account(f"arena-{agent.name}"[:32])
        sub = (res.get("response", {}).get("data") if isinstance(res, dict) else None) or res
        if not isinstance(sub, str):
            raise RuntimeError(f"create_sub_account failed: {res}")
        agent.hl_subaccount = sub
        ex.sub_account_transfer(sub, True, int(agent.starting_equity * 1_000_000))  # USDC has 6 decimals

    # --- builder code
    def approved_builder_fee(self, user: str | None = None) -> int | None:
        """Max fee (tenths of a bp) `user` has approved for our builder, or None if the query fails."""
        try:
            res = self.info.post("/info", {"type": "maxBuilderFee", "user": user or self.master.address, "builder": self.builder})
            return int(res)
        except Exception:
            return None

    def ensure_builder_approved(self) -> None:
        """The master wallet (which signs for every sub-account) approves our own builder fee once.
        Approval must come from a main wallet, which the master is. Never fatal: trading continues
        without the builder code and the UI shows a warning instead."""
        want = int(self.settings.hl_builder_fee_tenths_bp)
        have = self.approved_builder_fee()
        if have is not None and have >= want:
            return
        try:
            res = self._exchange(None).approve_builder_fee(self.builder, f"{want / 1000:.3f}%")
            if isinstance(res, dict) and res.get("status") != "ok":
                raise RuntimeError(str(res))
            self.builder_warning = None
        except Exception as e:  # e.g. builder below 100 USDC account value
            self.builder_warning = f"builder fee not approved for {self.builder}: {e}"
            log.warning(self.builder_warning)

    def _builder(self):
        return {"b": self.builder, "f": int(self.settings.hl_builder_fee_tenths_bp)} if not self.builder_warning else None

    def _send(self, ex, market, is_buy, size, order_type, limit_px, reduce_only, builder):
        if order_type == "market" or limit_px is None:
            if reduce_only:
                return ex.market_close(market, size, None, 0.01, builder=builder)
            return ex.market_open(market, is_buy, size, None, 0.01, builder=builder)
        return ex.order(market, is_buy, size, limit_px, {"limit": {"tif": "Ioc"}}, reduce_only, builder=builder)

    def place(self, db, agent, market, side, size, order_type, limit_px, reduce_only) -> Fill | None:
        ex = self._exchange(agent.hl_subaccount)
        is_buy = side == "buy"
        builder = self._builder()
        res = self._send(ex, market, is_buy, size, order_type, limit_px, reduce_only, builder)
        statuses = (res.get("response", {}).get("data", {}).get("statuses", []) if isinstance(res, dict) else [])
        errors = [st["error"] for st in statuses if "error" in st]
        if builder and errors and "builder" in " ".join(errors).lower():
            # the exchange rejected the builder code (not approved / not eligible): trade without it, flag it
            self.builder_warning = f"exchange rejected builder code: {errors[0]}"
            log.warning(self.builder_warning)
            res = self._send(ex, market, is_buy, size, order_type, limit_px, reduce_only, None)
            statuses = (res.get("response", {}).get("data", {}).get("statuses", []) if isinstance(res, dict) else [])
            builder = None
        for st in statuses:
            if "filled" in st:
                f = st["filled"]
                px, sz = float(f["avgPx"]), float(f["totalSz"])
                notional = px * sz
                bfee = notional * self.settings.hl_builder_fee_tenths_bp / 1_000_000 if builder else 0.0
                return Fill(market, side, sz, px, notional * self.settings.taker_fee_bps / 10_000, bfee, 0.0, str(f.get("oid")))
            if "error" in st:
                raise RuntimeError(st["error"])
        return None

    def flatten(self, db, agent) -> list[Fill]:
        fills = []
        for m, (sz, _) in self.positions(db, agent).items():
            f = self.place(db, agent, m, "sell" if sz > 0 else "buy", abs(sz), "market", None, True)
            if f:
                fills.append(f)
        return fills

    def positions(self, db, agent) -> dict[str, tuple[float, float]]:
        out: dict[str, tuple[float, float]] = {}
        for dex in self._dexs:
            try:
                state = self.info.user_state(agent.hl_subaccount, dex)
            except Exception:
                continue
            for ap in state.get("assetPositions", []):
                p = ap["position"]
                sz = float(p["szi"])
                if sz:
                    out[p["coin"]] = (sz, float(p.get("entryPx") or 0))
        return out

    def equity(self, db, agent) -> float:
        total = 0.0
        for dex in self._dexs:
            try:
                state = self.info.user_state(agent.hl_subaccount, dex)
                total += float(state["marginSummary"]["accountValue"])
            except Exception:
                continue
        return total


_adapter: ExchangeAdapter | None = None


def get_exchange() -> ExchangeAdapter:
    global _adapter
    if _adapter is None:
        s = get_settings()
        if s.arena_mode == "sim":
            _adapter = SimExchange(s)
        elif s.arena_mode == "paper":
            _adapter = PaperExchange(s)
        else:
            _adapter = TestnetExchange(s)
    return _adapter


def set_exchange_for_tests(adapter: ExchangeAdapter | None) -> None:
    global _adapter
    _adapter = adapter
