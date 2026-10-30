import os

import pytest

os.environ.setdefault("ARENA_MODE", "sim")
os.environ["TICK_SECONDS"] = "0"  # no background loop in tests
os.environ["ADMIN_TOKEN"] = "test-admin"

from fastapi.testclient import TestClient  # noqa: E402

from app import db as dbmod  # noqa: E402
from app import hl  # noqa: E402
from app.config import get_settings  # noqa: E402

ADMIN = {"x-admin-token": "test-admin"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    get_settings.cache_clear()
    dbmod.reset_engine_for_tests()
    hl.set_exchange_for_tests(hl.SimExchange(get_settings(), seed=7))
    from app.main import app

    with TestClient(app) as c:
        yield c
    hl.set_exchange_for_tests(None)


def make_agent(c, name="a1", **limits):
    r = c.post("/admin/agents", json={"name": name, "owner": "tester", "starting_equity": 10_000, "limits": {"allowed_markets": ["BTC", "ETH", "xyz:NVDA"], **limits}}, headers=ADMIN)
    assert r.status_code == 201, r.text
    j = r.json()
    return j, {"authorization": f"Bearer {j['agent_key']}"}, {"authorization": f"Bearer {j['owner_key']}"}


def test_create_requires_admin(client):
    assert client.post("/admin/agents", json={"name": "x", "owner": "y"}).status_code == 403


def test_order_flow_and_ledger(client):
    _, agent, owner = make_agent(client)
    r = client.post("/v1/orders", json={"market": "BTC", "side": "buy", "size": 0.1, "reason": "test"}, headers=agent).json()
    assert r["verdict"] == "approved" and r["filled_size"] == 0.1 and r["builder_fee_usd"] > 0
    me = client.get("/v1/me", headers=agent).json()
    assert me["leverage"] > 1.0 and me["equity"] < 10_000  # fees and slippage paid
    pos = client.get("/v1/positions", headers=agent).json()
    assert pos[0]["market"] == "BTC" and pos[0]["size"] == 0.1
    # close half: realized pnl recorded
    r = client.post("/v1/orders", json={"market": "BTC", "side": "sell", "size": 0.05}, headers=agent).json()
    assert r["verdict"] == "approved" and r["realized_pnl_usd"] != 0


def test_sandbox_resizes_and_rejects(client):
    _, agent, _ = make_agent(client)
    r = client.post("/v1/orders", json={"market": "BTC", "side": "buy", "size": 10}, headers=agent).json()
    assert r["verdict"] == "resized" and r["resized_to"] < 10 and r["filled_size"] == r["resized_to"]
    r = client.post("/v1/orders", json={"market": "SOL", "side": "buy", "size": 1}, headers=agent).json()
    assert r["verdict"] == "rejected" and r["filled_size"] == 0


def test_agent_key_cannot_change_limits(client):
    _, agent, owner = make_agent(client)
    assert client.put("/v1/limits", json={"max_leverage": 50}, headers=agent).status_code == 403
    assert client.put("/v1/limits", json={"max_leverage": 2}, headers=owner).json()["max_leverage"] == 2
    assert client.put("/v1/limits", json={"allowed_markets": ["NOPE"]}, headers=owner).status_code == 422


def test_drawdown_flattens_and_halts(client):
    _, agent, owner = make_agent(client, drawdown_flatten_pct=10)
    client.post("/v1/orders", json={"market": "BTC", "side": "buy", "size": 0.4}, headers=agent)  # ~4.5x
    ex = hl.get_exchange()
    ex.shock("BTC", -0.05)  # 5% drop on 4.5x = ~22% drawdown
    out = client.post("/admin/tick", headers=ADMIN).json()
    assert out["halted"] == ["a1"]
    me = client.get("/v1/me", headers=agent).json()
    assert me["status"] == "halted" and "drawdown" in me["halted_reason"]
    assert client.get("/v1/positions", headers=agent).json() == []
    r = client.post("/v1/orders", json={"market": "BTC", "side": "buy", "size": 0.1}, headers=agent).json()
    assert r["verdict"] == "rejected" and "halted" in r["verdict_reason"]
    # owner can resume
    assert client.post("/v1/resume", headers=owner).json()["status"] == "live"


def test_kill_switch_is_owner_only(client):
    _, agent, owner = make_agent(client)
    client.post("/v1/orders", json={"market": "ETH", "side": "buy", "size": 1}, headers=agent)
    assert client.post("/v1/flatten", headers=agent).status_code == 403
    assert client.post("/v1/flatten", headers=owner).json()["status"] == "halted"


def test_leaderboard_and_public_endpoints(client):
    make_agent(client, "alpha")
    make_agent(client, "beta")
    client.post("/admin/tick", headers=ADMIN)
    lb = client.get("/leaderboard").json()
    assert lb["mode"] == "sim" and len(lb["agents"]) == 2 and lb["agents"][0]["rank"] == 1
    detail = client.get("/agents/alpha").json()
    assert detail["metrics"]["name"] == "alpha" and "limits" in detail
    assert client.get("/stats").json()["agents_total"] == 2
    assert isinstance(client.get("/fills").json(), list)
