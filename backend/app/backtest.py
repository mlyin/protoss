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
from dataclasses import asdict, dataclass, field
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


def _ms(t: dt.datetime) -> int:
    return int(t.timestamp() * 1000)


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
        step_ms, start_ms, end_ms = BAR_SECONDS[bar] * 1000, _ms(start), _ms(end)
        raw: dict[int, dict] = {}
        try:
            t = start_ms
            while t < end_ms:  # the API caps a response at ~5000 bars
                chunk_end = min(end_ms, t + HL_MAX_BARS * step_ms)
                raw.update({int(r["t"]): r for r in self.info.candles_snapshot(market, bar, t, chunk_end)})
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
        t = _ms(start)
        try:
            while len(out) < cap:
                batch = self.info.user_fills_by_time(address, t, _ms(end))
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
        rng = random.Random(zlib.crc32(market.encode()) + self._seed)  # stable across processes, unlike hash()
        px, out, t = self._prices.get(market, 100.0), [], start
        while t < end:
            o, px = px, px * math.exp(rng.gauss(-0.5 * vol * vol, vol))
            wick = abs(rng.gauss(0, vol * 0.5))
            out.append(Candle(t, o, max(o, px) * (1 + wick), min(o, px) * (1 - wick), px, abs(rng.gauss(50, 20)) * 1000))
            t += dt.timedelta(seconds=step)
        return out


_source: tuple[tuple, PriceSource] | None = None
_candle_cache: dict[tuple, tuple[float, list[Candle]]] = {}


def get_source(settings: Settings) -> PriceSource:
    """SimCandles in sim mode; otherwise Hyperliquid, falling back to SimCandles when unreachable."""
    global _source
    key = (settings.arena_mode, settings.hl_api_url, tuple(settings.hl_perp_dexs))
    if _source and _source[0] == key:
        return _source[1]
    src: PriceSource = SimCandles(settings)
    if settings.arena_mode != "sim":
        from hyperliquid.utils import constants

        url = settings.hl_api_url or (constants.TESTNET_API_URL if settings.arena_mode == "testnet" else constants.MAINNET_API_URL)
        try:
            src = HyperliquidCandles(url, settings.hl_perp_dexs)
        except SourceUnavailable:
            pass
    _source = (key, src)
    return src


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
        rows = [{**r, "date": dt.date.fromisoformat(r["date"])} for r in csv.DictReader(f) if r.get("date")]
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
    realized: float = 0.0  # net of this fill's fee when it reduced a position, else 0


@dataclass
class Book:
    """Perp-style ledger (mirrors hl._apply_fill_to_ledger): cash moves only on realized P&L and fees."""

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
        after, realized = current + signed, 0.0
        if current and (signed > 0) != (current > 0):
            realized = min(abs(signed), abs(current)) * (px - entry) * (1 if current > 0 else -1)
        if current == 0 or (signed > 0) == (current > 0):
            new_entry = (abs(current) * entry + abs(signed) * px) / abs(after) if after else 0.0
        else:
            new_entry = px if abs(signed) > abs(current) else entry
        fee = size * px * self.fee_bps / 10_000
        self.cash += realized - fee
        if abs(after) < 1e-12:
            self.positions.pop(market, None)
        else:
            self.positions[market] = (after, new_entry)
        self.fills.append(Fill(ts, market, side, px, size, reason, realized - fee if realized else 0.0))
        return self.fills[-1]

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
        pos, target = book.size(spec.market), book.equity({spec.market: c.c}) / c.c
        if fast > slow * 1.0005 and pos <= 0:
            book.close(c.ts, spec.market, c.c, "flip short -> long")
            book.fill(c.ts, spec.market, "buy", target, c.c, f"momentum: {spec.fast}-bar avg {fast:.2f} > {spec.slow}-bar {slow:.2f}")
        elif fast < slow * 0.9995 and pos >= 0:
            book.close(c.ts, spec.market, c.c, "flip long -> short")
            book.fill(c.ts, spec.market, "sell", target, c.c, f"momentum: {spec.fast}-bar avg {fast:.2f} < {spec.slow}-bar {slow:.2f}")

    return on_bar


