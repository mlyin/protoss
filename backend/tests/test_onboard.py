"""Join with card: options, region gate, session creation, provider URLs, polling."""
import os
from urllib.parse import parse_qs, urlparse

import pytest

os.environ.setdefault("ARENA_MODE", "sim")
os.environ["TICK_SECONDS"] = "0"
os.environ["ADMIN_TOKEN"] = "test-admin"

from fastapi.testclient import TestClient  # noqa: E402

from app import db as dbmod  # noqa: E402
from app import hl  # noqa: E402
from app.config import get_settings  # noqa: E402

ADMIN = {"x-admin-token": "test-admin"}
WALLET = "0x" + "ab" * 20
VAULT = "0x" + "cd" * 20


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    monkeypatch.delenv("ONRAMP_MOONPAY_KEY", raising=False)
    get_settings.cache_clear()
    dbmod.reset_engine_for_tests()
    hl.set_exchange_for_tests(hl.SimExchange(get_settings(), seed=5))
    from app.main import app

    with TestClient(app) as c:
        yield c
    hl.set_exchange_for_tests(None)
    get_settings.cache_clear()


def seed_legion(c, vault=None):
    org = c.post("/admin/orgs", json={
        "name": "Lee's Semis Legion", "slug": "lee-semis", "leader": "lee", "initial_deposit": 1_000,
        "mandate": "BTC and ETH momentum. Never above 3x.",
        "limits": {"max_leverage": 3, "max_notional_usd": 60_000, "drawdown_flatten_pct": 12, "allowed_markets": ["BTC", "ETH"]},
    }, headers=ADMIN).json()
    assert "org_key" in org, org
    if vault:
        from app.models import Org
        with dbmod.session() as s:
            o = s.query(Org).filter_by(slug="lee-semis").one()
            o.hl_vault = vault
            s.commit()
    return org


def test_options_always_offer_manual_and_name_the_wallet_provider(client):
    seed_legion(client)
    d = client.get("/onboard/options", params={"legion": "lee-semis"}).json()
    assert [p["id"] for p in d["providers"]] == ["manual"]
    assert d["wallet_provider"] == {"id": "privy", "app_id": None}
    assert d["destination"] == {"kind": "wallet", "address": None, "legion": "Lee's Semis Legion"}
    assert d["blocked"] is None and d["min_usd"] == 20


def test_us_region_is_refused_plainly(client):
    seed_legion(client)
    d = client.post("/onboard/session", json={"legion": "lee-semis", "amount_usd": 100, "provider": "manual", "wallet": WALLET},
                    headers={"cf-ipcountry": "US"}).json()
    assert d["status"] == "unavailable" and "US" in d["reason"]
    assert client.get("/onboard/options", headers={"cf-ipcountry": "us"}).json()["blocked"]


