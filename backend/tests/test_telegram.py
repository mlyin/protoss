"""Two Telegram identities through the actual API, paper fills and signed wallet links."""
import datetime as dt
import importlib.util
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi.testclient import TestClient

from app import backtest, db as dbmod, hl
from app.config import get_settings

spec = importlib.util.spec_from_file_location("telegram_bridge", Path(__file__).resolve().parents[2] / "scripts/telegram_bridge.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)
ADMIN = {"x-admin-token": "test-admin"}
CHAT = -100123


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ARENA_MODE", "sim")
    monkeypatch.setenv("ADMIN_TOKEN", "test-admin")
    monkeypatch.setenv("TICK_SECONDS", "0")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/telegram.db")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cache = tmp_path / "candles"
    cache.mkdir()
    monkeypatch.setattr(backtest.FileCandles, "DIR", cache)
    backtest._source = None
    get_settings.cache_clear()
    dbmod.reset_engine_for_tests()
    hl.set_exchange_for_tests(hl.SimExchange(get_settings(), seed=3))
    from app.main import app
    with TestClient(app) as c:
        yield c
    hl.set_exchange_for_tests(None)
    get_settings.cache_clear()
    backtest._source = None


class LocalAPI:
    def __init__(self, client):
        self.client = client

    def call(self, method, path, body=None):
        response = self.client.request(method, path, json=body, headers=ADMIN)
        assert response.is_success, response.text
        return response.json()


class FakeTelegram:
    def __init__(self):
        self.sent = []

    def call(self, method, **body):
        if method == "sendMessage":
            self.sent.append(body)
            return {"message_id": len(self.sent)}
        assert method == "answerCallbackQuery"
        return True


def make_bridge(client, tmp_path):
    h = client.post("/huddle", headers=ADMIN, json={"chat_id": f"telegram:{CHAT}", "title": "Protoss demo", "quorum": 2}).json()
    tg = FakeTelegram()
    worker = bridge.Bridge(tg, LocalAPI(client), bridge.State(tmp_path / "state.json"), CHAT, [111, 222], "protoss_demo_bot", h["id"])
    return worker, tg, h["id"]


def message(update_id, user, text, chat=CHAT):
    return {"update_id": update_id, "message": {"message_id": update_id, "chat": {"id": chat, "type": "private" if chat == user else "supergroup"},
            "from": {"id": user, "first_name": "Same name"}, "text": text}}


def test_two_accounts_to_paper_fill_and_retry(client, tmp_path):
    worker, tg, hid = make_bridge(client, tmp_path)
    worker.handle(message(1, 111, "/idea buy and hold Anthropic"))
    card = next(m for m in tg.sent if "reply_markup" in m)
    assert card["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "back:1"
    assert "Paper demo" in card["text"] and "xyz:ANT" in card["text"]
    callback = {"update_id": 2, "callback_query": {"id": "c1", "from": {"id": 222}, "data": "back:1",
                "message": {"chat": {"id": CHAT, "type": "supergroup"}}}}
    worker.handle(callback)
    worker.handle(message(3, 111, "/pledge 20"))
    h = client.get(f"/huddle/{hid}", headers=ADMIN).json()
    assert h["theses"][0]["status"] == "proposed"  # both people pledge independently
    worker.handle(message(4, 222, "/pledge 20"))
    worker.handle(message(4, 222, "/pledge 20"))  # Telegram replay must not add another $20
    h = client.get(f"/huddle/{hid}", headers=ADMIN).json()
    thesis = h["theses"][0]
    assert thesis["status"] == "live" and thesis["pledged_usd"] == 40
    assert {b["who"] for b in thesis["backers"]} == {"tg:111", "tg:222"}
    copies = h["theses"][1:]
    assert len(copies) == 2 and len({copy["agent_id"] for copy in copies}) == 2
    assert {copy["author"] for copy in copies} == {"tg:111", "tg:222"}
    assert all(copy["pledged_usd"] == 20 and len(copy["triggers"]) == 1 for copy in copies)
    assert any("separate paper copy filled" in m["text"] for m in tg.sent)
    assert any("practice money" in m["text"] for m in tg.sent)
    assert client.get(f"/huddle/{hid}/outbox", headers=ADMIN).json() == []
    old_count = len(tg.sent)
    worker.drain()
    assert len(tg.sent) == old_count


def test_uninvited_users_wrong_groups_and_bot_messages_are_ignored(client, tmp_path):
    worker, tg, hid = make_bridge(client, tmp_path)
    worker.handle(message(1, 333, "/idea buy and hold BTC"))
    worker.handle(message(2, 111, "/idea buy and hold BTC", chat=-999))
    update = message(3, 111, "/idea buy and hold BTC")
    update["message"]["from"]["is_bot"] = True
    worker.handle(update)
    worker.handle(message(4, 111, "/idea@another_bot buy and hold BTC"))
    assert tg.sent == []
    assert client.get(f"/huddle/{hid}", headers=ADMIN).json()["theses"] == []


def test_private_research_is_separate_from_group_and_accepts_new_users(client, tmp_path):
    worker, tg, hid = make_bridge(client, tmp_path)
    worker.live = True
    calls = []

    class ResearchOnly:
        def call(self, method, path, body=None):
            calls.append((method, path, body))
            assert (method, path) == ("POST", "/lab/chat")
            return {"kind": "clarify", "reply": "Which holding period should I test?"}

    worker.protoss = ResearchOnly()
    worker.handle(message(101, 333, "hi", chat=333))
    assert len(tg.sent[-1]["reply_markup"]["inline_keyboard"]) == 4
    worker.handle(message(102, 333, "buy XMR after a hack", chat=333))
    assert len(calls) == 1 and "Which holding period" in tg.sent[-1]["text"]
    worker.handle(message(103, 111, "/pledge 50", chat=111))
    worker.handle(message(104, 333, "/status", chat=333))
    worker.handle(message(105, 333, "Dwarkesh is always right", chat=333))
    worker.handle(message(106, 333, f"/start join_{CHAT}", chat=333))
    assert len(calls) == 1
    assert all(m["chat_id"] in (111, 333) for m in tg.sent)
    assert client.get(f"/huddle/{hid}", headers=ADMIN).json()["theses"] == []
    assert client.get(f"/telegram/huddles/{hid}/connections", headers=ADMIN).json() == []


def test_private_buttons_failures_and_replay_do_not_reach_orders(client, tmp_path):
    worker, tg, hid = make_bridge(client, tmp_path)
    worker.live = True

    class Unavailable:
        def call(self, method, path, body=None):
            assert path == "/lab/chat"
            raise bridge.APIError("unavailable")

    worker.protoss = Unavailable()
    update = {"update_id": 201, "callback_query": {"id": "p1", "from": {"id": 111},
              "data": "research:unitree", "message": {"chat": {"id": 111, "type": "private"}}}}
    worker.handle(update)
    worker.handle(update)
    assert len(tg.sent) == 1 and "unavailable" in tg.sent[0]["text"]
    update["update_id"] = 202
    update["callback_query"]["data"] = "back:1"
    worker.handle(update)
    assert "Choose one" in tg.sent[-1]["text"]
    assert client.get(f"/huddle/{hid}", headers=ADMIN).json()["theses"] == []


def test_private_sim_backend_never_reports_fake_results(client, tmp_path):
    worker, tg, _ = make_bridge(client, tmp_path)
    worker.handle(message(301, 111, "buy XMR", chat=111))
    assert "No simulated result" in tg.sent[-1]["text"]


def test_group_upgrade_preserves_checkpoint_and_rejects_other_identities(tmp_path):
    state = bridge.State(tmp_path / "upgrade.json")
    old = {"bot": 123, "chat": CHAT, "users": [111, 222]}
    state.data.update(identity=old, offset=987, sent={"outbox:1:0": 12})
    new = {**old, "chat": -100456}
    with pytest.raises(bridge.APIError):
        bridge.bind_identity(state, new)
    with pytest.raises(bridge.APIError):
        bridge.bind_identity(state, {**new, "users": [111, 333]}, CHAT)
    bridge.bind_identity(state, new, CHAT)
    saved = bridge.State(state.path).data
    assert saved["identity"] == new and saved["offset"] == 987
    assert saved["sent"] == {"outbox:1:0": 12}


def test_group_greeting_replies_without_creating_idea(client, tmp_path):
    worker, tg, hid = make_bridge(client, tmp_path)
    worker.handle(message(401, 111, "yo"))
    assert tg.sent[-1]["chat_id"] == CHAT and "I'm here" in tg.sent[-1]["text"]
    assert client.get(f"/huddle/{hid}", headers=ADMIN).json()["theses"] == []


def private_token(tg):
    url = tg.sent[-1]["reply_markup"]["inline_keyboard"][0][0]["url"]
    return parse_qs(urlsplit(url).fragment.split("?", 1)[1])["token"][0]


def sign(client, token, account):
    headers = {"Authorization": "Bearer " + token}
    data = client.get("/telegram/connect", headers=headers).json()
    signature = account.sign_message(encode_defunct(text=data["challenge"])).signature.hex()
    return headers, {"wallet": account.address, "signature": "0x" + signature.removeprefix("0x")}


def test_private_links_prove_two_distinct_wallets_without_deposits(client, tmp_path):
    worker, tg, hid = make_bridge(client, tmp_path)
    worker.handle(message(1, 111, "/join"))
    assert tg.sent[-1]["chat_id"] == CHAT
    worker.handle(message(2, 111, f"/start join_{CHAT}", chat=111))
    token1 = private_token(tg)
    assert tg.sent[-1]["chat_id"] == 111
    # Same update after restart must not rotate the private token.
    worker.handle(message(2, 111, f"/start join_{CHAT}", chat=111))
    account1, account2 = Account.create(), Account.create()
    h1, body1 = sign(client, token1, account1)
    assert client.get("/telegram/connect", headers=h1).headers["cache-control"] == "no-store"
    assert client.post("/telegram/connect", headers=h1, json=body1).json()["ownership_verified"]
    worker.handle(message(3, 222, f"/start join_{CHAT}", chat=222))
    token2 = private_token(tg)
    h2, body2 = sign(client, token2, account2)
    # A signature for the first identity's challenge cannot authenticate the second.
    assert client.post("/telegram/connect", headers=h2, json=body1).status_code == 422
    duplicate_headers, duplicate = sign(client, token2, account1)
    assert client.post("/telegram/connect", headers=duplicate_headers, json=duplicate).status_code == 409
    assert client.post("/telegram/connect", headers=h2, json=body2).json()["deposit_verified"] is False
    assert len(client.get(f"/telegram/huddles/{hid}/connections", headers=ADMIN).json()) == 2
    assert client.get(f"/telegram/huddles/{hid}/connections").status_code == 403
    assert client.get("/telegram/connect").status_code == 401
    worker.handle(message(4, 111, "/status"))
    assert any("Deposit not checked" in m["text"] for m in tg.sent)
    assert client.get("/orgs").json() == []  # wallet linking never creates or funds a vault


def test_expired_and_rotated_links_fail(client, tmp_path):
    worker, tg, hid = make_bridge(client, tmp_path)
    worker.handle(message(1, 111, f"/start join_{CHAT}", chat=111))
    old = private_token(tg)
    worker.handle(message(2, 111, f"/start join_{CHAT}", chat=111))
    current = private_token(tg)
    assert client.get("/telegram/connect", headers={"Authorization": "Bearer " + old}).status_code == 404
    from app.telegram import WalletConnection
    from sqlalchemy import select
    with dbmod.session() as db:
        row = db.scalar(select(WalletConnection))
        row.expires_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)
    assert client.get("/telegram/connect", headers={"Authorization": "Bearer " + current}).status_code == 410


def test_link_creation_needs_admin_and_a_telegram_group(client):
    body = {"huddle_id": 999, "telegram_user_id": "111", "display_name": "A"}
    assert client.post("/telegram/links", json=body).status_code == 403
    assert client.post("/telegram/links", json=body, headers=ADMIN).status_code == 404


def test_crypto_basket_has_four_independent_fills(client, tmp_path):
    worker, tg, hid = make_bridge(client, tmp_path)
    worker.handle(message(2, 111, "/idea buy and hold 60% BTC and 40% ETH"))
    worker.handle(message(3, 111, "/pledge 20"))
    worker.handle(message(4, 222, "/pledge 50"))
    worker.handle(message(4, 222, "/pledge 50"))
    rows = client.get(f"/huddle/{hid}", headers=ADMIN).json()["theses"]
    assert rows[0]["proposal"]["holdings"] == [{"market": "BTC", "weight": 0.6}, {"market": "ETH", "weight": 0.4}]
    assert rows[0]["proposal"]["automatic_updates"] is False
    assert {row["author"] for row in rows[1:]} == {"tg:111", "tg:222"}
    assert len({row["agent_id"] for row in rows[1:]}) == 2
    for row, total in zip(rows[1:], [20, 50]):
        assert row["pledged_usd"] == total
        assert {fill["market"] for fill in row["triggers"]} == {"BTC", "ETH"}
        values = {fill["market"]: fill["size"] * fill["entry_px"] for fill in row["triggers"]}
        assert values["BTC"] / sum(values.values()) == pytest.approx(0.6, abs=0.001)
        assert sum(values.values()) <= total
    # A new idea does not silently change the existing copies.
    frozen = [row["proposal"] for row in rows[1:]]
    worker.handle(message(5, 111, "/idea buy and hold SOL"))
    after = client.get(f"/huddle/{hid}", headers=ADMIN).json()["theses"]
    assert [row["proposal"] for row in after[1:3]] == frozen


def test_browser_crypto_demo_uses_the_same_engine(client):
    room = client.get("/huddle/web/copies-basket-test").json()
    for sender, text in [("You", "protoss buy and hold 60% BTC and 40% ETH"), ("You", "in for 20"), ("Your friend", "in for 50")]:
        assert client.post(f"/huddle/{room['id']}/messages", json={"sender": sender, "text": text}).status_code == 201
    result = client.get(f"/huddle/{room['id']}").json()
    assert len(result["theses"]) == 3
    assert all(len(copy["triggers"]) == 2 for copy in result["theses"][1:])


def test_invalid_basket_is_not_silently_replaced(client):
    for text in ["Buy and hold 60% BTC and 60% ETH", "Buy and hold 60% BTC and 40% ETH and SOL",
                 "Buy and hold 60% BTC and 40% NONEXISTENT"]:
        result = client.post("/lab/chat", json={"message": text}).json()
        assert result["kind"] in ("clarify", "error"), result


def test_basket_backtest_contains_both_assets_and_costs(client):
    result = client.post("/lab/chat", json={"message": "Buy and hold 60% BTC and 40% ETH", "days": 30}).json()
    assert result["kind"] == "backtest", result
    assert {fill["market"] for fill in result["result"]["trades_sample"]} == {"BTC", "ETH"}
    assert any("funding is not modelled" in note for note in result["result"]["notes"])
    assert result["deployable"]["markets"] == ["BTC", "ETH"]


def test_setup_discovers_only_human_group_participants():
    updates = [message(1, 111, "/help"), message(2, 222, "/help"), message(3, 999, "/start", chat=999)]
    bot = message(4, 777, "/help")
    bot["message"]["from"]["is_bot"] = True
    updates += [bot, {"update_id": 5, "channel_post": {"chat": {"id": -999, "type": "channel"}}}]
    groups = bridge.discover_groups(updates)
    assert set(groups) == {CHAT}
    assert groups[CHAT]["users"] == {111, 222}


def test_guided_setup_keeps_token_out_of_output(monkeypatch, capsys):
    token = "unit-test-token-not-a-real-credential"
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setattr(bridge.getpass, "getpass", lambda prompt: token)
    monkeypatch.setattr("builtins.input", lambda prompt: "")
    class SetupTelegram:
        def __init__(self, supplied):
            assert supplied == token
        def call(self, method, **body):
            if method == "getMe":
                return {"username": "demo_bot"}
            if method == "getWebhookInfo":
                return {}
            assert method == "getUpdates"
            return [message(1, 111, "/help"), message(2, 222, "/help")]
    monkeypatch.setattr(bridge, "Telegram", SetupTelegram)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    assert bridge.setup_demo() == (CHAT, "111,222")
    assert token not in capsys.readouterr().out
    # Restore via monkeypatch rather than leaving a token in the process environment.
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")


def test_demo_menu_is_the_four_ideas(client, tmp_path):
    worker, tg, hid = make_bridge(client, tmp_path)
    worker.handle(message(1, 111, "/demo"))
    menu = tg.sent[-1]["reply_markup"]["inline_keyboard"]
    assert [row[0]["callback_data"] for row in menu] == ["idea:xmr", "idea:unitree", "idea:ant", "idea:dwarkesh"]
    worker.handle({"update_id": 2, "callback_query": {"id": "ant", "from": {"id": 111}, "data": "idea:ant",
        "message": {"chat": {"id": CHAT, "type": "supergroup"}}}})
    thesis = client.get(f"/huddle/{hid}", headers=ADMIN).json()["theses"][0]
    assert thesis["label"].startswith("Short and hold xyz:ANT")
