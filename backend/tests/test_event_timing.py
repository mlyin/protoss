"""Event entries must use information and candle prices available at the reported time."""
import datetime as dt

import pytest

from app import backtest as B
from app.lab import EventBuySpec

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 1, 5, tzinfo=UTC)


class HourlyHistory:
    name = 'test-event-timing'

    def candles(self, market, bar, start, end):
        assert bar == '1h'
        return [B.Candle(start + dt.timedelta(hours=i), 100 + i, 102 + i, 99 + i, 101 + i, 1)
                for i in range(int((end - start).total_seconds() / 3600))]


def study(monkeypatch, row):
    monkeypatch.setattr(B, 'load_events', lambda _: [row])
    B._candle_cache.clear()
    return B.run_backtest(EventBuySpec(market='XMR', days=4, hold_days=1), HourlyHistory(), now=NOW)


def test_publication_time_and_candle_close_bound_every_entry(monkeypatch):
    row = {'date': dt.date(2026, 1, 2), 'published_at': '2026-01-02T20:05:00+00:00',
           'source_url': 'https://example.test/episode'}
    result = study(monkeypatch, row)
    entry = result.trades_sample[0]
    assert entry.side == 'buy'
    assert entry.ts == dt.datetime(2026, 1, 2, 21, tzinfo=UTC)
    # The 20:00 opening-time candle closes at 21:00. Price includes configured slippage.
    assert entry.px == pytest.approx(145 * (1 + B.SLIPPAGE_BPS / 10_000))
    assert result.trades_sample[1].ts == entry.ts + dt.timedelta(days=1)
    observation = result.stats['observations'][0]
    assert observation['available_at'] == row['published_at']
    assert observation['entry_at'] == entry.ts.isoformat()
    assert observation['source_url'] == row['source_url']
    assert result.stats['per_event'][0][0] == '2026-01-02'


def test_date_only_news_waits_until_the_day_is_over(monkeypatch):
    result = study(monkeypatch, {'date': dt.date(2026, 1, 2)})
    assert result.trades_sample[0].ts == dt.datetime(2026, 1, 3, tzinfo=UTC)
    assert result.stats['observations'][0]['entry_at'] == result.trades_sample[0].ts.isoformat()
    assert any('Date-only events wait until the next UTC day' in note for note in result.notes)
    assert all('the gap is the edge' not in note for note in result.notes)


def test_incomplete_holding_period_is_not_reported_as_a_one_day_trade(monkeypatch):
    with pytest.raises(B.NoEventsInWindow, match='no event has a complete 1d holding period'):
        study(monkeypatch, {'date': dt.date(2026, 1, 4), 'published_at': '2026-01-04T20:05:00Z'})


def test_timezone_is_preserved_and_naive_publication_times_are_rejected():
    event = B.study_event({'date': dt.date(2026, 1, 2), 'published_at': '2026-01-02T20:05:00-05:00'})
    assert event.available_at == dt.datetime(2026, 1, 3, 1, 5, tzinfo=UTC)
    with pytest.raises(ValueError, match='timezone'):
        B.study_event({'date': dt.date(2026, 1, 2), 'published_at': '2026-01-02T20:05:00'})


def test_duplicate_publication_times_count_once_in_trades_and_baseline(monkeypatch):
    row = {'date': dt.date(2026, 1, 2), 'published_at': '2026-01-02T20:05:00Z'}
    monkeypatch.setattr(B, 'load_events', lambda _: [row, {**row, 'source_url': 'https://example.test/duplicate'}])
    B._candle_cache.clear()
    result = B.run_backtest(EventBuySpec(market='XMR', days=4, hold_days=1), HourlyHistory(), now=NOW)
    assert len(result.trades_sample) == 2
    assert result.stats['events'] == 1


def test_daily_file_fallback_reports_actual_bar_and_close(tmp_path, monkeypatch):
    (tmp_path / 'XMR_1d.csv').write_text('t,o,h,l,c,v\n' + '\n'.join(
        f'{int((NOW - dt.timedelta(days=i)).timestamp())},100,102,99,101,1' for i in range(4, 0, -1)))
    monkeypatch.setattr(B, 'load_events', lambda _: [{'date': dt.date(2026, 1, 2)}])
    B._candle_cache.clear()
    result = B.run_backtest(EventBuySpec(market='XMR', days=4, hold_days=1), B.FileCandles(tmp_path), now=NOW)
    assert result.bars == 4
    assert result.trades_sample[0].ts == dt.datetime(2026, 1, 3, tzinfo=UTC)
    assert 'Hyperliquid 1d candles' in result.notes[0]
    assert 'simulated' not in result.notes[0]


def test_unused_hourly_cache_cannot_relabel_layered_simulation_as_real(tmp_path, monkeypatch):
    (tmp_path / 'XMR_1h.csv').write_text('t,o,h,l,c,v\n0,100,102,99,101,1\n')
    source = B.LayeredCandles(B.FileCandles(tmp_path), HourlyHistory())
    monkeypatch.setattr(B, 'load_events', lambda _: [{'date': dt.date(2026, 1, 2)}])
    B._candle_cache.clear()
    result = B.run_backtest(EventBuySpec(market='XMR', days=4, hold_days=1), source, now=NOW)
    assert result.notes[0] == B.SIM_NOTE
