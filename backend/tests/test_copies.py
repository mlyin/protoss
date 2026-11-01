"""Live copies: each Telegram participant's order leaves their own Hyperliquid account, signed by the API wallet they
authorized. Exercised offline against a fake exchange with the real adapter, huddle and bridge code."""
import importlib.util
import json
import os
from pathlib import Path

import pytest
from eth_account import Account
from fastapi.testclient import TestClient

from app import backtest, db as dbmod, hl
from app.config import get_settings

spec = importlib.util.spec_from_file_location("telegram_bridge", Path(__file__).resolve().parents[2] / "scripts/telegram_bridge.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)
ADMIN = {"x-admin-token": "test-admin"}
CHAT = -100555

K1, K2 = Account.create(), Account.create()
ACC1, ACC2 = "0x1111111111111111111111111111111111111111", "0x2222222222222222222222222222222222222222"
WALLETS = {"tg:111": {"name": "lando", "address": ACC1, "agent_key": K1.key.hex()},
           "tg:222": {"name": "second", "address": ACC2, "agent_key": K2.key.hex()}}


class FakeInfo:
    """Enough of hyperliquid.info.Info for the adapter: prices, account state, approved agents, fill history."""

    def __init__(self):
        self.authorized = {ACC1.lower(): {K1.address.lower()}, ACC2.lower(): {K2.address.lower()}}
        self.value = {ACC1: {"": 110.61, "xyz": 22.0}, ACC2: {"": 0.0, "xyz": 0.0}}  # second is unified: its 98.21 is spot USDC
        self.positions = {ACC1: {}, ACC2: {}}
        self.fills = {ACC1: [], ACC2: []}

    def all_mids(self, dex=""):
        return {"BTC": "100000", "ETH": "3000", "XMR": "330"} if dex == "" else {"xyz:ANT": "111.0", "xyz:NVDA": "214", "xyz:UNITREE": "96.8"}

    def user_state(self, address, dex=""):
        pos = [{"position": {"coin": m, "szi": str(s), "entryPx": str(e)}} for m, (s, e) in self.positions[address].items() if (":" in m) == (dex == "xyz")]
        return {"marginSummary": {"accountValue": str(self.value[address][dex])}, "assetPositions": pos}

    def post(self, path, body):
        t = body["type"]
        if t == "extraAgents":
            return [{"address": a, "name": "protoss"} for a in self.authorized.get(body["user"].lower(), ())]
        if t == "userFillsByTime":
            return [f for f in self.fills[body["user"]] if f["time"] >= body["startTime"]]
        if t == "clearinghouseState":
            return self.user_state(body["user"], body.get("dex", ""))
        if t == "userAbstraction":
            return "unifiedAccount" if body["user"] == ACC2 else "disabled"
        if t == "spotClearinghouseState":
            return {"balances": [{"coin": "USDC", "total": "98.21"}]} if body["user"] == ACC2 else {"balances": []}
        if t == "meta":
            return {"universe": [{"name": "xyz:ANT", "szDecimals": 2}, {"name": "xyz:NVDA", "szDecimals": 2}, {"name": "xyz:UNITREE", "szDecimals": 2, "onlyIsolated": True}]} if body.get("dex") == "xyz" else \
                   {"universe": [{"name": "BTC", "szDecimals": 5}, {"name": "ETH", "szDecimals": 4}, {"name": "XMR", "szDecimals": 2}]}
        raise AssertionError(body)


class FakeExchange:
    """One per participant, like the SDK's Exchange(agent_key, account_address=master)."""

    made = []

    def __init__(self, wallet, url, account_address=None, perp_dexs=None, info=None):
        self.wallet, self.master, self.info = wallet, account_address, info
        self.leverage = {}
        self.orders = []
        FakeExchange.made.append(self)

    def update_leverage(self, lev, market, is_cross=True):
        self.leverage[market] = lev
        self.cross = getattr(self, "cross", {})
        self.cross[market] = is_cross
        return {"status": "ok"}

    def market_open(self, market, is_buy, size, px, slippage, builder=None):
        import time

        mark = float(self.info.all_mids("xyz" if ":" in market else "")[market])
        self.orders.append((market, is_buy, size))
        cur = self.info.positions[self.master].get(market, (0.0, 0.0))
        self.info.positions[self.master][market] = (cur[0] + (size if is_buy else -size), mark)
        self.info.fills[self.master].append({"coin": market, "px": str(mark), "sz": str(size), "side": "B" if is_buy else "A", "time": int(time.time() * 1000),
                                             "fee": f"{size * mark * 0.00045:.6f}", "hash": "0xfeedbeef" + self.master[-4:], "dir": "Open Long"})
        return {"status": "ok", "response": {"data": {"statuses": [{"filled": {"avgPx": str(mark), "totalSz": str(size), "oid": len(self.orders)}}]}}}

    def market_close(self, market, size, px, slippage, builder=None):
        return self.market_open(market, False, size, px, slippage)


def make_copies(settings, wallets=WALLETS, trading=True):
    from app import copies as C

    ex = C.CopiesExchange.__new__(C.CopiesExchange)
    ex.settings = settings
    ex.url = "https://api.hyperliquid.xyz"
    ex.wallets = dict(wallets)
    ex.max_usd = 100.0
    ex.builder, ex.builder_warning = None, "no builder address configured"
    ex.info = FakeInfo()
    ex._dexs = ["", "xyz"]
    ex._ex_cache, ex._lev_done = {}, set()
    ex._cache, ex._cache_ts = {}, 0.0
    ex.tick()
    FakeExchange.made = []
    # patch the SDK classes the adapter instantiates
    import hyperliquid.exchange as hx

    real = hx.Exchange
    ex._exchange_cls = real

    def factory(wallet, url, account_address=None, perp_dexs=None):
        return FakeExchange(wallet, url, account_address=account_address, perp_dexs=perp_dexs, info=ex.info)

    ex._factory = factory
    return ex


@pytest.fixture()
def live(tmp_path, monkeypatch):
    monkeypatch.setenv("ARENA_MODE", "copies")
    monkeypatch.setenv("MAINNET_TRADING_ENABLED", "true")
    monkeypatch.setenv("ADMIN_TOKEN", "test-admin")
    monkeypatch.setenv("TICK_SECONDS", "0")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/copies.db")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cache = tmp_path / "candles"
    cache.mkdir()
    monkeypatch.setattr(backtest.FileCandles, "DIR", cache)
    backtest._source = None
    class FixtureHistory(backtest.SimCandles):
        # Deterministic stand-in for the historical-data contract. Never call
        # the public market API from these isolated execution-path tests.
        name = 'hyperliquid'

    monkeypatch.setattr(backtest, 'get_source', lambda settings: FixtureHistory(settings))
    get_settings.cache_clear()
    dbmod.reset_engine_for_tests()
    ex = make_copies(get_settings())
    from app import copies as C

    monkeypatch.setattr(C.CopiesExchange, "_exchange_for", lambda self, agent: self._ex_cache.setdefault(agent.owner, self._factory(None, self.url, account_address=self.wallet_for(agent)["address"])))
    hl.set_exchange_for_tests(ex)
    from app.main import app

    with TestClient(app) as c:
        yield c, ex
    hl.set_exchange_for_tests(None)
    get_settings.cache_clear()
    backtest._source = None


class LocalAPI:
    def __init__(self, client):
        self.client = client

    def call(self, method, path, body=None):
        r = self.client.request(method, path, json=body, headers=ADMIN)
        assert r.is_success, r.text
        return r.json()

    def get_bytes(self, path):
        r = self.client.get(path, headers=ADMIN)
        assert r.is_success, r.text
        return r.content


class FakeTelegram:
    def __init__(self):
        self.sent = []

    def call(self, method, **body):
        if method == "sendMessage":
            self.sent.append(body)
            return {"message_id": len(self.sent)}
        return True


def msg(uid, user, text):
    return {"update_id": uid, "message": {"message_id": uid, "chat": {"id": CHAT, "type": "supergroup"}, "from": {"id": user, "first_name": "P"}, "text": text}}


def test_two_participants_two_real_orders_from_their_own_accounts(live, tmp_path):
    client, ex = live
    h = client.post("/huddle", headers=ADMIN, json={"chat_id": f"telegram:{CHAT}", "title": "protoss beta testing", "quorum": 2}).json()
    tg = FakeTelegram()
    w = bridge.Bridge(tg, LocalAPI(client), bridge.State(tmp_path / "s.json"), CHAT, [111, 222], "ProtossTradingDemoBot", h["id"], live=True)
    w.handle(msg(1, 111, "/help"))
    assert "own Hyperliquid account" in tg.sent[-1]["text"] and "paper" not in tg.sent[-1]["text"]
    w.handle(msg(2, 111, "/idea buy and hold xyz:ANT"))
    w.handle({"update_id": 3, "callback_query": {"id": "c", "from": {"id": 222}, "data": "back:1", "message": {"chat": {"id": CHAT, "type": "supergroup"}}}})
    w.handle(msg(4, 111, "/pledge 20"))
    w.handle(msg(5, 222, "/pledge 20"))
    hud = client.get(f"/huddle/{h['id']}", headers=ADMIN).json()
    copies = hud["theses"][1:]
    assert len(copies) == 2 and {c["author"] for c in copies} == {"tg:111", "tg:222"}
    # one SDK exchange per participant, acting for that participant's own master account, leverage set to 1x once
    by_master = {e.master: e for e in FakeExchange.made}
    assert set(by_master) == {ACC1, ACC2}
    for e in by_master.values():
        assert e.leverage == {"xyz:ANT": 1} and len(e.orders) == 1
        market, is_buy, size = e.orders[0]
        assert market == "xyz:ANT" and is_buy and size == 0.18  # $20 at 111 rounded down to the market's 0.01 step
    # Fill records stay private; shared chat receives only a neutral account notice.
    texts = [m["text"] for m in tg.sent]
    assert sum("An account update is available privately" in t for t in texts) == 2
    assert not any("0x1111" in t or "0xfeedbeef" in t or "order filled:" in t for t in texts)
    assert not any("0x2222" in t for t in texts)
    assert not any("paper" in t.lower() or "practice" in t.lower() for t in texts), [t for t in texts if "paper" in t.lower() or "practice" in t.lower()]
    assert any("separate orders, one from each account" in t for t in texts)


def test_unauthorized_wallet_refuses_only_that_copy(live, tmp_path):
    client, ex = live
    ex.info.authorized[ACC2.lower()] = set()  # second account never pressed Authorize
    h = client.post("/huddle", headers=ADMIN, json={"chat_id": f"telegram:{CHAT}", "title": "t", "quorum": 2}).json()
    tg = FakeTelegram()
    w = bridge.Bridge(tg, LocalAPI(client), bridge.State(tmp_path / "s.json"), CHAT, [111, 222], "bot", h["id"], live=True)
    w.handle(msg(1, 111, "/idea buy and hold xyz:ANT"))
    w.handle(msg(2, 222, "/back 1"))
    w.handle(msg(3, 111, "/pledge 20"))
    w.handle(msg(4, 222, "/pledge 20"))
    texts = [m["text"] for m in tg.sent]
    assert sum("An account update is available privately" in t for t in texts) == 2
    assert not any("not authorized" in t or "copy did not go out" in t for t in texts)
    assert {e.master for e in FakeExchange.made} == {ACC1}


def test_sizing_sees_the_pledge_not_the_account_and_caps_orders(live):
    client, ex = live
    from types import SimpleNamespace

    agent = SimpleNamespace(owner="tg:222", starting_equity=20.0, limits=SimpleNamespace(allowed_markets=["xyz:ANT"], max_leverage=1.0))
    assert ex.account_equity(ACC2) == 98.21 and ex.equity(None, agent) == 20.0  # unified: spot USDC counts; sizing still sees the pledge
    ex.info.positions[ACC2] = {"BTC": (0.01, 100000.0), "xyz:ANT": (0.18, 111.0)}
    assert ex.positions(None, agent) == {"xyz:ANT": (0.18, 111.0)}  # the account's other business is not this copy's
    with pytest.raises(RuntimeError, match="per-order cap"):
        ex.place(None, agent, "xyz:ANT", "buy", 1.0, "market", None, False)  # $111 > $100
    ex.settings.mainnet_trading_enabled = False
    with pytest.raises(RuntimeError, match="live copies are off"):
        ex.place(None, agent, "xyz:ANT", "buy", 0.1, "market", None, False)
    ex.settings.mainnet_trading_enabled = True


def test_wallet_file_is_private_and_round_trips(tmp_path, monkeypatch):
    from app import copies as C

    path = tmp_path / "wallets.json"
    C.save_wallet("tg:111", {"name": "lando", "address": ACC1, "agent_key_env": "HL_AGENT_KEY_LANDO"}, path)
    assert oct(path.stat().st_mode & 0o777) == "0o600"
    assert C.load_wallets(path)["tg:111"]["address"] == ACC1
    os.chmod(path, 0o644)
    with pytest.raises(RuntimeError, match="chmod 600"):
        C.load_wallets(path)
    os.chmod(path, 0o600)
    monkeypatch.setenv("HL_AGENT_KEY_LANDO", K1.key.hex())
    assert C._key(C.load_wallets(path)["tg:111"]) == K1.key.hex()
    assert json.loads(path.read_text())["tg:111"].get("agent_key") is None  # env reference, nothing stored


def test_isolated_only_markets_get_isolated_leverage(live):
    client, ex = live
    from types import SimpleNamespace

    agent = SimpleNamespace(owner="tg:111", starting_equity=12.0, limits=SimpleNamespace(allowed_markets=["xyz:UNITREE"], max_leverage=1.0))
    f = ex.place(None, agent, "xyz:UNITREE", "buy", 12 / 96.8, "market", None, False)
    e = ex._ex_cache["tg:111"]
    assert e.cross["xyz:UNITREE"] is False and e.leverage["xyz:UNITREE"] == 1
    assert f.size == 0.12 and f.market == "xyz:UNITREE"
    f2 = ex.place(None, agent, "xyz:ANT", "buy", 0.1, "market", None, False)
    assert e.cross["xyz:ANT"] is True and f2.size == 0.1


def test_plain_chat_thesis_thumbs_up_and_in_for_sends_two_real_orders(live, tmp_path):
    """No slash commands: a sentence proposes, a thumbs up backs, "in for 11" pledges. Two orders, two accounts."""
    client, ex = live
    h = client.post("/huddle", headers=ADMIN, json={"chat_id": f"telegram:{CHAT}", "title": "protoss beta testing", "quorum": 2}).json()
    tg = FakeTelegram()
    w = bridge.Bridge(tg, LocalAPI(client), bridge.State(tmp_path / "s.json"), CHAT, [111, 222], "ProtossTradingDemoBot", h["id"], live=True)
    w.handle(msg(1, 111, "lets buy unitree i think robots are gonna take over the world"))
    card = next(m for m in tg.sent if "reply_markup" in m)
    assert "xyz:UNITREE" in card["text"]
    card_id = card["chat_id"] and len(tg.sent)  # FakeTelegram numbers message ids by send order
    card_mid = next(i + 1 for i, m in enumerate(tg.sent) if "reply_markup" in m)
    assert w.state.data["cards"][str(card_mid)] == 1
    # the friend reacts with a thumbs up on the card
    w.handle({"update_id": 2, "message_reaction": {"chat": {"id": CHAT, "type": "supergroup"}, "message_id": card_mid, "user": {"id": 222},
                                                    "new_reaction": [{"type": "emoji", "emoji": "\U0001F44D"}]}})
    w.handle(msg(3, 111, "in for 11"))
    w.handle(msg(4, 222, "in for 11"))
    by_master = {e.master: e for e in FakeExchange.made}
    assert set(by_master) == {ACC1, ACC2}
    for e in by_master.values():
        market, is_buy, size = e.orders[0]
        assert market == "xyz:UNITREE" and is_buy and size == 0.11 and e.cross["xyz:UNITREE"] is False
    texts = [m["text"] for m in tg.sent]
    assert sum("An account update is available privately" in t for t in texts) == 2
    assert not any("paper" in t.lower() for t in texts)
    # a stray chat line that is neither thesis nor backing is ignored, not answered with help
    before = len(tg.sent)
    w.handle(msg(5, 111, "lol"))
    assert len(tg.sent) == before


class PhotoTelegram(FakeTelegram):
    def upload(self, method, fields, name, filename, data, mime="image/png"):
        self.sent.append({"method": method, "text": fields["caption"], "photo": data, **{k: v for k, v in fields.items() if k != "caption"}})
        return {"message_id": len(self.sent)}


def test_cards_go_out_as_a_chart_with_no_local_links(live, tmp_path):
    client, ex = live
    h = client.post("/huddle", headers=ADMIN, json={"chat_id": f"telegram:{CHAT}", "title": "protoss beta testing", "quorum": 2}).json()
    tg = PhotoTelegram()
    w = bridge.Bridge(tg, LocalAPI(client), bridge.State(tmp_path / "s.json"), CHAT, [111, 222], "ProtossTradingDemoBot", h["id"], live=True)
    w.handle(msg(1, 111, "/idea buy and hold xyz:ANT"))
    card = next(m for m in tg.sent if m.get("method") == "sendPhoto")
    assert card["photo"][:8] == b"\x89PNG\r\n\x1a\n" and card["reply_markup"]["inline_keyboard"][0][0]["text"] == "Back this idea"
    assert "http" not in card["text"] and "tg:111" not in card["text"] and "from P" in card["text"]
    # a thumbs up on the photo backs the idea like it did on the text card
    assert w.state.data["cards"][str(tg.sent.index(card) + 1)] == 1


def test_hack_fires_each_copy_by_name_closes_and_scores_the_idea_author(live, tmp_path):
    import datetime as dt

    from app import huddle as HD
    from app.db import session

    client, ex = live
    h = client.post("/huddle", headers=ADMIN, json={"chat_id": f"telegram:{CHAT}", "title": "protoss beta testing", "quorum": 2}).json()
    tg = PhotoTelegram()
    w = bridge.Bridge(tg, LocalAPI(client), bridge.State(tmp_path / "s.json"), CHAT, [111, 222], "ProtossTradingDemoBot", h["id"], live=True)
    named = lambda uid, user, name, text: {"update_id": uid, "message": {"message_id": uid, "chat": {"id": CHAT, "type": "supergroup"}, "from": {"id": user, "first_name": name}, "text": text}}  # noqa: E731
    w.handle(named(1, 111, "Matthew", "Let's buy XMR every time a major company gets hacked"))
    w.handle(named(2, 222, "Lando", "in for 11"))
    w.handle(named(3, 111, "Matthew", "in for 11"))
    w.handle(named(4, 111, "Matthew", "protoss hack: Example Exchange drained for $40M"))
    fired = [m["text"] for m in tg.sent if " fired on " in m["text"]]
    assert fired == []
    assert sum("An account update is available privately" in m["text"] for m in tg.sent) == 4
    with session() as db:
        assert HD.settle(db, ex, now=dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=2)) == 2
    w.drain()
    assert not any(" copy of idea 1 closed: XMR" in m["text"] for m in tg.sent)
    assert sum("An account update is available privately" in m["text"] for m in tg.sent) == 6
    w.handle(named(5, 111, "Matthew", "protoss score"))
    assert tg.sent[-1]["text"].startswith("Your positions are private.")


