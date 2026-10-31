"""Backtest engine and price sources for the Lab.

Vectorless on purpose: a few thousand hourly bars per request, plain Python loops, taker fee plus 3 bp of
slippage on every fill, mark-to-market on every bar close. Two price sources behind one Protocol:
Hyperliquid candles when the API is reachable, a seeded GBM otherwise (and always in sim mode) so tests
are reproducible offline.
"""
from __future__ import annotations

import csv
import datetime as dt
import math
import random
import time
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from .config import Settings
from .ledger import max_drawdown_pct, sharpe

UTC = dt.timezone.utc
BAR_SECONDS = {"1h": 3600, "4h": 4 * 3600, "1d": 86400}
SLIPPAGE_BPS = 3.0
SIM_NOTE = "simulated prices (seeded GBM) — Hyperliquid unreachable / sim mode"
HACKS_NOTE = "event dataset: illustrative, curated list — verify dates before relying on it"
HL_MAX_BARS = 5000
CURVE_POINTS = 400
HACKS_CSV = Path(__file__).resolve().parent / "data" / "hacks.csv"


class SourceUnavailable(Exception):
    """A live source could not be reached or returned something unusable."""


@dataclass(frozen=True)
class Candle:
    ts: dt.datetime
    o: float
    h: float
    l: float
    c: float
    v: float


class PriceSource(Protocol):
    name: str

    def has(self, market: str) -> bool: ...
    def markets(self) -> list[str]: ...
    def candles(self, market: str, bar: str, start: dt.datetime, end: dt.datetime) -> list[Candle]: ...


# ----------------------------------------------------------------------------------------------- sources

class HyperliquidCandles:
    name = "hyperliquid"

    def __init__(self, url: str, dexs: list[str], timeout: float = 10.0):
        from hyperliquid.info import Info

        try:
            self.info = Info(url, skip_ws=True, perp_dexs=[""] + list(dexs), timeout=timeout)
        except Exception as e:  # DNS failure, timeout, bad JSON: all mean "no live data"
            raise SourceUnavailable(str(e)) from e
        self._markets = sorted(n for n in self.info.name_to_coin if "/" not in n and not n.startswith("@"))

    def has(self, market: str) -> bool:
        return market in self._markets

    def markets(self) -> list[str]:
        return list(self._markets)

    def candles(self, market: str, bar: str, start: dt.datetime, end: dt.datetime) -> list[Candle]:
        step_ms = BAR_SECONDS[bar] * 1000
        start_ms, end_ms = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
        raw: dict[int, dict] = {}
        try:
            t = start_ms
            while t < end_ms:
                chunk_end = min(end_ms, t + HL_MAX_BARS * step_ms)
                for row in self.info.candles_snapshot(market, bar, t, chunk_end):
                    raw[int(row["t"])] = row
                t = chunk_end
        except Exception as e:
            raise SourceUnavailable(str(e)) from e
        out = [
            Candle(dt.datetime.fromtimestamp(t / 1000, UTC), float(r["o"]), float(r["h"]), float(r["l"]), float(r["c"]), float(r["v"]))
            for t, r in sorted(raw.items())
            if start_ms <= t < end_ms
        ]
        if not out:
            raise SourceUnavailable(f"no candles for {market}")
        return out

    def fills(self, address: str, start: dt.datetime, end: dt.datetime, cap: int = 20_000) -> list[dict]:
        """All perp fills of a wallet in the window, paginated by time (the API returns <= 2000 per call)."""
        out: list[dict] = []
        t, end_ms = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
        try:
            while len(out) < cap:
                batch = self.info.user_fills_by_time(address, t, end_ms)
                out += batch
                if len(batch) < 2000:
                    break
                t = int(batch[-1]["time"]) + 1
        except Exception as e:
            raise SourceUnavailable(str(e)) from e
        return [f for f in out if "/" not in f["coin"] and not f["coin"].startswith("@")]


