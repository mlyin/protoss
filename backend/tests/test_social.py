"""Profiles, follows and the derived activity feed."""
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
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    get_settings.cache_clear()
    dbmod.reset_engine_for_tests()
    hl.set_exchange_for_tests(hl.SimExchange(get_settings(), seed=5))
    from app.main import app

    with TestClient(app) as c:
        yield c
    hl.set_exchange_for_tests(None)


def seed(c):
    org = c.post("/admin/orgs", json={
        "name": "Lee's Semis Legion", "slug": "lee-semis", "leader": "lee", "initial_deposit": 1_000,
        "mandate": "Trade BTC and ETH perps on momentum. Never above 3x. Stop everything at 12% drawdown.",
        "limits": {"max_leverage": 3, "max_notional_usd": 60_000, "drawdown_flatten_pct": 12, "allowed_markets": ["BTC", "ETH"]},
    }, headers=ADMIN).json()
    org_h = {"authorization": f"Bearer {org['org_key']}"}
    c.post("/orgs/lee-semis/deposit", json={"depositor": "matthew", "amount_usd": 100})
    m = c.post("/orgs/lee-semis/agents", json={"name": "lee-exec", "allocation_usd": 800, "strategy": "crossover", "limits": {"max_leverage": 3}}, headers=org_h).json()
    m_h = {"authorization": f"Bearer {m['agent_key']}"}
    solo = c.post("/admin/agents", json={"name": "solo-bot", "owner": "priya", "starting_equity": 10_000, "limits": {"allowed_markets": ["BTC"]}}, headers=ADMIN).json()
    s_h = {"authorization": f"Bearer {solo['agent_key']}"}
    r = c.post("/v1/orders", json={"market": "BTC", "side": "buy", "size": 0.01, "order_type": "market", "reason": "test fill"}, headers=m_h)
    assert r.status_code == 201, r.text
    r = c.post("/v1/orders", json={"market": "SOL", "side": "buy", "size": 1, "order_type": "market"}, headers=m_h)  # outside the mandate
    assert r.json()["verdict"] == "rejected"
    c.post("/v1/orders", json={"market": "BTC", "side": "buy", "size": 0.02, "order_type": "market"}, headers=s_h)
    return org, m, solo


def test_feed_merges_ledger_newest_first(client):
    seed(client)
    feed = client.get("/feed").json()
    kinds = {i["kind"] for i in feed}
    assert {"fill", "reject", "deposit", "new_org", "new_agent"} <= kinds
    assert feed == sorted(feed, key=lambda i: i["ts"], reverse=True)
    fill = next(i for i in feed if i["kind"] == "fill" and i["actor"] == "lee-exec")
    assert fill["org_slug"] == "lee-semis" and fill["market"] == "BTC" and "test fill" in fill["text"]
    rej = next(i for i in feed if i["kind"] == "reject")
    assert "SOL" in rej["text"]


def test_profile_shows_stakes_and_value(client):
    seed(client)
    p = client.get("/u/matthew").json()
    assert p["total_deposited"] == 100 and len(p["stakes"]) == 1
    assert p["stakes"][0]["org"] == "lee-semis" and 0 < p["stakes"][0]["share_pct"] < 20
    assert client.get("/u/nobody-here").status_code == 404
    lead = client.get("/u/lee").json()
    assert lead["leads"][0]["slug"] == "lee-semis"
    owner = client.get("/u/priya").json()
    assert owner["agents"][0]["name"] == "solo-bot"


def test_follow_filters_the_feed(client):
    org, m, solo = seed(client)
    assert client.post("/social/profiles", json={"handle": "sam", "display_name": "Sam"}).status_code == 201
    assert client.post("/social/profiles", json={"handle": "sam", "display_name": "Sam"}).status_code == 409
    # sam follows only the solo bot: feed has solo's fill, nothing from the legion
    assert client.post("/social/follow", json={"handle": "sam", "target_type": "agent", "target_id": solo["id"]}).status_code == 201
    feed = client.get("/feed", params={"handle": "sam"}).json()
    assert feed and all(i["org_slug"] is None for i in feed)
    assert any(i["kind"] == "fill" and i["actor"] == "solo-bot" for i in feed)
    # now follow the legion too
    client.post("/social/follow", json={"handle": "sam", "target_type": "org", "target_id": "lee-semis"})
    feed = client.get("/feed", params={"handle": "sam"}).json()
    assert any(i["kind"] == "deposit" and i["org_slug"] == "lee-semis" for i in feed)
    assert client.get("/u/sam").json()["following"] == [{"type": "agent", "id": solo["id"]}, {"type": "org", "id": "lee-semis"}]
    client.request("DELETE", "/social/follow", json={"handle": "sam", "target_type": "org", "target_id": "lee-semis"})
    assert len(client.get("/u/sam").json()["following"]) == 1
    assert client.post("/social/follow", json={"handle": "sam", "target_type": "org", "target_id": "nope"}).status_code == 404
