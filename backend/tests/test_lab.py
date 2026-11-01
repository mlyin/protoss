import datetime as dt
import os
import shutil

import pytest

os.environ.setdefault("ARENA_MODE", "sim")
os.environ["TICK_SECONDS"] = "0"
os.environ["ADMIN_TOKEN"] = "test-admin"

from fastapi.testclient import TestClient  # noqa: E402

from app import backtest as B  # noqa: E402
from app import db as dbmod  # noqa: E402
from app import hl  # noqa: E402
from app.backtest import load_hacks  # noqa: E402
from app.config import get_settings  # noqa: E402

HEX40 = "0x" + "ab" * 20
REAL_CANDLES = B.FileCandles.DIR  # the shipped cache, before the fixture pins its own copy


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)  # the rule-based planner must carry every test offline
    # the Lab answers from cached candles where it has them; pin the cache to XMR so these tests do not move
    # every time scripts/candles.py ships another market
    cache = tmp_path / "candles"
    cache.mkdir()
    shutil.copy(B.FileCandles.DIR / "XMR_1d.csv", cache / "XMR_1d.csv")
    monkeypatch.setattr(B.FileCandles, "DIR", cache)
    B._source = None
    get_settings.cache_clear()
    dbmod.reset_engine_for_tests()
    hl.set_exchange_for_tests(hl.SimExchange(get_settings(), seed=3))
    from app.main import app

    with TestClient(app) as c:
        yield c
    hl.set_exchange_for_tests(None)


def chat(c, message, **body):
    r = c.post("/lab/chat", json={"message": message, **body})
    assert r.status_code == 200, r.text
    return r.json()


def test_examples(client):
    ex = client.get("/lab/examples").json()["examples"]
    assert len(ex) == 4 and all(isinstance(e, str) and e for e in ex)  # the four demo ideas, nothing else


def test_public_research_does_not_substitute_simulation_for_missing_history(client, monkeypatch):
    from app import lab

    monkeypatch.setenv('ARENA_MODE', 'paper')
    get_settings.cache_clear()
    monkeypatch.setattr(lab, 'get_source', lambda settings: B.SimCandles(settings))
    result = chat(client, 'buy and hold XMR')
    assert result['kind'] == 'error' and result['result'] is None
    assert result['deployable'] is None
    assert 'No simulated performance result was substituted' in result['reply']


def test_hack_events_backtest(client):
    j = chat(client, "what if I bought XMR every time a major company got hacked and held 7 days")  # no window stated
    assert j["kind"] == "backtest", j["reply"]
    assert 'baseline:' in j['reply'] and 'not proof of an edge' in j['reply']
    assert 'event timing:' in j['reply'] and 'cached in the repo' in j['reply']
    assert all(note in j['reply'] for note in j['result']['notes'] if note.startswith('event dataset:'))
    assert 'Prices are simulated' not in j['reply']
    assert j["spec"]["type"] == "event_buy" and j["spec"]["event_set"] == "major_hacks" and j["spec"]["hold_days"] == 7
    assert j["spec"]["days"] == 730  # the hack list reaches back years, so the window widens to the cap
    res = j["result"]
    start, end = dt.datetime.fromisoformat(res["start"]).date(), dt.datetime.fromisoformat(res["end"]).date()
    dates = sorted(r["date"] for r in load_hacks() if start <= r["date"] <= end)
    assert dates, "the 730-day window should contain hack dates"
    assert 0 < res["trades"] <= len(dates)
    if all((b - a).days > 7 for a, b in zip(dates, dates[1:])):  # no overlapping events: one round trip each
        assert res["trades"] == len(dates)
    assert len(res["equity_curve"]) <= 400 and len(res["benchmark_curve"]) <= 400
    assert any("illustrative" in n for n in res["notes"])
    assert res["trades_sample"][0]["side"] == "buy" and res["trades_sample"][-1]["side"] == "sell"
    assert j["deployable"]["markets"] == ["XMR"]
    assert "#" not in j["reply"] and len(j['reply']) < 2500  # retain material research caveats
    # an explicit window keeps the user's choice, and one with no events asks instead of printing a flat 0%
    # (the list is live and now has events in the last 90 days, so pin the list for this check)
    import app.backtest as B

    real = B.load_hacks
    B.load_hacks = lambda: [r for r in real() if r["date"] < dt.date(2025, 6, 1)]
    try:
        short = chat(client, "buy XMR on hacks, hold 7 days, over the last 90 days")
    finally:
        B.load_hacks = real
    assert short["kind"] == "clarify" and short["spec"] is None and "window" in short["reply"].lower()
    far = chat(client, "short BTC for 3 days after 2024-01-15 over the last 30 days")
    assert far["kind"] == "clarify" and far["result"] is None
    recent = chat(client, "short BTC for 3 days after 2025-03-15")  # no window stated: reach back to the event
    assert recent["kind"] == "backtest" and 180 < recent["spec"]["days"] <= 730 and recent["result"]["trades"] == 1


