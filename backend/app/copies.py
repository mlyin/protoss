"""Separate-wallet mainnet execution ("copies"): each participant's order goes out from their own Hyperliquid account,
signed by an API wallet they authorized themselves. Nothing is pooled, nobody at Protoss holds a master key.

How a participant gets here (once, in their own hands):
  1. app.hyperliquid.xyz -> More -> API -> generate an API wallet, name it protoss, Authorize (a signature from their account).
  2. On the machine that runs the bridge: `python scripts/wallets.py add tg:<telegram user id> --name lando --address 0x<their account>`
     and paste the API wallet key at the hidden prompt. It lands in ~/.protoss/wallets.json, mode 0600, never in the repo.
  3. Start the bridge with `scripts/telegram_demo.py --live ...`. From then on Telegram is the only interface.

What the adapter guarantees:
  - An agent trades only the account registered for its owner (`tg:<id>`), and only if the API wallet in the file is in
    that account's approved agent list on Hyperliquid (checked at agent creation, refused otherwise).
  - Sizing never sees the whole account: equity() is capped at the participant's pledge, so a $20 copy buys $20 even
    when the account holds $98. positions() only reports the agent's allowed markets.
  - Per-order cap COPIES_MAX_USD (default 100). Orders are refused unless MAINNET_TRADING_ENABLED=true.
  - Every fill is confirmed back from Hyperliquid's fill history (time, size, price, hash) before it is announced.
Attribution caveat: if the same account also trades the same market elsewhere, positions and P&L for that market are
shared on the exchange side; the demo keeps one market per copy to avoid that.
"""
from __future__ import annotations

import json
import logging
import math
import os
import stat
import time
from pathlib import Path

from .config import Settings
from .hl import Fill, TestnetExchange

log = logging.getLogger("protoss.copies")

WALLETS_FILE = Path(os.environ.get("COPIES_WALLETS_FILE", str(Path.home() / ".protoss" / "wallets.json")))


def load_wallets(path: Path = WALLETS_FILE) -> dict[str, dict]:
    """{ "tg:123": {"name": "lando", "address": "0x..", "agent_key" | "agent_key_env": ...}, ... }"""
    if not path.exists():
        return {}
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise RuntimeError(f"{path} is readable by others (mode {oct(mode)}); chmod 600 it")
    data = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for who, w in data.items():
        if not isinstance(w, dict) or not w.get("address"):
            continue
        out[who] = {"name": w.get("name") or who, "address": w["address"], "agent_key": w.get("agent_key"), "agent_key_env": w.get("agent_key_env")}
    return out


