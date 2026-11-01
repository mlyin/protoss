"""Do not describe a partial or broken price series as a complete research window."""
import datetime as dt
from dataclasses import replace

import pytest

from app import backtest as B
from app.lab import BuyHoldSpec, EventBuySpec

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 1, tzinfo=UTC)


class History:
    name = 'hyperliquid'

    def __init__(self, rows):
        self.rows = rows

    def candles(self, market, bar, start, end):
        return self.rows


def rows(start, hours):
    return [B.Candle(start + dt.timedelta(hours=i), 100, 102, 99, 101, 1) for i in range(hours)]


def run(history, spec=None):
    B._candle_cache.clear()
    return B.run_backtest(spec or BuyHoldSpec(market='XMR', days=180), History(history), now=NOW)


def test_old_partial_series_reports_its_actual_end_and_cadence():
    start = NOW - dt.timedelta(days=180)
    result = run(rows(start, 72))
    assert result.end == start + dt.timedelta(days=3)
    assert result.coverage['bar'] == '1h'
    assert not result.coverage['complete_requested_window']
    assert result.coverage['requested_end'] == NOW.isoformat()
    assert any('result stops there' in note for note in result.notes)


@pytest.mark.parametrize('defect', ['gap', 'duplicate', 'reversed', 'wrong_interval', 'nan', 'negative', 'bounds', 'volume', 'unfinished'])
def test_broken_series_is_rejected_instead_of_producing_returns(defect):
    start = NOW - dt.timedelta(days=180)
    history = rows(start, 72)
    if defect == 'gap':
        del history[30]
    elif defect == 'duplicate':
        history[30] = history[29]
    elif defect == 'reversed':
        history[30], history[31] = history[31], history[30]
    elif defect == 'wrong_interval':
        history = history[::2]
    elif defect == 'nan':
        history[30] = replace(history[30], c=float('nan'))
    elif defect == 'negative':
        history[30] = replace(history[30], c=-1)
    elif defect == 'bounds':
        history[30] = replace(history[30], h=100)
    elif defect == 'volume':
        history[30] = replace(history[30], v=-1)
    else:
        history[-1] = replace(history[-1], ts=NOW)
    with pytest.raises(B.SourceUnavailable):
        run(history)


def test_a_gap_cannot_extend_an_event_hold_without_disclosure(monkeypatch):
    start = NOW - dt.timedelta(days=4)
    history = rows(start, 96)
    del history[36]
    monkeypatch.setattr(B, 'load_events', lambda _: [{'date': start.date()}])
    with pytest.raises(B.SourceUnavailable, match='missing, duplicate or out-of-order'):
        run(history, EventBuySpec(market='XMR', days=4, hold_days=1))


def test_daily_only_cache_never_claims_hourly_history(tmp_path):
    start = NOW - dt.timedelta(days=4)
    (tmp_path / 'XMR_1d.csv').write_text('t,o,h,l,c,v\n' + '\n'.join(
        f'{int((start + dt.timedelta(days=i)).timestamp())},100,102,99,101,1' for i in range(4)))
    B._candle_cache.clear()
    result = B.run_backtest(BuyHoldSpec(market='XMR', days=4), B.FileCandles(tmp_path), now=NOW)
    assert result.coverage['bar'] == '1d'
    assert result.coverage['complete_requested_window']
    assert result.bars == 4


def test_adaptive_daily_fallback_ends_at_a_completed_day():
    now = NOW + dt.timedelta(hours=13, minutes=37)

    class RecentIntraday(History):
        def candles(self, market, bar, start, end):
            if bar == '1h':
                return rows(end - dt.timedelta(days=2), 48)
            assert bar == '1d' and end == NOW
            return [B.Candle(start + dt.timedelta(days=i), 100, 102, 99, 101, 1) for i in range(30)]

    B._candle_cache.clear()
    result = B.run_backtest(BuyHoldSpec(market='XMR', days=30), RecentIntraday([]), now=now)
    assert result.bars == 30 and result.end == NOW
    assert result.coverage['bar'] == '1d'
    assert result.coverage['complete_requested_window']