class SimCandles:
    """Deterministic GBM per market: same (market, seed, window) always yields the same path."""

    name = "sim"
    EXTRA_MARKETS = {"XMR": 300.0, "DOGE": 0.2, "SOL": 190.0}
    HOURLY_VOL = 0.015

    def __init__(self, settings: Settings, seed: int = 7):
        self._prices = {**self.EXTRA_MARKETS, **settings.sim_markets}
        self._seed = seed

    def has(self, market: str) -> bool:
        return market in self._prices

    def markets(self) -> list[str]:
        return sorted(self._prices)

    def candles(self, market: str, bar: str, start: dt.datetime, end: dt.datetime) -> list[Candle]:
        step = BAR_SECONDS[bar]
        vol = self.HOURLY_VOL * math.sqrt(step / 3600)
        rng = random.Random(zlib.crc32(market.encode()) + self._seed)
        px = self._prices.get(market, 100.0)
        out, t = [], start
        while t < end:
            o = px
            px *= math.exp(rng.gauss(-0.5 * vol * vol, vol))
            wick = abs(rng.gauss(0, vol * 0.5))
            out.append(Candle(t, o, max(o, px) * (1 + wick), min(o, px) * (1 - wick), px, abs(rng.gauss(50, 20)) * 1000))
            t += dt.timedelta(seconds=step)
        return out


_source: PriceSource | None = None
_source_key: tuple | None = None
_candle_cache: dict[tuple, tuple[float, list[Candle]]] = {}


def get_source(settings: Settings) -> PriceSource:
    """SimCandles in sim mode; otherwise Hyperliquid, falling back to SimCandles when unreachable."""
    global _source, _source_key
    key = (settings.arena_mode, settings.hl_api_url, tuple(settings.hl_perp_dexs))
    if _source is not None and _source_key == key:
        return _source
    if settings.arena_mode == "sim":
        _source = SimCandles(settings)
    else:
        from hyperliquid.utils import constants

        url = settings.hl_api_url or (constants.TESTNET_API_URL if settings.arena_mode == "testnet" else constants.MAINNET_API_URL)
        try:
            _source = HyperliquidCandles(url, settings.hl_perp_dexs)
        except SourceUnavailable:
            _source = SimCandles(settings)
    _source_key = key
    return _source


def cached_candles(source: PriceSource, market: str, bar: str, start: dt.datetime, end: dt.datetime, ttl: float = 60.0) -> list[Candle]:
    key = (source.name, market, bar, start.isoformat(), end.isoformat())
    hit = _candle_cache.get(key)
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]
    candles = source.candles(market, bar, start, end)
    _candle_cache[key] = (time.monotonic(), candles)
    return candles


def data_note(source: PriceSource, bar: str) -> str:
    return f"Hyperliquid {bar} candles" if source.name == "hyperliquid" else SIM_NOTE


def load_hacks() -> list[dict]:
    with HACKS_CSV.open(newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r.get("date")]
    for r in rows:
        r["date"] = dt.date.fromisoformat(r["date"])
    return sorted(rows, key=lambda r: r["date"])


# ----------------------------------------------------------------------------------------------- ledger

@dataclass
class Fill:
    ts: dt.datetime
    market: str
    side: str
    px: float
    size: float
    reason: str
    realized: float = 0.0