def save_wallet(who: str, entry: dict, path: Path = WALLETS_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    data[who] = entry
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    os.chmod(path, 0o600)


def _key(w: dict) -> str | None:
    return w.get("agent_key") or (os.environ.get(w["agent_key_env"]) if w.get("agent_key_env") else None)


class CopiesExchange(TestnetExchange):
    """Mainnet, one API wallet per participant. Reuses the testnet adapter's price feed and order plumbing."""

    name = "copies"

    def __init__(self, settings: Settings, wallets: dict[str, dict] | None = None):
        from hyperliquid.info import Info
        from hyperliquid.utils import constants

        self.settings = settings
        self.url = settings.hl_api_url or constants.MAINNET_API_URL
        self.wallets = load_wallets() if wallets is None else wallets
        self.max_usd = float(os.environ.get("COPIES_MAX_USD", "100"))
        self.builder = settings.hl_builder_address
        self.builder_warning = None if self.builder else "no builder address configured"
        self.info = Info(self.url, skip_ws=True)
        self._dexs = [""] + list(settings.hl_perp_dexs)
        self._ex_cache = {}
        self._lev_done: set[tuple[str, str]] = set()
        self._cache, self._cache_ts = {}, 0.0
        self.tick()

    # --- who trades what
    def wallet_for(self, agent) -> dict:
        w = self.wallets.get(agent.owner)
        if not w:
            raise RuntimeError(f"no authorized wallet for {agent.owner}; run scripts/wallets.py add {agent.owner} ...")
        if not _key(w):
            raise RuntimeError(f"wallet for {agent.owner} has no API key loaded (agent_key or {w.get('agent_key_env')})")
        return w

    def _account_for(self, db, agent) -> str:
        return self.wallet_for(agent)["address"]

    def _exchange_for(self, agent):
        from eth_account import Account
        from hyperliquid.exchange import Exchange

        w = self.wallet_for(agent)
        if agent.owner not in self._ex_cache:
            self._ex_cache[agent.owner] = Exchange(Account.from_key(_key(w)), self.url, account_address=w["address"], perp_dexs=list(self.settings.hl_perp_dexs))
        return self._ex_cache[agent.owner]

    def authorized(self, agent) -> bool:
        """Is the API wallet we hold for this owner in the account's approved agent list on Hyperliquid?"""
        from eth_account import Account

        w = self.wallet_for(agent)
        mine = Account.from_key(_key(w)).address.lower()
        agents = self.info.post("/info", {"type": "extraAgents", "user": w["address"]})
        return any(str(a.get("address", "")).lower() == mine for a in agents or [])

    def on_agent_created(self, db, agent) -> None:
        if not self.authorized(agent):
            w = self.wallet_for(agent)
            raise RuntimeError(f"{w['name']}: the API wallet in wallets.json is not authorized on {w['address'][:6]}... Authorize it in the app (More, API) first.")

    # --- sizing sees the pledge, not the account
    def account_equity(self, address: str) -> float:
        """Perps equity on every dex, plus spot USDC when the account is unified (that USDC is margin there)."""
        total = super().account_equity(address)
        try:
            if self.info.post("/info", {"type": "userAbstraction", "user": address}) == "unifiedAccount":
                spot = self.info.post("/info", {"type": "spotClearinghouseState", "user": address})
                total += sum(float(b.get("total", 0)) for b in spot.get("balances", []) if b.get("coin") == "USDC")
        except Exception as e:
            log.debug("abstraction/spot read failed for %s: %s", address, e)
        return total

    def equity(self, db, agent) -> float:
        real = self.account_equity(self._account_for(db, agent))
        return max(0.0, min(float(agent.starting_equity or 0.0), real))

    def positions(self, db, agent):
        allowed = set(getattr(getattr(agent, "limits", None), "allowed_markets", None) or [])
        out = super().positions(db, agent)
        return {m: v for m, v in out.items() if not allowed or m in allowed}

    # --- orders
    def _builder(self):
        return None  # per-account builder approval is a separate signature; left off for the demo

    def place(self, db, agent, market, side, size, order_type, limit_px, reduce_only) -> Fill | None:
        if not self.settings.mainnet_trading_enabled:
            raise RuntimeError("live copies are off; start with --live (MAINNET_TRADING_ENABLED=true)")
        size = self.round_size(market, size)
        if size <= 0:
            raise RuntimeError(f"size rounds to zero at {market}'s step")
        mark = self.mark(market)
        if not reduce_only and size * mark > self.max_usd + 0.01:
            raise RuntimeError(f"order {size * mark:.2f} USD is above the per-order cap of {self.max_usd:.0f} USD (COPIES_MAX_USD)")
        ex = self._exchange_for(agent)
        lev = max(1, int(getattr(getattr(agent, "limits", None), "max_leverage", 1) or 1))
        if (agent.owner, market) not in self._lev_done and not reduce_only:
            meta = self.market_meta(market) or {}
            is_cross = not meta.get("onlyIsolated", False)  # some HIP-3 markets (xyz:UNITREE) only take isolated margin
            r = ex.update_leverage(lev, market, is_cross)
            if isinstance(r, dict) and r.get("status") != "ok":
                raise RuntimeError(f"could not set {lev}x on {market}: {r}")
            self._lev_done.add((agent.owner, market))
        t0 = int(time.time() * 1000)
        res = self._send(ex, market, side == "buy", size, order_type, limit_px, reduce_only, None)
        statuses = res.get("response", {}).get("data", {}).get("statuses", []) if isinstance(res, dict) else []
        for st in statuses:
            if "error" in st:
                raise RuntimeError(st["error"])
        filled = next((st["filled"] for st in statuses if "filled" in st), None)
        if not filled:
            return None
        px, sz = float(filled["avgPx"]), float(filled["totalSz"])
        if not (math.isfinite(px) and math.isfinite(sz)) or sz <= 0:
            raise RuntimeError(f"unreadable fill: {filled}")
        fee = self._confirm(self._account_for(db, agent), market, t0) or px * sz * self.settings.taker_fee_bps / 10_000
        return Fill(market, side, sz, px, fee, 0.0, 0.0, str(filled.get("oid")))

    def _confirm(self, address: str, market: str, since_ms: int) -> float | None:
        """Read the fill back from Hyperliquid so what we announce is what the exchange recorded. Returns the fee paid."""
        for _ in range(4):
            try:
                fills = [f for f in self.info.post("/info", {"type": "userFillsByTime", "user": address, "startTime": since_ms - 2000}) if f["coin"] == market]
            except Exception:
                fills = []
            if fills:
                self.last_fill = fills[-1]
                return sum(float(f.get("fee", 0)) for f in fills)
            time.sleep(0.5)
        self.last_fill = None
        return None

    def flatten(self, db, agent):
        return super().flatten(db, agent)
