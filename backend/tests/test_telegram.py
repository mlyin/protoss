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
    assert any("An account update is available privately" in m["text"] for m in tg.sent)
    assert any("Paper demo. No real funds." in m["text"] for m in tg.sent)
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


def test_private_research_keeps_timing_and_baseline_caveats(client, tmp_path):
    worker, tg, _ = make_bridge(client, tmp_path)
    worker.live = True
    notes = ['baseline: Observed difference, not proof of an edge.', 'event timing: Wait for publication.',
             'event dataset: Verify disclosure dates.', 'history coverage: Stops at the available final candle.',
             'Real Hyperliquid candles cached in the repo.']

    class ResearchOnly:
        def call(self, method, path, body=None):
            assert method == 'POST' and path == '/lab/chat'
            return {'kind': 'backtest', 'reply': 'Historical comparison. Funding is not modelled.', 'result': {'notes': notes}}

    worker.protoss = ResearchOnly()
    worker.handle(message(302, 111, 'buy XMR after major hacks', chat=111))
    response = '\n'.join(row['text'] for row in tg.sent)
    assert all(note in response for note in notes)
    assert all(row['chat_id'] == 111 for row in tg.sent)
    assert 'No order placed' in response


def test_private_research_rejects_simulated_notes_even_if_reply_omits_them(client, tmp_path):
    worker, tg, _ = make_bridge(client, tmp_path)
    worker.live = True

    class Simulated:
        def call(self, method, path, body=None):
            return {'kind': 'backtest', 'reply': 'Result: +99.0%', 'result': {'notes': [backtest.SIM_NOTE]}}

    worker.protoss = Simulated()
    worker.handle(message(303, 111, 'buy XMR', chat=111))
    assert '+99.0%' not in tg.sent[-1]['text']
    assert 'Real market history is unavailable' in tg.sent[-1]['text']


def test_long_research_card_keeps_image_and_all_caveats_without_duplicate_delivery(client, tmp_path):
    worker, _, _ = make_bridge(client, tmp_path)
    text = 'Historical comparison\n' + ('Publication and disclosure timing must be verified.\n' * 30) + 'Funding is not modelled.'

    class PhotoTelegram(FakeTelegram):
        def upload(self, method, fields, *args):
            assert method == 'sendPhoto' and len(fields['caption']) <= 1024
            self.sent.append({'photo': True, 'text': fields['caption']})
            return {'message_id': len(self.sent)}

    class QueuedResearch:
        def call(self, method, path, body=None):
            if path.endswith('/outbox'):
                return [{'id': 1, 'kind': 'card', 'thesis_id': 1, 'text': text}]
            if path.endswith('/delivered'):
                return {'delivered': 1}
            return {'mode': 'paper', 'theses': [{'id': 1, 'n': 1, 'status': 'proposed', 'test': {}}]}

        def get_bytes(self, path):
            return b'test image payload'

    worker.telegram, worker.protoss = PhotoTelegram(), QueuedResearch()
    worker.drain()
    sent = worker.telegram.sent
    assert sum(bool(row.get('photo')) for row in sent) == 1
    assert 'Funding is not modelled.' in sent[-1]['text']
    assert sum(row['text'].count('Publication and disclosure timing must be verified.') for row in sent) == 30
    count = len(sent)
    worker.drain()
    assert len(sent) == count


@pytest.mark.parametrize('image_first', [True, False])
def test_card_retry_keeps_caveats_when_image_availability_changes(client, tmp_path, image_first):
    worker, _, _ = make_bridge(client, tmp_path)
    text = 'Historical comparison\n' + ('Verify publication timing.\n' * 60) + 'Funding is not modelled.'

    class FlakyTelegram(FakeTelegram):
        failed = False

        def upload(self, method, fields, *args):
            self.sent.append({'photo': True, 'text': fields['caption']})
            return {'message_id': len(self.sent)}

        def call(self, method, **body):
            if method == 'sendMessage' and 'Funding is not modelled.' in body.get('text', '') and not self.failed:
                self.failed = True
                raise bridge.APIError('temporary text failure')
            return super().call(method, **body)

    class QueuedResearch:
        attempts = 0
        delivered = 0

        def call(self, method, path, body=None):
            if path.endswith('/outbox'):
                return [{'id': 1, 'kind': 'card', 'thesis_id': 1, 'text': text}]
            if path.endswith('/delivered'):
                self.delivered += 1
                return {'delivered': 1}
            return {'mode': 'paper', 'theses': [{'id': 1, 'n': 1, 'status': 'proposed', 'test': {}}]}

        def get_bytes(self, path):
            self.attempts += 1
            if (self.attempts == 1) != image_first:
                raise bridge.APIError('image unavailable')
            return b'test image payload'

    worker.telegram, worker.protoss = FlakyTelegram(), QueuedResearch()
    with pytest.raises(bridge.APIError):
        worker.drain()
    assert worker.protoss.delivered == 0
    worker.drain()
    sent = worker.telegram.sent
    assert worker.protoss.delivered == 1
    assert sum(row['text'].count('Funding is not modelled.') for row in sent) == 1
    assert sum(row['text'].count('Verify publication timing.') for row in sent) == 60
    assert sum(bool(row.get('photo')) for row in sent) == int(image_first)
    count = len(sent)
    worker.drain()
    assert len(sent) == count


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