def test_session_targets_the_vault_and_polls_to_funded(client, monkeypatch):
    seed_legion(client, vault=VAULT)
    r = client.post("/onboard/session", json={"legion": "lee-semis", "amount_usd": 100, "provider": "manual", "wallet": WALLET, "region": "DE"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "ok" and d["url"] is None
    assert d["destination"] == {"kind": "vault", "address": VAULT}
    assert len(d["steps"]) == 4 and "Lee's Semis Legion" in d["steps"][2]
    sid = d["session_id"]
    p = client.get(f"/onboard/session/{sid}").json()
    assert p["status"] == "created" and p["funded_usd"] == 0
    # sim mode: funds arrive 20 s in
    import app.onboard as ob
    import datetime as dt
    real_now = ob._now
    monkeypatch.setattr(ob, "_now", lambda: real_now() + dt.timedelta(seconds=25))
    p = client.get(f"/onboard/session/{sid}").json()
    assert p["status"] == "funded" and p["funded_usd"] == 100
    p = client.post(f"/onboard/session/{sid}/staked", json={"tx": "0xfeed"}).json()
    assert p["status"] == "staked"


def test_wallet_is_required_and_minimum_enforced(client):
    seed_legion(client)
    d = client.post("/onboard/session", json={"legion": "lee-semis", "amount_usd": 100, "provider": "manual"}).json()
    assert d["status"] == "needs_wallet"
    r = client.post("/onboard/session", json={"legion": "lee-semis", "amount_usd": 5, "provider": "manual", "wallet": WALLET})
    assert r.status_code == 422
    r = client.post("/onboard/session", json={"legion": "lee-semis", "amount_usd": 50, "provider": "moonpay", "wallet": WALLET})
    assert r.status_code == 422  # not configured, not offered


def test_moonpay_url_is_signed_when_a_secret_is_set(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/m.db")
    monkeypatch.setenv("ONRAMP_MOONPAY_KEY", "pk_test_x")
    monkeypatch.setenv("ONRAMP_MOONPAY_SECRET", "sk_test_y")
    monkeypatch.setenv("ONRAMP_MOONPAY_CURRENCY", "usdc_hypercore")
    get_settings.cache_clear()
    dbmod.reset_engine_for_tests()
    hl.set_exchange_for_tests(hl.SimExchange(get_settings(), seed=5))
    from app.main import app
    try:
        with TestClient(app) as c:
            seed_legion(c)
            opts = c.get("/onboard/options").json()
            mp = next(p for p in opts["providers"] if p["id"] == "moonpay")
            assert mp["delivers"] == "hypercore"
            d = c.post("/onboard/session", json={"legion": None, "amount_usd": 250, "provider": "moonpay", "wallet": WALLET}).json()
            assert d["status"] == "ok" and d["url"].startswith("https://buy.moonpay.com?")
            q = parse_qs(urlparse(d["url"]).query)
            assert q["walletAddress"] == [WALLET] and q["currencyCode"] == ["usdc_hypercore"] and q["baseCurrencyAmount"] == ["250.00"]
            assert q["externalTransactionId"] == [d["session_id"]] and q["signature"]
            assert d["destination"] == {"kind": "wallet", "address": WALLET}
            assert c.get(f"/onboard/session/{d['session_id']}").json()["status"] == "redirected"
    finally:
        hl.set_exchange_for_tests(None)
        get_settings.cache_clear()


def _moonpay_post(c, key, event, *, t=None, sig=None):
    import hashlib
    import hmac
    import json
    import time
    body = json.dumps(event).encode()
    t = str(int(time.time()) if t is None else t)
    sig = sig or hmac.new(key.encode(), t.encode() + b"." + body, hashlib.sha256).hexdigest()
    return c.post("/onboard/webhooks/moonpay", content=body, headers={"content-type": "application/json", "Moonpay-Signature-V2": f"t={t},s={sig}"})


def test_moonpay_webhook_flips_a_session_to_funded_only_when_signed(client, monkeypatch):
    seed_legion(client, vault=VAULT)
    sid = client.post("/onboard/session", json={"legion": "lee-semis", "amount_usd": 100, "provider": "manual", "wallet": WALLET, "region": "DE"}).json()["session_id"]
    done = {"type": "transaction_updated", "data": {"status": "completed", "externalTransactionId": sid, "quoteCurrencyAmount": 96.12}}
    # not configured: refuse rather than accept unsigned money news
    assert _moonpay_post(client, "wk_test_x", done).status_code == 503
    monkeypatch.setenv("ONRAMP_MOONPAY_WEBHOOK_KEY", "wk_test_x")
    get_settings.cache_clear()
    assert _moonpay_post(client, "wk_test_wrong", done).status_code == 401
    assert _moonpay_post(client, "wk_test_x", done, t=1_000_000_000).status_code == 401  # replayed from 2001
    assert client.get(f"/onboard/session/{sid}").json()["status"] == "created"
    r = _moonpay_post(client, "wk_test_x", done)
    assert r.status_code == 200 and r.json()["session_status"] == "funded"
    p = client.get(f"/onboard/session/{sid}").json()
    assert p["status"] == "funded" and p["funded_usd"] == 96.12
    # a late "failed" never walks a funded session backwards; an unknown session is acknowledged and ignored
    failed = {"type": "transaction_failed", "data": {"status": "failed", "externalTransactionId": sid}}
    assert _moonpay_post(client, "wk_test_x", failed).json()["session_status"] == "funded"
    other = {"type": "transaction_updated", "data": {"status": "completed", "externalTransactionId": "nope"}}
    assert _moonpay_post(client, "wk_test_x", other).json()["ignored"] == "no matching session"


def test_moonpay_webhook_marks_a_failed_payment(client, monkeypatch):
    monkeypatch.setenv("ONRAMP_MOONPAY_WEBHOOK_KEY", "wk_test_x")
    get_settings.cache_clear()
    seed_legion(client, vault=VAULT)
    sid = client.post("/onboard/session", json={"legion": "lee-semis", "amount_usd": 100, "provider": "manual", "wallet": WALLET, "region": "DE"}).json()["session_id"]
    r = _moonpay_post(client, "wk_test_x", {"type": "transaction_failed", "data": {"status": "failed", "externalTransactionId": sid}})
    assert r.json()["session_status"] == "failed"
    assert client.get(f"/onboard/session/{sid}").json()["status"] == "failed"


def test_moonpay_webhook_rejects_signed_garbage_and_never_unstakes(client, monkeypatch):
    import hashlib
    import hmac
    import time
    monkeypatch.setenv("ONRAMP_MOONPAY_WEBHOOK_KEY", "wk_test_x")
    get_settings.cache_clear()
    t = str(int(time.time()))
    for body in (b"not json", b"[1, 2]"):
        sig = hmac.new(b"wk_test_x", t.encode() + b"." + body, hashlib.sha256).hexdigest()
        r = client.post("/onboard/webhooks/moonpay", content=body, headers={"Moonpay-Signature-V2": f"t={t},s={sig}"})
        assert r.status_code == 400, body
    assert client.post("/onboard/webhooks/moonpay", content=b"{}", headers={"Moonpay-Signature-V2": "garbage"}).status_code == 401
    seed_legion(client, vault=VAULT)
    sid = client.post("/onboard/session", json={"legion": "lee-semis", "amount_usd": 100, "provider": "manual", "wallet": WALLET, "region": "DE"}).json()["session_id"]
    client.post(f"/onboard/session/{sid}/staked", json={"tx": "0xfeed"})
    done = {"type": "transaction_updated", "data": {"status": "completed", "externalTransactionId": sid, "quoteCurrencyAmount": 1}}
    assert _moonpay_post(client, "wk_test_x", done).json()["session_status"] == "staked"