@dataclass
class Book:
    """Perp-style ledger: cash moves only on realized P&L and fees; equity = cash + unrealized."""

    cash: float
    fee_bps: float
    positions: dict[str, tuple[float, float]] = field(default_factory=dict)  # market -> (signed size, entry)
    fills: list[Fill] = field(default_factory=list)

    def size(self, market: str) -> float:
        return self.positions.get(market, (0.0, 0.0))[0]

    def gross_notional(self, marks: dict[str, float]) -> float:
        return sum(abs(sz) * marks.get(m, entry) for m, (sz, entry) in self.positions.items())

    def equity(self, marks: dict[str, float]) -> float:
        return self.cash + sum(sz * (marks.get(m, entry) - entry) for m, (sz, entry) in self.positions.items())

    def fill(self, ts: dt.datetime, market: str, side: str, size: float, mark: float, reason: str, slip: bool = True) -> Fill | None:
        if size <= 0:
            return None
        px = mark * (1 + (SLIPPAGE_BPS / 10_000) * (1 if side == "buy" else -1)) if slip else mark
        signed = size if side == "buy" else -size
        current, entry = self.positions.get(market, (0.0, 0.0))
        realized = 0.0
        after = current + signed
        if current and (signed > 0) != (current > 0):
            realized = min(abs(signed), abs(current)) * (px - entry) * (1 if current > 0 else -1)
        if after == 0:
            new_entry = 0.0
        elif current == 0 or (signed > 0) == (current > 0):
            new_entry = (abs(current) * entry + abs(signed) * px) / abs(after)
        else:
            new_entry = px if abs(signed) > abs(current) else entry
        fee = size * px * self.fee_bps / 10_000
        self.cash += realized - fee
        if abs(after) < 1e-12:
            self.positions.pop(market, None)
        else:
            self.positions[market] = (after, new_entry)
        f = Fill(ts, market, side, px, size, reason, realized - fee if realized else 0.0)
        self.fills.append(f)
        return f

    def close(self, ts: dt.datetime, market: str, mark: float, reason: str) -> Fill | None:
        sz = self.size(market)
        return self.fill(ts, market, "sell" if sz > 0 else "buy", abs(sz), mark, reason) if sz else None


# ----------------------------------------------------------------------------------------------- strategies
# Each builder returns on_bar(i, candle) which places fills on the book; the engine marks after each bar.

Step = Callable[[int, Candle], None]


def _momentum(spec, candles: list[Candle], book: Book) -> Step:
    closes = [c.c for c in candles]

    def on_bar(i: int, c: Candle) -> None:
        if i + 1 < spec.slow:
            return
        fast = sum(closes[i + 1 - spec.fast : i + 1]) / spec.fast
        slow = sum(closes[i + 1 - spec.slow : i + 1]) / spec.slow
        pos = book.size(spec.market)
        target = book.equity({spec.market: c.c}) / c.c
        if fast > slow * 1.0005 and pos <= 0:
            book.close(c.ts, spec.market, c.c, "flip short -> long")
            book.fill(c.ts, spec.market, "buy", target, c.c, f"momentum: {spec.fast}-bar avg {fast:.2f} > {spec.slow}-bar {slow:.2f}")
        elif fast < slow * 0.9995 and pos >= 0:
            book.close(c.ts, spec.market, c.c, "flip long -> short")
            book.fill(c.ts, spec.market, "sell", target, c.c, f"momentum: {spec.fast}-bar avg {fast:.2f} < {spec.slow}-bar {slow:.2f}")

    return on_bar


def _meanrev(spec, candles: list[Candle], book: Book) -> Step:
    closes = [c.c for c in candles]
    n = spec.lookback

    def on_bar(i: int, c: Candle) -> None:
        if i + 1 < n:
            return
        win = closes[i + 1 - n : i + 1]
        mean = sum(win) / n
        sd = math.sqrt(sum((x - mean) ** 2 for x in win) / (n - 1)) or 1e-9
        z = (c.c - mean) / sd
        pos = book.size(spec.market)
        if pos == 0:
            size = book.equity({spec.market: c.c}) / c.c
            if z > spec.z:
                book.fill(c.ts, spec.market, "sell", size, c.c, f"fade: z={z:.2f} above {n}-bar mean")
            elif z < -spec.z:
                book.fill(c.ts, spec.market, "buy", size, c.c, f"fade: z={z:.2f} below {n}-bar mean")
        elif (pos > 0 and z >= 0) or (pos < 0 and z <= 0):
            book.close(c.ts, spec.market, c.c, "reverted to mean")
        elif abs(z) > 3.0:
            book.close(c.ts, spec.market, c.c, f"stop: z={z:.2f}")

    return on_bar


def _dca(spec, candles: list[Candle], book: Book) -> Step:
    period = dt.timedelta(days=spec.every_days)
    state = {"next": candles[0].ts if candles else None}

    def on_bar(i: int, c: Candle) -> None:
        if state["next"] is not None and c.ts >= state["next"]:
            book.fill(c.ts, spec.market, "buy", spec.amount / c.c, c.c, f"DCA ${spec.amount:,.0f}")
            state["next"] += period

    return on_bar


