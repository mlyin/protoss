"""Cached Hyperliquid candles answer Lab questions when the API is unreachable."""
import datetime as dt
import os

os.environ.setdefault("ARENA_MODE", "sim")

from app import backtest as B  # noqa: E402
from app import lab as L  # noqa: E402
from app.config import get_settings  # noqa: E402

UTC = dt.timezone.utc


def test_xmr_history_is_shipped_and_layered_over_sim():
    files = B.FileCandles()
    assert files.has("XMR") and "XMR" in files.markets()
    span = files.span("XMR")
    assert span and span[0].date() == dt.date(2024, 8, 22) and span[1] >= dt.datetime(2026, 10, 30, tzinfo=UTC)
    get_settings.cache_clear()
    B._source = None
    src = B.get_source(get_settings())
    assert isinstance(src, B.LayeredCandles) and src.real("XMR") and not src.real("BTC")
    cs = src.candles("XMR", "1d", dt.datetime(2026, 1, 1, tzinfo=UTC), dt.datetime(2026, 2, 1, tzinfo=UTC))
    assert len(cs) == 31 and all(c.l <= c.c <= c.h for c in cs)


def test_event_study_runs_on_real_xmr_candles_and_says_so():
    get_settings.cache_clear()
    B._source = None
    src = B.get_source(get_settings())
    res = B.run_backtest(L.EventBuySpec(market="XMR", days=730, hold_days=7, starting_equity=10_000), src, now=dt.datetime(2026, 10, 31, tzinfo=UTC))
    assert res.bars == 730 and res.trades >= 20
    assert "cached in the repo" in res.notes[0] and "2024-08-22" in res.notes[0]
    assert any("event dates fall inside the window" in n for n in res.notes)