def _meanrev(spec, candles: list[Candle], book: Book) -> Step:
    closes, n = [c.c for c in candles], spec.lookback

    def on_bar(i: int, c: Candle) -> None:
        if i + 1 < n:
            return
        win = closes[i + 1 - n : i + 1]
        mean = sum(win) / n
        sd = math.sqrt(sum((x - mean) ** 2 for x in win) / (n - 1)) or 1e-9
        z, pos = (c.c - mean) / sd, book.size(spec.market)
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
    due = [candles[0].ts]

    def on_bar(i: int, c: Candle) -> None:
        if c.ts >= due[0]:
            book.fill(c.ts, spec.market, "buy", spec.amount / c.c, c.c, f"DCA ${spec.amount:,.0f}")
            due[0] += dt.timedelta(days=spec.every_days)

    return on_bar


def _weekday(spec, candles: list[Candle], book: Book) -> Step:
    def on_bar(i: int, c: Candle) -> None:
        wd = c.ts.weekday()
        first = i == 0 or candles[i - 1].ts.weekday() != wd
        last = i == len(candles) - 1 or candles[i + 1].ts.weekday() != wd
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
    open_side, close_side = ("buy", "sell") if spec.side == "long" else ("sell", "buy")

    def on_bar(i: int, c: Candle) -> None:
        marks = {spec.market: c.c}
        while lots and lots[0][0] <= c.ts:
            book.fill(c.ts, spec.market, close_side, min(lots.pop(0)[1], abs(book.size(spec.market))), c.c, f"exit after {spec.hold_days}d hold")
        while pending and pending[0] <= c.ts:
            when, eq = pending.pop(0), book.equity(marks)
            notional = min(spec.size_pct * eq, max(0.0, eq - book.gross_notional(marks)))  # overlapping events never exceed 100%
            if notional > 0:
                book.fill(c.ts, spec.market, open_side, notional / c.c, c.c, f"event {when:%Y-%m-%d}: {spec.side}")
                lots.append((c.ts + dt.timedelta(days=spec.hold_days), notional / c.c))
                lots.sort()

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
        d = asdict(self)
        d.update(start=self.start.isoformat(), end=self.end.isoformat(), return_pct=round(self.return_pct, 4), max_drawdown_pct=round(self.max_drawdown_pct, 4))
        d.update(sharpe=None if self.sharpe is None else round(self.sharpe, 3), win_rate_pct=None if self.win_rate_pct is None else round(self.win_rate_pct, 2))
        d["final_equity"] = round(self.final_equity, 2)
        for k in ("equity_curve", "benchmark_curve"):
            d[k] = None if d[k] is None else [[ts.isoformat(), round(v, 2)] for ts, v in d[k]]
        d["trades_sample"] = [{"ts": f.ts.isoformat(), "side": f.side, "px": round(f.px, 6), "size": round(f.size, 6), "reason": f.reason} for f in self.trades_sample]
        return d


def window(days: int, bar: str, now: dt.datetime | None = None) -> tuple[dt.datetime, dt.datetime]:
    step = BAR_SECONDS[bar]
    end = dt.datetime.fromtimestamp(math.floor((now or dt.datetime.now(UTC)).timestamp() / step) * step, UTC)
    return end - dt.timedelta(days=days), end


def downsample(points: list, limit: int = CURVE_POINTS) -> list:
    """Evenly spaced subset that always keeps the first and last point."""
    n = len(points)
    return list(points) if n <= limit else [points[round(i * (n - 1) / (limit - 1))] for i in range(limit)]


def _simulate(candles: list[Candle], market: str, build: Callable[[list[Candle], Book], Step], equity: float, fee_bps: float) -> tuple[Book, list]:
    book, curve = Book(equity, fee_bps), []
    step = build(candles, book)
    for i, c in enumerate(candles):
        step(i, c)
        if i == len(candles) - 1:
            book.close(c.ts, market, c.c, "end of window")
        curve.append((c.ts, book.equity({market: c.c})))
    return book, curve