def _weekday(spec, candles: list[Candle], book: Book) -> Step:
    n = len(candles)

    def on_bar(i: int, c: Candle) -> None:
        wd = c.ts.weekday()
        first = i == 0 or candles[i - 1].ts.weekday() != wd
        last = i == n - 1 or candles[i + 1].ts.weekday() != wd
        if wd == spec.buy_weekday and first and book.size(spec.market) == 0:
            book.fill(c.ts, spec.market, "buy", book.equity({spec.market: c.c}) / c.c, c.c, f"{c.ts:%A} open")
        elif wd == spec.sell_weekday and last and book.size(spec.market) > 0:
            book.close(c.ts, spec.market, c.c, f"{c.ts:%A} close")

    return on_bar


def _buy_hold(spec, candles: list[Candle], book: Book) -> Step:
    def on_bar(i: int, c: Candle) -> None:
        if i == 0:
            book.fill(c.ts, spec.market, "buy", book.cash / c.c, c.c, "buy and hold")

    return on_bar


def _event_buy(spec, candles: list[Candle], book: Book, dates: list[dt.date]) -> Step:
    pending = sorted(dt.datetime.combine(d, dt.time(), UTC) for d in set(dates))
    lots: list[tuple[dt.datetime, float]] = []  # (exit ts, size)
    hold = dt.timedelta(days=spec.hold_days)
    open_side, close_side = ("buy", "sell") if spec.side == "long" else ("sell", "buy")

    def on_bar(i: int, c: Candle) -> None:
        marks = {spec.market: c.c}
        while lots and lots[0][0] <= c.ts:
            _, sz = lots.pop(0)
            book.fill(c.ts, spec.market, close_side, min(sz, abs(book.size(spec.market))), c.c, f"exit after {spec.hold_days}d hold")
        while pending and pending[0] <= c.ts:
            when = pending.pop(0)
            eq = book.equity(marks)
            notional = min(spec.size_pct * eq, max(0.0, eq - book.gross_notional(marks)))
            if notional > 0:
                book.fill(c.ts, spec.market, open_side, notional / c.c, c.c, f"event {when:%Y-%m-%d}: {spec.side}")
                lots.append((c.ts + hold, notional / c.c))
                lots.sort()

    return on_bar


def _replay(fills: list[dict], scale: float, book: Book, bar: str) -> Callable[[dt.datetime], None]:
    """Tail a wallet: apply its fills (scaled) during the bar they happened in, at the wallet's fill price."""
    step = dt.timedelta(seconds=BAR_SECONDS[bar])
    queue = sorted(fills, key=lambda f: int(f["time"]))

    def on_bar(ts: dt.datetime) -> None:
        while queue and dt.datetime.fromtimestamp(int(queue[0]["time"]) / 1000, UTC) < ts + step:
            f = queue.pop(0)
            book.fill(ts, f["coin"], "buy" if f["side"] == "B" else "sell", float(f["sz"]) * scale, float(f["px"]), f"wallet {f.get('dir', 'fill')}", slip=False)

    return on_bar


_STRATEGIES: dict[str, Callable] = {"momentum": _momentum, "meanrev": _meanrev, "dca": _dca, "weekday": _weekday, "buy_hold": _buy_hold}


# ----------------------------------------------------------------------------------------------- engine

@dataclass
class BacktestResult:
    label: str
    market: str
    start: dt.datetime
    end: dt.datetime
    bars: int
    trades: int
    return_pct: float
    max_drawdown_pct: float
    sharpe: float | None
    win_rate_pct: float | None
    starting_equity: float
    final_equity: float
    equity_curve: list[tuple[dt.datetime, float]]
    benchmark_curve: list[tuple[dt.datetime, float]] | None
    trades_sample: list[Fill]
    notes: list[str]

    def as_dict(self) -> dict:
        def curve(pts: list[tuple[dt.datetime, float]]) -> list[list]:
            return [[ts.isoformat(), round(v, 2)] for ts, v in pts]

        return {
            "label": self.label,
            "market": self.market,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "bars": self.bars,
            "trades": self.trades,
            "return_pct": round(self.return_pct, 4),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "sharpe": None if self.sharpe is None else round(self.sharpe, 3),
            "win_rate_pct": None if self.win_rate_pct is None else round(self.win_rate_pct, 2),
            "starting_equity": self.starting_equity,
            "final_equity": round(self.final_equity, 2),
            "equity_curve": curve(self.equity_curve),
            "benchmark_curve": None if self.benchmark_curve is None else curve(self.benchmark_curve),
            "trades_sample": [
                {"ts": f.ts.isoformat(), "side": f.side, "px": round(f.px, 6), "size": round(f.size, 6), "reason": f.reason} for f in self.trades_sample
            ],
            "notes": self.notes,
        }