def test_close_my_idea_closes_only_the_senders_copy(live, tmp_path):
    client, ex = live
    h = client.post("/huddle", headers=ADMIN, json={"chat_id": f"telegram:{CHAT}", "title": "protoss beta testing", "quorum": 2}).json()
    tg = PhotoTelegram()
    w = bridge.Bridge(tg, LocalAPI(client), bridge.State(tmp_path / "s.json"), CHAT, [111, 222], "ProtossTradingDemoBot", h["id"], live=True)
    named = lambda uid, user, name, text: {"update_id": uid, "message": {"message_id": uid, "chat": {"id": CHAT, "type": "supergroup"}, "from": {"id": user, "first_name": name}, "text": text}}  # noqa: E731
    w.handle(named(1, 111, "Matthew", "I think robots are going to take over the world"))
    w.handle(named(2, 222, "Lando", "in for 11"))
    w.handle(named(3, 111, "Matthew", "in for 11"))
    w.handle(named(4, 222, "Lando", "close my idea 1"))
    closed = [m["text"] for m in tg.sent if " closed: " in m["text"]]
    assert closed == []
    assert tg.sent[-1]["text"].startswith("An account update is available privately")
    sides = [(e.master, o[1]) for e in FakeExchange.made for o in e.orders]
    assert (ACC2, False) in sides and (ACC1, False) not in sides  # Lando sold; Matthew's position is untouched
    w.handle(named(5, 222, "Lando", "/close 1"))
    assert tg.sent[-1]["text"] == "You have no open copy of idea 1 here."
    w.handle(named(6, 111, "Matthew", "/status"))
    assert "Wallet connections" not in tg.sent[-2]["text"] and tg.sent[-1]["text"].startswith("Here's where things stand:")