def _result(label: str, market: str, start: dt.datetime, end: dt.datetime, bar: str, book: Book, curve: list, bench: list | None, notes: list[str]) -> BacktestResult:
    values, equity = [v for _, v in curve], book.fills and None
    equity = curve[0][1] if not book.fills else None  # placeholder, replaced below
    closes = [f.realized for f in book.fills if f.realized != 0]
    return BacktestResult(
        label=label, market=market, start=start, end=end, bars=len(curve),
        trades=len(closes),
        return_pct=(values[-1] / book.start_equity - 1) * 100,
        max_drawdown_pct=max_drawdown_pct(values),
        sharpe=sharpe(values, BAR_SECONDS[bar]),
        win_rate_pct=(sum(1 for p in closes if p > 0) / len(closes) * 100) if closes else None,
        starting_equity=book.start_equity,
        final_equity=values[-1],
        equity_curve=downsample(curve),
        benchmark_curve=None if bench is None else downsample(bench),
        trades_sample=downsample(book.fills, 20),
        notes=notes,
    )


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
    if spec.type == "event_buy":
        dates = list(spec.custom_dates or []) if spec.event_set == "custom" else [r["date"] for r in load_hacks()]
        in_window = [d for d in dates if start.date() <= d <= end.date()]
        notes.append(HACKS_NOTE if spec.event_set == "major_hacks" else f"custom event dates: {len(dates)} supplied")
        notes.append(f"{len(in_window)} of {len(dates)} event dates fall inside the window")
        build: Callable = lambda cs, bk: _event_buy(spec, cs, bk, in_window)  # noqa: E731
    else:
        build = lambda cs, bk: _STRATEGIES[spec.type](spec, cs, bk)  # noqa: E731
    book, curve = _simulate(candles, spec.market, build, spec.starting_equity, spec.fee_bps)
    _, bench = _simulate(candles, spec.market, lambda cs, bk: _buy_hold(spec, cs, bk), spec.starting_equity, spec.fee_bps)
    if spec.type == "dca":
        buys = [f for f in book.fills if f.side == "buy"]
        notes.append(f"DCA: {len(buys)} buys deployed ${sum(f.size * f.px for f in buys):,.0f} of the ${spec.starting_equity:,.0f} starting equity; return is on the full starting equity")
    return _result(spec.label(), spec.market, start, end, bar, book, curve, bench, notes)


def _run_tail(spec, source: PriceSource, start: dt.datetime, end: dt.datetime, notes: list[str]) -> BacktestResult:
    short = f"{spec.address[:6]}…{spec.address[-4:]}"
    fills = None
    if isinstance(source, HyperliquidCandles):
        try:
            fills = source.fills(spec.address, start, end)
        except SourceUnavailable:
            fills = None
    if fills and spec.markets:
        fills = [f for f in fills if f["coin"] in spec.markets]
    if not fills:
        why = "no fills in window" if fills == [] else "sim mode / Hyperliquid unreachable"
        notes.append(f"wallet fills for {short} unavailable ({why}): synthesized a plausible fill series from a 3/10 momentum strategy on BTC instead")
        from .lab import MomentumSpec  # lab imports this module; resolve the cycle lazily

        res = run_backtest(MomentumSpec(market="BTC", days=spec.days, starting_equity=spec.starting_equity, fee_bps=spec.fee_bps), source)
        res.label, res.notes = f"Tail {short} (synthesized)", notes
        return res

    fills.sort(key=lambda f: int(f["time"]))
    markets = sorted({f["coin"] for f in fills})
    series = {m: {c.ts: c.c for c in cached_candles(source, m, "1h", start, end)} for m in markets}
    grid = sorted({ts for s in series.values() for ts in s})
    scale = spec.scale or _default_scale(fills, spec.starting_equity)
    book, marks, curve, queue = Book(spec.starting_equity, spec.fee_bps), {}, [], list(fills)
    for ts in grid:
        marks.update({m: series[m][ts] for m in markets if ts in series[m]})
        while queue and int(queue[0]["time"]) < _ms(ts) + 3_600_000:  # fills during this bar, at the wallet's own price
            f = queue.pop(0)
            book.fill(ts, f["coin"], "buy" if f["side"] == "B" else "sell", float(f["sz"]) * scale, float(f["px"]), f"wallet {f.get('dir', 'fill')}", slip=False)
        curve.append((ts, book.equity(marks)))
    for m in list(book.positions):
        book.close(grid[-1], m, marks[m], "end of window")
    curve[-1] = (grid[-1], book.equity(marks))
    notes.append(f"replayed {len(fills)} Hyperliquid fills of {short} across {', '.join(markets)} scaled x{scale:.4g}; positions open before the window are ignored")
    return _result(f"Tail {short}", ",".join(markets), start, end, "1h", book, curve, None, notes)


def _default_scale(fills: list[dict], equity: float) -> float:
    """Scale so the wallet's peak gross notional (rebuilt from its fills) equals the follower's equity."""
    pos: dict[str, float] = {}
    last_px: dict[str, float] = {}
    peak = 0.0
    for f in fills:
        pos[f["coin"]] = pos.get(f["coin"], 0.0) + float(f["sz"]) * (1 if f["side"] == "B" else -1)
        last_px[f["coin"]] = float(f["px"])
        peak = max(peak, sum(abs(s) * last_px[m] for m, s in pos.items()))
    return equity / peak if peak > 0 else 1.0