def window(days: int, bar: str, now: dt.datetime | None = None) -> tuple[dt.datetime, dt.datetime]:
    step = BAR_SECONDS[bar]
    now = now or dt.datetime.now(UTC)
    end = dt.datetime.fromtimestamp(math.floor(now.timestamp() / step) * step, UTC)
    return end - dt.timedelta(days=days), end


def downsample(points: list, limit: int = CURVE_POINTS) -> list:
    n = len(points)
    if n <= limit:
        return list(points)
    return [points[round(i * (n - 1) / (limit - 1))] for i in range(limit)]


def sample_fills(fills: list[Fill], limit: int = 20) -> list[Fill]:
    return downsample(fills, limit)


def _simulate(candles: list[Candle], market: str, build: Callable[[list[Candle], Book], Step], equity: float, fee_bps: float) -> tuple[Book, list[tuple[dt.datetime, float]]]:
    book = Book(equity, fee_bps)
    step = build(candles, book)
    curve = []
    for i, c in enumerate(candles):
        step(i, c)
        if i == len(candles) - 1:
            book.close(c.ts, market, c.c, "end of window")
        curve.append((c.ts, book.equity({market: c.c})))
    return book, curve


def _stats(book: Book, curve: list[tuple[dt.datetime, float]], equity: float, bar: str) -> dict:
    values = [v for _, v in curve]
    closes = [f.realized for f in book.fills if f.realized != 0]
    return {
        "trades": len(closes),
        "return_pct": (values[-1] / equity - 1) * 100 if values else 0.0,
        "max_drawdown_pct": max_drawdown_pct(values),
        "sharpe": sharpe(values, BAR_SECONDS[bar]),
        "win_rate_pct": (sum(1 for p in closes if p > 0) / len(closes) * 100) if closes else None,
        "final_equity": values[-1] if values else equity,
    }


def run_backtest(spec, source: PriceSource, now: dt.datetime | None = None) -> BacktestResult:
    """Run a validated Spec (see lab.py) against a price source. Raises SourceUnavailable / ValueError."""
    bar = getattr(spec, "bar", "1h")
    start, end = window(spec.days, bar, now)
    notes = [data_note(source, bar), f"fees: {spec.fee_bps} bp taker per side plus {SLIPPAGE_BPS:g} bp slippage on every fill"]
    if spec.type == "tail_wallet":
        return _run_tail(spec, source, start, end, notes)

    candles = cached_candles(source, spec.market, bar, start, end)
    if len(candles) < 2:
        raise ValueError(f"not enough {bar} candles for {spec.market}")
    label = spec.label()
    if spec.type == "event_buy":
        dates = list(spec.custom_dates or []) if spec.event_set == "custom" else [r["date"] for r in load_hacks()]
        in_window = [d for d in dates if start.date() <= d <= end.date()]
        notes.append(HACKS_NOTE if spec.event_set == "major_hacks" else f"custom event dates: {len(dates)} supplied")
        notes.append(f"{len(in_window)} of {len(dates)} event dates fall inside the window")

        def build(cs: list[Candle], bk: Book) -> Step:
            return _event_buy(spec, cs, bk, in_window)

    else:

        def build(cs: list[Candle], bk: Book) -> Step:
            return _STRATEGIES[spec.type](spec, cs, bk)

    book, curve = _simulate(candles, spec.market, build, spec.starting_equity, spec.fee_bps)
    _, bench = _simulate(candles, spec.market, lambda cs, bk: _buy_hold(spec, cs, bk), spec.starting_equity, spec.fee_bps)
    if spec.type == "dca":
        deployed = sum(f.size * f.px for f in book.fills if f.side == "buy")
        notes.append(f"DCA deployed ${deployed:,.0f} of the ${spec.starting_equity:,.0f} starting equity; return is on the full starting equity")
    return BacktestResult(
        label=label,
        market=spec.market,
        start=start,
        end=end,
        bars=len(candles),
        starting_equity=spec.starting_equity,
        equity_curve=downsample(curve),
        benchmark_curve=downsample(bench),
        trades_sample=sample_fills(book.fills),
        notes=notes,
        **_stats(book, curve, spec.starting_equity, bar),
    )