def test_dwarkesh_menu_requests_episode_evidence_without_creating_a_trade(client, tmp_path):
    worker, tg, hid = make_bridge(client, tmp_path)
    worker.handle(message(501, 111, "Dwarkesh mentioned NVDA"))
    assert "specific claim" in tg.sent[-1]["text"]
    assert client.get(f"/huddle/{hid}", headers=ADMIN).json()["theses"] == []
    worker.handle({"update_id": 502, "callback_query": {"id": "d1", "from": {"id": 222},
                  "data": "idea:dwarkesh", "message": {"chat": {"id": CHAT, "type": "supergroup"}}}})
    assert client.get(f"/huddle/{hid}", headers=ADMIN).json()["theses"] == []
    assert "specific claim" in tg.sent[-1]["text"]
    assert not any("Back this idea" in str(m.get("reply_markup")) for m in tg.sent)


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
    shared = "\n".join(m["text"] for m in tg.sent if m["chat_id"] == CHAT)
    assert "Wallet connections" not in shared and "Deposit not checked" not in shared
    assert account1.address[:8] not in shared and account2.address[:8] not in shared
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
    assert [row["proposal"] for row in after if row["n"] > 1000] == frozen  # copies are numbered from 1001


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


def test_guided_setup_keeps_token_out_of_output(monkeypatch, capsys, tmp_path):
    token = "unit-test-token-not-a-real-credential"
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setattr(bridge.getpass, "getpass", lambda prompt: token)
    monkeypatch.setattr("builtins.input", lambda prompt: "")
    monkeypatch.setattr(bridge.Path, "home", lambda: tmp_path)
    class SetupTelegram:
        def __init__(self, supplied):
            assert supplied == token
        def call(self, method, **body):
            if method == "getMe":
                return {"id": 123, "username": "demo_bot"}
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


def test_group_position_requests_never_lookup_or_publish_positions(client, tmp_path, monkeypatch):
    from app import huddle as HD

    worker, tg, hid = make_bridge(client, tmp_path)

    def no_financial_lookup(*args, **kwargs):
        raise AssertionError('shared position request must not fetch account data')

    for method in ('mark', 'positions', 'equity'):
        monkeypatch.setattr(hl.get_exchange(), method, no_financial_lookup)
    worker.handle(message(1, 111, '/mine'))
    worker.handle(message(2, 111, "what's my position?"))
    worker.handle({'update_id': 3, 'callback_query': {'id': 'mine', 'from': {'id': 222}, 'data': 'mine',
                   'message': {'chat': {'id': CHAT, 'type': 'supergroup'}}}})
    assert len(tg.sent) == 3
    for sent in tg.sent:
        assert sent['chat_id'] == CHAT
        assert sent['text'].endswith(HD.PRIVATE_POSITIONS_NOTICE)
        assert sent['reply_markup']['inline_keyboard'] == [[{'text': 'My positions', 'url': 'https://protoss.trade/app/'}]]
    rows = client.get(f'/huddle/{hid}', headers=ADMIN).json()['messages']
    assert all(row['text'] == HD.PRIVATE_POSITIONS_NOTICE for row in rows if row['from_bot'])


def test_legacy_position_messages_are_redacted_without_deleting_database_rows(client, tmp_path):
    from app import huddle as HD
    from app.db import session

    worker, tg, hid = make_bridge(client, tmp_path)
    private = "Owner's positions: private-position-sentinel 6.5 XMR from $125. P&L +$900."
    with session() as db:
        row = HD.HuddleMessage(huddle_id=hid, sender=HD.BOT, text=private, kind='mine', from_bot=True, delivered=False)
        db.add(row)
        db.flush()
        row_id = row.id
    for path in [f'/huddle/{hid}', f'/huddle/{hid}/outbox']:
        response = client.get(path, headers=ADMIN)
        assert 'private-position-sentinel' not in response.text
        assert HD.PRIVATE_POSITIONS_NOTICE in response.text

    class OlderAPI(LocalAPI):
        def call(self, method, path, body=None):
            if method == 'GET' and path.endswith('/outbox'):
                return [{'id': row_id, 'kind': 'mine', 'text': private}]
            return super().call(method, path, body)

    worker.protoss = OlderAPI(client)
    worker.drain()
    assert 'private-position-sentinel' not in str(tg.sent)
    assert tg.sent[-1]['text'].endswith(HD.PRIVATE_POSITIONS_NOTICE)
    with session() as db:
        row = db.get(HD.HuddleMessage, row_id)
        assert row.text == private and row.delivered