def test_buttons_and_replies_make_the_chat_interactive(live, tmp_path):
    client, ex = live
    h = client.post("/huddle", headers=ADMIN, json={"chat_id": f"telegram:{CHAT}", "title": "protoss beta testing", "quorum": 2}).json()
    tg = PhotoTelegram()
    w = bridge.Bridge(tg, LocalAPI(client), bridge.State(tmp_path / "s.json"), CHAT, [111, 222], "ProtossTradingDemoBot", h["id"], live=True)
    named = lambda uid, user, name, text: {"update_id": uid, "message": {"message_id": 100 + uid, "chat": {"id": CHAT, "type": "supergroup"}, "from": {"id": user, "first_name": name}, "text": text}}  # noqa: E731
    tap = lambda uid, user, name, data, card: {"update_id": uid, "callback_query": {"id": str(uid), "from": {"id": user, "first_name": name}, "data": data, "message": {"message_id": card, "chat": {"id": CHAT, "type": "supergroup"}}}}  # noqa: E731
    w.handle(named(1, 111, "Matthew", "I think robots are going to take over the world"))
    card = next(m for m in tg.sent if m.get("method") == "sendPhoto")
    assert card["reply_parameters"]["message_id"] == 101  # the card answers Matthew's message
    card_mid = tg.sent.index(card) + 1
    buttons = [b["callback_data"] for row in card["reply_markup"]["inline_keyboard"] for b in row]
    assert buttons == ["back:1", "in:1:10", "in:1:20", "in:1:50"]
    w.handle(tap(2, 222, "Lando", "in:1:20", card_mid))
    assert tg.sent[-1]["text"].startswith("Lando is in for $20 on idea 1.") and tg.sent[-1]["reply_parameters"]["message_id"] == card_mid
    w.handle(tap(3, 111, "Matthew", "in:1:10", card_mid))
    fills = [m for m in tg.sent if "An account update is available privately" in m["text"]]
    assert len(fills) == 2
    assert all(m["reply_markup"]["inline_keyboard"][0][0]["url"] == "https://protoss.trade/app/" for m in fills)
    w.handle(tap(4, 222, "Lando", "mine", card_mid))
    mine = tg.sent[-1]
    assert mine["text"].startswith("Your positions are private.") and "xyz:UNITREE" not in mine["text"] and "Matthew" not in mine["text"]
    assert mine["reply_markup"]["inline_keyboard"][0][0] == {"text": "My positions", "url": "https://protoss.trade/app/"}
    w.handle(tap(5, 222, "Lando", "close:1", card_mid))
    assert tg.sent[-1]["text"].startswith("An account update is available privately")
    w.handle(named(6, 111, "Matthew", "what's my position?"))
    assert tg.sent[-1]["text"].startswith("Your positions are private.") and tg.sent[-1]["reply_parameters"]["message_id"] == 106
