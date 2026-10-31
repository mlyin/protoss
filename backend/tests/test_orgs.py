import os

import pytest

os.environ.setdefault("ARENA_MODE", "sim")
os.environ["TICK_SECONDS"] = "0"
os.environ["ADMIN_TOKEN"] = "test-admin"

from fastapi.testclient import TestClient  # noqa: E402

from app import db as dbmod  # noqa: E402
from app import hl  # noqa: E402
from app.config import get_settings  # noqa: E402

ADMIN = {"x-admin-token": "test-admin"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # TEST_DATABASE_URL=postgresql+psycopg://... runs the same suite against Postgres (fresh schema per test)
    pg = os.environ.get("TEST_DATABASE_URL")
    monkeypatch.setenv("DATABASE_URL", pg or f"sqlite:///{tmp_path}/t.db")
    get_settings.cache_clear()
    dbmod.reset_engine_for_tests()
    if pg:
        from sqlalchemy import text
        with dbmod.engine().begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    hl.set_exchange_for_tests(hl.SimExchange(get_settings(), seed=3))
    from app.main import app

    with TestClient(app) as c:
        yield c
    hl.set_exchange_for_tests(None)


def make_org(c, **kw):
    body = {
        "name": "Lee's Semis Phalanx",
        "slug": "lee-semis",
        "leader": "lee",
        "mandate": "Trade BTC and ETH perps on momentum. Never above 3x. Stop everything at 12% drawdown.",
        "limits": {"max_leverage": 3, "max_notional_usd": 60_000, "drawdown_flatten_pct": 12, "allowed_markets": ["BTC", "ETH"]},
        "initial_deposit": 1_000,
    }
    body.update(kw)
    r = c.post("/admin/orgs", json=body, headers=ADMIN)
    assert r.status_code == 201, r.text
    j = r.json()
    return j, {"authorization": f"Bearer {j['org_key']}"}


def add_member(c, org_h, name="exec-1", allocation=5_000, **limits):
    r = c.post("/orgs/lee-semis/agents", json={"name": name, "allocation_usd": allocation, "strategy": "test", "limits": limits}, headers=org_h)
    assert r.status_code == 201, r.text
    j = r.json()
    return j, {"authorization": f"Bearer {j['agent_key']}"}


def test_deposits_pool_and_shares(client):
    org, org_h = make_org(client)
    assert org["pool_cash"] == 1_000 and org["depositors"] == 1
    r = client.post("/orgs/lee-semis/deposit", json={"depositor": "matthew", "amount_usd": 100}).json()
    r = client.post("/orgs/lee-semis/deposit", json={"depositor": "sam", "amount_usd": 100}).json()
    assert r["pool_cash"] == 1_200
    shares = {s["depositor"]: s for s in r["shares"]}
    assert abs(shares["lee"]["share_pct"] - 83.33) < 0.01 and abs(shares["sam"]["share_pct"] - 8.33) < 0.01
    # cannot withdraw more than the unallocated pool
    assert client.post("/orgs/lee-semis/deposit", json={"depositor": "sam", "amount_usd": -5_000}).status_code == 422


def test_member_allocation_and_nested_limits(client):
    org, org_h = make_org(client)
    client.post("/orgs/lee-semis/deposit", json={"depositor": "matthew", "amount_usd": 9_000})
    # member asks for 10x but the mandate says 3x: the member is created at 3x
    m, agent_h = add_member(client, org_h, allocation=5_000, max_leverage=10)
    assert m["limits"]["max_leverage"] == 3 and m["allocation_usd"] == 5_000
    assert client.get("/orgs/lee-semis").json()["pool_cash"] == 5_000
    # a member cannot be given a market outside the mandate
    r = client.post("/orgs/lee-semis/agents", json={"name": "rogue", "allocation_usd": 1_000, "limits": {"allowed_markets": ["SOL"]}}, headers=org_h)
    assert r.status_code == 422
    # the agent key cannot touch the mandate
    assert client.put("/orgs/lee-semis/mandate", json={"max_leverage": 20}, headers=agent_h).status_code == 403
    # mandate notional (60k) binds before the agent's own cap when two members both load up
    _, agent2_h = add_member(client, org_h, name="exec-2", allocation=5_000)
    r1 = client.post("/v1/orders", json={"market": "BTC", "side": "buy", "size": 1}, headers=agent_h).json()
    assert r1["verdict"] == "resized" and "leverage" in r1["verdict_reason"]  # 5k * 3x = 15k of BTC max for this agent
    r2 = client.post("/v1/orders", json={"market": "ETH", "side": "buy", "size": 20}, headers=agent2_h).json()
    assert r2["verdict"] in ("approved", "resized")
    detail = client.get("/orgs/lee-semis").json()
    assert detail["members"] == 2 and len(detail["decisions"]) >= 2


def test_org_mandate_binds_tighter_than_agent(client):
    org, org_h = make_org(client, limits={"max_leverage": 1, "max_notional_usd": 60_000, "drawdown_flatten_pct": 12, "allowed_markets": ["BTC", "ETH"]})
    client.post("/orgs/lee-semis/deposit", json={"depositor": "matthew", "amount_usd": 9_000})
    _, agent_h = add_member(client, org_h, allocation=5_000)
    # org equity 10k at 1x = 10k notional; the agent alone (5k at 1x) would allow 5k; ask for 9k of BTC
    marks = client.get("/v1/markets").json()["markets"]
    size = 9_000 / marks["BTC"]
    r = client.post("/v1/orders", json={"market": "BTC", "side": "buy", "size": size}, headers=agent_h).json()
    assert r["verdict"] == "resized" and r["resized_to"] < size


def test_org_drawdown_flattens_everyone(client):
    org, org_h = make_org(client, limits={"max_leverage": 5, "max_notional_usd": 200_000, "drawdown_flatten_pct": 8, "allowed_markets": ["BTC", "ETH"]})
    client.post("/orgs/lee-semis/deposit", json={"depositor": "matthew", "amount_usd": 9_000})
    _, a1 = add_member(client, org_h, name="m1", allocation=5_000, drawdown_flatten_pct=50)
    _, a2 = add_member(client, org_h, name="m2", allocation=5_000, drawdown_flatten_pct=50)
    client.post("/v1/orders", json={"market": "BTC", "side": "buy", "size": 0.2}, headers=a1)  # ~4.5x on m1
    client.post("/v1/orders", json={"market": "ETH", "side": "buy", "size": 1}, headers=a2)  # small on m2
    hl.get_exchange().shock("BTC", -0.06)  # m1 loses ~27%, org loses ~13% -> org cap (8%) hit, member caps (50%) not
    out = client.post("/admin/tick", headers=ADMIN).json()
    assert out["halted_orgs"] == ["lee-semis"]
    d = client.get("/orgs/lee-semis").json()
    assert d["status"] == "halted" and all(m["status"] == "halted" for m in d["members_detail"])
    assert client.get("/v1/positions", headers=a2).json() == []  # the innocent member was flattened too: the mandate is org-wide
    # leader resumes everyone with one call
    assert client.post("/orgs/lee-semis/resume", headers=org_h).json()["status"] == "live"
    assert client.get("/v1/me", headers=a2).json()["status"] == "live"


def test_org_kill_switch_is_owner_only(client):
    org, org_h = make_org(client)
    _, agent_h = add_member(client, org_h, allocation=500)
    assert client.post("/orgs/lee-semis/halt", headers=agent_h).status_code == 403
    assert client.post("/orgs/lee-semis/halt", headers=org_h).json()["status"] == "halted"
    assert client.get("/orgs").json()[0]["status"] == "halted"