def test_private_thesis_json_html_and_cards_require_authentication_even_when_cached(client, tmp_path):
    worker, tg, hid = make_bridge(client, tmp_path)
    worker.handle(message(1, 111, '/idea buy and hold Anthropic'))
    thesis = client.get(f'/huddle/{hid}', headers=ADMIN).json()['theses'][0]
    tid = thesis['id']
    for path in [f'/theses/{tid}', f'/t/{tid}', f'/og/t/{tid}.png', f'/og/t/{tid}.png?format=phone']:
        assert client.get(path).status_code == 403
        assert client.get(path, headers={'x-admin-token': 'wrong'}).status_code == 403
        authorized = client.get(path, headers=ADMIN)
        assert authorized.status_code == 200
        assert authorized.headers['cache-control'] == 'private, no-store'
        assert client.get(path).status_code == 403  # populated server cache does not bypass authorization


def test_public_simulated_web_idea_previews_remain_accessible(client):
    h = client.get('/huddle/web/public-preview').json()
    response = client.post(f"/huddle/{h['id']}/messages", json={'sender': 'Test user', 'text': 'protoss buy and hold Anthropic'})
    assert response.status_code == 201
    tid = client.get(f"/huddle/{h['id']}").json()['theses'][0]['id']
    for path in [f'/theses/{tid}', f'/t/{tid}', f'/og/t/{tid}.png']:
        assert client.get(path).status_code == 200


def test_legacy_account_updates_and_status_are_private_without_changing_records(client, tmp_path, monkeypatch):
    from app import huddle as HD
    from app.db import session

    worker, tg, hid = make_bridge(client, tmp_path)
    sentinel = 'private-financial-sentinel 6.5 XMR at $125 with profit $900'
    with session() as db:
        child = HD.Thesis(huddle_id=hid, n=1001, author='tg:111', text='Public idea', kind='rule', label='Public idea',
                          spec={'_telegram_copy_owner': 'tg:111', '_parent_n': 1})
        db.add(child)
        db.flush()
        tid = child.id
        rows = [HD.HuddleMessage(huddle_id=hid, sender=HD.BOT, text=sentinel, kind='result', from_bot=True, thesis_id=tid, delivered=False),
                HD.HuddleMessage(huddle_id=hid, sender=HD.BOT, text="Here's where things stand:\n" + sentinel, kind='text', from_bot=True, delivered=False),
                HD.HuddleMessage(huddle_id=hid, sender=HD.BOT, text='Call 2 from a friend: hit\nScore, by whose idea it was:\n' + sentinel, kind='text', from_bot=True, delivered=False)]
        db.add_all(rows)
        db.flush()
        old = {r.id: r.text for r in rows}
    for path in [f'/huddle/{hid}', f'/huddle/{hid}/outbox']:
        assert sentinel not in client.get(path, headers=ADMIN).text

    class OlderAPI(LocalAPI):
        def call(self, method, path, body=None):
            if method == 'GET' and path.endswith('/outbox'):
                return [{'id': rid, 'kind': 'result' if i == 0 else 'text', 'text': text, 'thesis_id': tid if i == 0 else None}
                        for i, (rid, text) in enumerate(old.items())]
            return super().call(method, path, body)

    worker.protoss = OlderAPI(client)
    worker.drain()
    assert sentinel not in str(tg.sent)
    assert len(tg.sent) == 3
    assert all(m['reply_markup']['inline_keyboard'][0][0]['url'] == 'https://protoss.trade/app/' for m in tg.sent)
    with session() as db:
        assert all(db.get(HD.HuddleMessage, rid).text == text for rid, text in old.items())
        assert all(db.get(HD.HuddleMessage, rid).delivered for rid in old)

    def no_lookup(*args, **kwargs):
        raise AssertionError('shared status cannot inspect private positions')

    for method in ('mark', 'positions', 'equity'):
        monkeypatch.setattr(hl.get_exchange(), method, no_lookup)
    worker.protoss = LocalAPI(client)
    worker.handle(message(900, 111, '/status'))
    worker.handle(message(901, 111, '/score'))
    assert sentinel not in str(tg.sent)


@pytest.mark.parametrize('wallet_review', [False, True])
def test_shared_status_does_not_query_wallet_connections_or_trade_receipts(client, tmp_path, wallet_review):
    worker, tg, hid = make_bridge(client, tmp_path)
    worker.wallet_review = wallet_review

    class PrivateAPI(LocalAPI):
        def call(self, method, path, body=None):
            assert not path.endswith('/connections'), 'group must not read linked wallets'
            assert not path.startswith('/live/groups/'), 'group must not read or verify owner receipts'
            return super().call(method, path, body)

    worker.protoss = PrivateAPI(client)
    worker.handle(message(902, 111, '/status'))
    assert not any('Wallet connections' in row['text'] or 'tg:111' in row['text'] for row in tg.sent)
    if wallet_review:
        assert tg.sent[-1]['text'].startswith('Your positions are private.')