def test_momentum_spec_and_window(client):
    j = chat(client, "backtest a 3/10 momentum crossover on BTC over the last 90 days with $25k")
    assert j["kind"] == "backtest"
    spec, res = j["spec"], j["result"]
    assert spec["type"] == "momentum" and spec["fast"] == 3 and spec["slow"] == 10 and spec["starting_equity"] == 25_000
    span = dt.datetime.fromisoformat(res["end"]) - dt.datetime.fromisoformat(res["start"])
    assert abs(span.days - 90) <= 1 and res["bars"] == 90 * 24
    assert res["starting_equity"] == 25_000 and res["benchmark_curve"] is not None
    assert res["trades"] > 0 and res["sharpe"] is not None and 1 <= len(res["trades_sample"]) <= 20
    assert j["deployable"]["markets"] == ["BTC"] and j["deployable"]["name"] == "lab-momentum-btc"
    assert j["deployable"]["limits"]["allowed_markets"] == ["BTC"] and j["deployable"]["limits"]["max_leverage"] == 2


def test_tail_wallet_never_invents_fills(client):
    j = chat(client, f"tail {HEX40} with $10k")  # sim mode has no wallet fills to replay
    assert j["kind"] == "error" and j["result"] is None and "live Hyperliquid API" in j["reply"]
    assert j["spec"]["type"] == "tail_wallet" and j["spec"]["address"] == HEX40


def test_bad_address_is_error(client):
    j = chat(client, "copy 0xabc with $5k")
    assert j["kind"] == "error" and j["result"] is None and "40 hex" in j["reply"]


def test_clarify(client):
    j = chat(client, "what should I do")
    assert j["kind"] == "clarify" and j["spec"] is None and j["result"] is None and j["reply"].endswith("?")
    assert chat(client, "run a momentum crossover")["kind"] == "clarify"


def test_unlisted_market_is_error(client):
    j = chat(client, "buy and hold FAKECOIN")
    assert j["kind"] == "error" and j["result"] is None and "FAKECOIN" in j["reply"]
    assert "ETH" in chat(client, "buy and hold ETHH")["reply"]  # nearest listed market suggested


def test_buy_hold_matches_benchmark(client):
    j = chat(client, "buy and hold SOL", days=60)
    res = j["result"]
    bench_return = (res["benchmark_curve"][-1][1] / res["starting_equity"] - 1) * 100
    assert abs(res["return_pct"] - bench_return) < 1e-6
    assert res["trades"] == 1 and res["final_equity"] < res["starting_equity"] * 50


def test_dca_weekday_meanrev_parse(client):
    d = chat(client, "DCA $100 into HYPE every week since January")
    assert d["spec"]["type"] == "dca" and d["spec"]["every_days"] == 7 and d["spec"]["amount"] == 100
    assert d["spec"]["days"] >= (dt.date.today() - dt.date(dt.date.today().year, 1, 1)).days - 1
    w = chat(client, "what if I bought NVDA perps every Monday open and sold Friday close")
    assert w["spec"]["type"] == "weekday" and w["spec"]["market"] == "xyz:NVDA" and (w["spec"]["buy_weekday"], w["spec"]["sell_weekday"]) == (0, 4)
    m = chat(client, "fade 2 sigma moves in ethereum on 4h bars with a 30 bar lookback")
    assert m["spec"]["type"] == "meanrev" and m["spec"]["market"] == "ETH" and m["spec"]["z"] == 2 and m["spec"]["lookback"] == 30 and m["spec"]["bar"] == "4h"
    assert m["result"]["bars"] == 180 * 6
    s = chat(client, "short BTC for 3 days after 2026-09-01 and 2026-10-01")
    assert s["spec"]["type"] == "event_buy" and s["spec"]["side"] == "short" and s["spec"]["hold_days"] == 3 and s["spec"]["event_set"] == "custom"
    assert s["result"]["trades"] == 2 and s["result"]["trades_sample"][0]["side"] == "sell"


def test_deterministic(client):
    a = chat(client, "backtest a 3/10 momentum crossover on BTC over the last 30 days")
    b = chat(client, "backtest a 3/10 momentum crossover on BTC over the last 30 days")
    assert a["result"]["final_equity"] == b["result"]["final_equity"]
    assert a["result"]["equity_curve"] == b["result"]["equity_curve"]


def test_dip_buy_on_cached_history(client):
    import csv

    j = chat(client, "buy XMR after it drops 8% in a day and sell 5 days later")
    assert j["kind"] == "backtest", j["reply"]
    spec, res = j["spec"], j["result"]
    assert spec["type"] == "dip_buy" and spec["drop_pct"] == 8 and spec["over_days"] == 1 and spec["hold_days"] == 5
    assert spec["days"] == 730 and res["bars"] > 300  # drops are rare, so the window reaches back to the cap on daily bars
    # every entry is a cached close 8% or more below the one before it, counted here straight from the file
    start, end = (dt.datetime.fromisoformat(res[k]).timestamp() for k in ("start", "end"))
    with open(B.FileCandles.DIR / "XMR_1d.csv", newline="") as f:
        closes = [float(r["c"]) for r in csv.DictReader(f) if start <= int(r["t"]) < end]
    dips = sum(closes[i] / closes[i - 1] - 1 <= -0.08 for i in range(1, len(closes)))
    assert dips and any(n.startswith(f"{dips} closes 8% or more below") for n in res["notes"]), res["notes"]
    assert any(n.startswith("baseline:") for n in res["notes"]) and 0 < res["trades"] <= dips
    assert "Buy XMR after any 8% drop within 1 day, hold 5d" in j["reply"]
    weekly = chat(client, "what if I bought XMR every time it fell 15% in a week and held 2 weeks")
    assert (weekly["spec"]["over_days"], weekly["spec"]["hold_days"]) == (7, 14)
    never = chat(client, "buy XMR when it drops 80% in a day")
    assert never["kind"] == "clarify" and never["reply"].startswith("XMR did not fall 80%")


