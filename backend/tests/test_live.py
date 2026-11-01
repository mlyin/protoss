"""User-owned mainnet intents, frozen quotes, real-fill evidence, and browser signing parity.

All exchange responses and Telegram sends are fake. No test submits a mainnet action.
"""
import json
import subprocess
from decimal import Decimal
from pathlib import Path

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from hyperliquid.utils.signing import action_hash

from app import live
from app.config import get_settings, Settings
from test_telegram import client, ADMIN, make_bridge, message


@pytest.fixture()
def enabled(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_LIVE_ENABLED", "true")
    get_settings.cache_clear()
    yield client
    get_settings.cache_clear()


@pytest.fixture()
def market(monkeypatch):
    calls = []
    state = {"balance": "100", "mode": "disabled", "positions": [], "status": {"status": "unknownOid"}, "fills": []}
    def info(body):
        calls.append(body)
        kind = body["type"]
        if kind == "metaAndAssetCtxs":
            return [{"universe": [{"name": "xyz:ANT", "szDecimals": 2}]}, [{"markPx": "110"}]]
        if kind == "perpDexs":
            return [None, {"name": "other"}, {"name": "xyz"}]
        if kind == "l2Book":
            return {"time": state.get("book_time", live.now_ms()), "levels": [[{"px": "109.9"}], [{"px": "110"}]]}
        if kind == "clearinghouseState":
            return {"withdrawable": state["balance"], "assetPositions": state["positions"], "marginSummary": {"accountValue": state["balance"]}}
        if kind == "userAbstraction":
            return state["mode"]
        if kind == "spotClearinghouseState":
            return {"balances": [{"coin": "USDC", "total": "98"}]}
        if kind == "orderStatus":
            return state["status"]
        if kind == "userFillsByTime":
            return state["fills"]
        raise AssertionError(body)
    monkeypatch.setattr(live, "info", info)
    return state, calls


def request(client, uid="111", idea=None, wallet=None):
    if idea is None:
        h = client.post("/huddle", headers=ADMIN, json={"chat_id": "telegram:-100", "title": "Live test", "quorum": 2}).json()
        idea = client.post("/live/ideas", headers=ADMIN, json={"huddle_id": h["id"], "request_id": "test-idea", "market": "ANT"}).json()
        idea["huddle_id"] = h["id"]
    r = client.post("/live/intents", headers=ADMIN, json={"idea_id": idea["id"], "telegram_user_id": uid, "display_name": "Person " + uid, "budget": "20"})
    assert r.status_code == 200, r.text
    intent = r.json()
    link = client.post(f"/live/intents/{intent['id']}/link", headers=ADMIN, json={"telegram_user_id": uid, "huddle_id": idea["huddle_id"]}).json()["url"]
    headers = {"Authorization": "Bearer " + link.split("token=")[1]}
    wallet = wallet or Account.create()
    data = client.get("/live/review", headers=headers).json()
    sig = wallet.sign_message(encode_defunct(text=data["challenge"])).signature.hex()
    response = client.post("/live/wallet", headers=headers, json={"wallet": wallet.address, "signature": "0x" + sig.removeprefix("0x")})
    return idea, intent, headers, wallet, response


def test_live_is_opt_in_and_links_are_private(client):
    assert client.get("/live/review").status_code == 403


def test_browser_approval_cannot_share_server_execution_mode():
    with pytest.raises(ValueError, match="separately"):
        Settings(arena_mode="copies", telegram_live_enabled=True, admin_token="test-admin")


def test_quotes_use_real_market_identifiers_and_cap_exposure(enabled, market):
    idea, intent, headers, wallet, response = request(enabled)
    assert response.status_code == 200
    assert enabled.get("/live/review").status_code == 401
    q = enabled.post("/live/quote", headers=headers, json={}).json()
    assert q["order_action"]["orders"][0]["a"] == 120000
    assert q["order_action"]["orders"][0]["c"] == "0x" + intent["id"]
    assert q["leverage_action"] == {"type": "updateLeverage", "asset": 120000, "isCross": True, "leverage": 1}
    assert Decimal(q["size"]) * Decimal(q["limit_price"]) <= 20
    assert Decimal(q["limit_price"]) <= Decimal(q["ask"]) * Decimal("1.005")
    assert q["order_action"]["orders"][0]["t"] == {"limit": {"tif": "Ioc"}}
    # No browser approval yet: merely generating a quote creates no receipt or order submission.
    assert enabled.get("/live/review", headers=headers).json()["status"] == "draft"
    assert enabled.post("/live/prepare", headers=headers, json={"nonce": q["nonce"] + 1}).status_code == 409
    assert enabled.post("/live/prepare", headers=headers, json={"nonce": q["nonce"]}).status_code == 200
    assert enabled.post("/live/prepare", headers=headers, json={"nonce": q["nonce"]}).status_code == 409
    assert enabled.post("/live/quote", headers=headers, json={}).status_code == 409
    assert enabled.post("/live/verify", headers=headers, json={}).json()["receipt"] is None


def test_separate_wallet_identity_and_amount_are_bound(enabled, market):
    idea, intent, headers, wallet, response = request(enabled)
    other = request(enabled, uid="222", idea=idea, wallet=wallet)
    assert other[-1].status_code == 409
    assert enabled.post(f"/live/intents/{intent['id']}/link", headers=ADMIN,
        json={"telegram_user_id": "222", "huddle_id": idea["huddle_id"]}).status_code == 404
    assert enabled.post("/live/intents", headers=ADMIN, json={"idea_id": idea["id"], "telegram_user_id": "111", "display_name": "Person", "budget": "50"}).status_code == 409
    second = request(enabled, uid="222", idea=idea)
    assert second[-1].status_code == 200
    assert second[3].address != wallet.address


@pytest.mark.parametrize("condition", ["no_money", "position", "stale", "portfolio"])
def test_quote_fails_closed(enabled, market, condition):
    state, _ = market
    _, _, headers, _, _ = request(enabled)
    if condition == "no_money": state["balance"] = "12"
    if condition == "position": state["positions"] = [{"position": {"coin": "xyz:ANT", "szi": "1"}}]
    if condition == "stale": state["book_time"] = 0
    if condition == "portfolio": state["mode"] = "portfolioMargin"
    assert enabled.post("/live/quote", headers=headers, json={}).status_code in (409, 503)


def test_unified_account_is_not_misreported_as_unfunded(enabled, market):
    state, _ = market
    state.update(balance="0", mode="unifiedAccount")
    _, _, headers, _, _ = request(enabled)
    response = enabled.post("/live/quote", headers=headers, json={})
    assert response.status_code == 200
    assert response.json()["account"]["spot_balances"][0]["total"] == "98"


def fill_order(state, q, partial=False):
    state["status"] = {"status": "order", "order": {"status": "canceled" if partial else "filled", "order": {
        "coin": "xyz:ANT", "cloid": q["cloid"], "side": "B", "origSz": q["size"], "limitPx": q["limit_price"], "oid": 1234}}}
    state["fills"] = [{"coin": "xyz:ANT", "oid": 1234, "side": "B", "sz": "0.1" if partial else q["size"],
        "px": "110", "time": q["nonce"] + 20, "fee": "0.01", "feeToken": "USDC", "tid": 999}]


@pytest.mark.parametrize("partial", [False, True])
def test_exchange_verified_receipt_is_idempotent(enabled, market, partial):
    state, calls = market
    idea, _, headers, wallet, _ = request(enabled)
    q = enabled.post("/live/quote", headers=headers, json={}).json()
    enabled.post("/live/prepare", headers=headers, json={"nonce": q["nonce"]})
    fill_order(state, q, partial)
    # Unrelated fills never become this participant's receipt.
    unrelated = {**state["fills"][0], "oid": 99999}
    state["fills"] = [unrelated]
    assert enabled.post("/live/verify", headers=headers, json={}).json()["receipt"] is None
    fill_order(state, q, partial)
    state["fills"].append(dict(state["fills"][0]))
    result = enabled.post("/live/verify", headers=headers, json={}).json()
    assert result["status"] == ("partial" if partial else "filled")
    assert result["receipt"]["wallet"] == wallet.address.lower()
    assert result["receipt"]["size"] == ("0.1" if partial else q["size"])
    enabled.post("/live/verify", headers=headers, json={})
    outbox = enabled.get(f"/huddle/{idea['huddle_id']}/outbox", headers=ADMIN).json()
    assert len([r for r in outbox if "Verified on Hyperliquid" in r["text"]]) == 1
    assert all(c["type"] != "order" for c in calls)


def test_old_quotes_and_wrong_order_evidence_rejected(enabled, market, monkeypatch):
    state, _ = market
    _, _, headers, _, _ = request(enabled)
    q = enabled.post("/live/quote", headers=headers, json={}).json()
    original = live.now_ms
    monkeypatch.setattr(live, "now_ms", lambda: q["expires_after"])
    assert enabled.post("/live/prepare", headers=headers, json={"nonce": q["nonce"]}).status_code == 409
    monkeypatch.setattr(live, "now_ms", original)
    enabled.post("/live/prepare", headers=headers, json={"nonce": q["nonce"]})
    fill_order(state, q)
    state["status"]["order"]["order"]["cloid"] = "0x" + "0" * 32
    assert enabled.post("/live/verify", headers=headers, json={}).status_code == 502


def test_telegram_real_flow_has_no_simulation_receipts(enabled, tmp_path, market):
    worker, telegram, hid = make_bridge(enabled, tmp_path)
    worker.wallet_review = True
    worker.handle(message(1, 111, "/idea buy and hold ANT"))
    for idx, user in enumerate([111, 222], 2):
        worker.handle(message(idx, user, "/pledge 20"))
        url = telegram.sent[-1]["reply_markup"]["inline_keyboard"][0][0]["url"]
        worker.handle(message(idx + 10, user, "/start " + url.split("start=")[1], chat=user))
        assert "#/trade?token=" in telegram.sent[-1]["reply_markup"]["inline_keyboard"][0][0]["url"]
    ideas = enabled.get(f"/live/groups/{hid}", headers=ADMIN).json()
    assert len(ideas[0]["participants"]) == 2
    assert all(p["status"] == "draft" for p in ideas[0]["participants"])
    assert not any("Paper demo" in m["text"] or "copy filled" in m["text"] for m in telegram.sent)
    assert enabled.get(f"/huddle/{hid}", headers=ADMIN).json()["theses"] == []


def test_browser_order_hash_matches_official_sdk():
    root = Path(__file__).resolve().parents[2]
    actions = [{"type": "updateLeverage", "asset": 120000, "isCross": True, "leverage": 1},
        {"type": "order", "orders": [{"a": 120000, "b": True, "p": "110.55", "s": "0.18", "r": False,
            "t": {"limit": {"tif": "Ioc"}}, "c": "0x" + "a" * 32}], "grouping": "na"},
        {"type": "vaultTransfer", "vaultAddress": "0x" + "b" * 40, "isDeposit": True, "usd": 20000000}]
    nonce, expires = 1793490000000, 1793490120000
    for action in actions:
        script = "import {actionHash} from './web/src/hlsign.js'; console.log(actionHash(" + json.dumps(action) + f",{nonce},{expires}));"
        result = subprocess.run(["node", "--input-type=module", "-e", script], cwd=root, capture_output=True, text=True, check=True)
        assert result.stdout.strip() == "0x" + action_hash(action, None, nonce, expires).hex()