def _run_tail(spec, source: PriceSource, start: dt.datetime, end: dt.datetime, notes: list[str]) -> BacktestResult:
    short = f"{spec.address[:6]}…{spec.address[-4:]}"
    fills = None
    if isinstance(source, HyperliquidCandles):
        try:
            fills = source.fills(spec.address, start, end)
        except SourceUnavailable:
            fills = None
    if fills is not None and spec.markets:
        fills = [f for f in fills if f["coin"] in spec.markets]
    if not fills:
        notes.append(
            f"wallet fills for {short} unavailable ({'no fills in window' if fills == [] else 'sim mode / Hyperliquid unreachable'}): "
            "synthesized a plausible fill series from a 3/10 momentum strategy on BTC instead"
        )
        from .lab import MomentumSpec  # local import: lab depends on this module

        proxy = MomentumSpec(market="BTC", days=spec.days, starting_equity=spec.starting_equity, fee_bps=spec.fee_bps)
        res = run_backtest(proxy, source)
        res.label, res.notes = f"Tail {short} (synthesized)", notes
        return res

    markets = sorted({f["coin"] for f in fills})
    candles = {m: cached_candles(source, m, "1h", start, end) for m in markets}
    grid = sorted({c.ts for cs in candles.values() for c in cs})
    marks_at = {m: {c.ts: c.c for c in cs} for m, cs in candles.items()}
    scale = spec.scale or _default_scale(fills, spec.starting_equity)
    book = Book(spec.starting_equity, spec.fee_bps)
    replay = _replay(fills, scale, book, "1h")
    marks: dict[str, float] = {}
    curve = []
    for ts in grid:
        marks.update({m: marks_at[m][ts] for m in markets if ts in marks_at[m]})
        replay(ts)
        curve.append((ts, book.equity(marks)))
    for m in list(book.positions):
        book.close(grid[-1], m, marks[m], "end of window")
    curve[-1] = (grid[-1], book.equity(marks))
    notes.append(f"replayed {len(fills)} Hyperliquid fills of {short} across {', '.join(markets)} scaled x{scale:.4g}; positions open before the window are ignored")
    notes.append("tail-wallet agents cannot be deployed yet: the deployable is a definition only")
    return BacktestResult(
        label=f"Tail {short}",
        market=",".join(markets),
        start=start,
        end=end,
        bars=len(grid),
        starting_equity=spec.starting_equity,
        equity_curve=downsample(curve),
        benchmark_curve=None,
        trades_sample=sample_fills(book.fills),
        notes=notes,
        **_stats(book, curve, spec.starting_equity, "1h"),
    )


def _default_scale(fills: list[dict], equity: float) -> float:
    """Scale so the wallet's peak gross notional (rebuilt from its fills) equals the follower's equity."""
    pos: dict[str, float] = {}
    last_px: dict[str, float] = {}
    peak = 0.0
    for f in sorted(fills, key=lambda f: int(f["time"])):
        pos[f["coin"]] = pos.get(f["coin"], 0.0) + float(f["sz"]) * (1 if f["side"] == "B" else -1)
        last_px[f["coin"]] = float(f["px"])
        peak = max(peak, sum(abs(s) * last_px[m] for m, s in pos.items()))
    return equity / peak if peak > 0 else 1.0