def test_the_four_ideas(client):
    # cached real history for the markets the ideas trade, so the sim fixture can answer them
    for name in ("xyz_UNITREE_1d.csv", "xyz_ANT_1d.csv", "xyz_NVDA_1d.csv"):
        shutil.copy(REAL_CANDLES / name, B.FileCandles.DIR / name)
    B._source = None
    from app.lab import EXAMPLES

    hacks, robots, bubble, dwarkesh = (chat(client, q) for q in EXAMPLES)
    assert hacks["kind"] == "backtest" and hacks["spec"]["market"] == "XMR" and hacks["spec"]["event_set"] == "major_hacks"
    assert hacks["spec"]["hold_days"] == 1  # the demo idea holds a day; "held 7 days" still means 7
    assert robots["kind"] == "backtest" and robots["spec"]["market"] == "xyz:UNITREE" and robots["spec"]["side"] == "long"
    assert robots["reply"].startswith("Robots taking over: Unitree")
    assert bubble["kind"] == "backtest" and bubble["spec"]["market"] == "xyz:ANT" and bubble["spec"]["side"] == "short"
    assert bubble["result"]["trades_sample"][0]["side"] == "sell" and "not Anthropic shares" in bubble["reply"]
    # the benchmark stays plain buy and hold, so a short and its benchmark move in opposite directions
    b = bubble["result"]
    assert (b["final_equity"] - b["starting_equity"]) * (b["benchmark_curve"][-1][1] - b["starting_equity"]) <= 0
    # Episode research needs evidence, not an invented default market.
    assert dwarkesh["kind"] == "clarify" and dwarkesh["spec"] is None and dwarkesh["result"] is None
    assert "specific claim" in dwarkesh["reply"]
    explicit = chat(client, "buy NVDA on each new Dwarkesh episode and hold 7 days")
    assert explicit["kind"] == "backtest" and explicit["spec"]["event_set"] == "dwarkesh"
    assert explicit["spec"]["market"] == "xyz:NVDA"
    assert "does not analyze episode claims" in explicit["reply"]
    episodes = B.load_events("dwarkesh")
    assert len(episodes) > 100 and episodes[0]["date"] == dt.date(2020, 5, 22)
    # Matthew's own sentence in the group chat maps to the same trade
    own = chat(client, "lets buy unitree i think robots are gonna take over the world")
    assert own["spec"]["market"] == "xyz:UNITREE" and own["spec"]["type"] == "buy_hold"


def test_podcast_idea_cannot_be_assigned_a_market_by_llm(monkeypatch):
    from app import lab

    def unexpected(*args, **kwargs):
        raise AssertionError("An unspecified podcast idea must be clarified before an LLM chooses a trade")

    monkeypatch.setattr(lab, "_plan_llm", unexpected)
    for message in ["Dwarkesh mentioned NVDA", "Dwarkesh had a long episode about NVDA", "Dwarkesh had a short episode about NVDA",
                    "do not buy NVDA on each Dwarkesh episode"]:
        assert isinstance(lab.plan(message, known={"xyz:NVDA"}), lab.Clarify)
    for message in ["Dwarkesh is always right", "Trade every new Dwarkesh episode",
                    "Research each new Dwarkesh episode and propose a trade"]:
        assert isinstance(lab.plan(message, known={"xyz:NVDA"}), lab.Clarify)


def test_podcast_release_rule_preserves_explicit_direction():
    from app.lab import plan_rules

    for instruction, side in [
        ("sell NVDA on each new Dwarkesh episode and hold 7 days", "short"),
        ("short NVDA on each new Dwarkesh episode and hold 7 days", "short"),
        ("buy NVDA on each new Dwarkesh episode and sell after 7 days", "long"),
        ("buy NVDA on every Dwarkesh episode and sell NVDA after 7 days", "long"),
        ("buy NVDA on every Dwarkesh episode and sell 7 days later", "long"),
    ]:
        spec = plan_rules(instruction, 10_000, 180, {"xyz:NVDA"})
        assert spec.event_set == "dwarkesh" and spec.market == "xyz:NVDA"
        assert spec.side == side


def test_hack_buy_then_sell_exit_stays_long():
    from app.lab import plan_rules

    spec = plan_rules("buy XMR after major hacks and sell 7 days later", 10_000, 180, {"XMR"})
    assert spec.side == "long"
