from app.risk import AccountState, Intent, LimitSet, drawdown_breached, evaluate

LIM = LimitSet(max_leverage=5, max_notional_usd=150_000, daily_loss_pct=4, drawdown_flatten_pct=10, max_orders_per_min=30, allowed_markets=("BTC", "ETH"))


def state(**kw):
    base = dict(equity=10_000, positions={}, marks={"BTC": 100_000, "ETH": 4_000}, orders_last_minute=0, day_start_equity=10_000, peak_equity=10_000)
    base.update(kw)
    return AccountState(**base)


def test_within_limits_is_approved():
    v = evaluate(Intent("BTC", "buy", 0.1), state(), LIM)
    assert v.decision == "approved" and v.size == 0.1


def test_disallowed_market_rejected():
    v = evaluate(Intent("SOL", "buy", 1), state(marks={"SOL": 200}), LIM)
    assert v.decision == "rejected" and "allowed-market" in v.reason


def test_halted_agent_rejected():
    assert evaluate(Intent("BTC", "buy", 0.1), state(status="halted"), LIM).decision == "rejected"


def test_rate_cap():
    assert evaluate(Intent("BTC", "buy", 0.1), state(orders_last_minute=30), LIM).decision == "rejected"


def test_leverage_resize():
    # 5x on 10k equity = 50k notional = 0.5 BTC max
    v = evaluate(Intent("BTC", "buy", 2.0), state(), LIM)
    assert v.decision == "resized" and abs(v.size - 0.5) < 1e-9 and "leverage" in v.reason


def test_notional_cap_binds_when_lower_than_leverage():
    lim = LimitSet(max_leverage=50, max_notional_usd=20_000, daily_loss_pct=4, drawdown_flatten_pct=10, max_orders_per_min=30, allowed_markets=("BTC",))
    v = evaluate(Intent("BTC", "buy", 1.0), state(), lim)
    assert v.decision == "resized" and abs(v.size - 0.2) < 1e-9 and "notional" in v.reason


def test_existing_positions_count_against_room():
    # already 0.3 BTC long (30k) -> only 20k room -> 0.2 BTC more
    v = evaluate(Intent("BTC", "buy", 1.0), state(positions={"BTC": 0.3}), LIM)
    assert v.decision == "resized" and abs(v.size - 0.2) < 1e-9


def test_no_room_rejects():
    v = evaluate(Intent("ETH", "buy", 1.0), state(positions={"BTC": 0.5}), LIM)  # 50k used of 50k
    assert v.decision == "rejected" and "no room" in v.reason


def test_reducing_is_always_allowed_even_over_limits():
    v = evaluate(Intent("BTC", "sell", 0.2), state(positions={"BTC": 0.8}, equity=5_000), LIM)  # 16x levered, selling down
    assert v.decision == "approved" and v.size == 0.2


def test_reduce_only_cannot_flip():
    v = evaluate(Intent("BTC", "sell", 1.0, reduce_only=True), state(positions={"BTC": 0.3}), LIM)
    assert v.decision == "approved" and abs(v.size - 0.3) < 1e-9


def test_daily_loss_blocks_new_risk_but_not_reducing():
    s = state(equity=9_500, day_start_equity=10_000, positions={"BTC": 0.1})  # -5% on the day
    assert evaluate(Intent("BTC", "buy", 0.1), s, LIM).decision == "rejected"
    assert evaluate(Intent("BTC", "sell", 0.1), s, LIM).decision == "approved"


def test_drawdown_breach():
    breached, dd = drawdown_breached(state(equity=8_900, peak_equity=10_000), LIM)
    assert breached and abs(dd - 11.0) < 1e-9
    assert not drawdown_breached(state(equity=9_100, peak_equity=10_000), LIM)[0]
