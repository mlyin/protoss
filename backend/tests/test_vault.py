"""A legion backed by a Hyperliquid vault: the API shape, the deposit lock, and the adapter's account routing."""
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
VAULT = "0x" + "ab" * 20


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


def make_org(c):
    j = c.post("/admin/orgs", json={"name": "Lee's Legion", "slug": "lee", "leader": "lee", "initial_deposit": 500,
                                    "mandate": "Trade BTC and ETH on momentum. Never above 3x. Stop at 12% drawdown.",
                                    "limits": {"max_leverage": 3, "allowed_markets": ["BTC", "ETH"]}}, headers=ADMIN).json()
    return j, {"authorization": f"Bearer {j['org_key']}"}


def test_vault_backs_a_legion_and_locks_api_deposits(client):
    org, h = make_org(client)
    assert client.get("/orgs/lee").json()["hl_vault"] is None
    assert client.put("/orgs/lee/vault", json={"address": "not-an-address"}, headers=h).status_code == 422
    assert client.put("/orgs/lee/vault", json={"address": VAULT}).status_code == 401  # owner only
    r = client.put("/orgs/lee/vault", json={"address": VAULT}, headers=h)
    assert r.status_code == 200 and r.json()["hl_vault"] == VAULT
    d = client.get("/orgs/lee").json()
    assert d["hl_vault"] == VAULT and d["vault"] is None  # sim exchange knows nothing about vaults
    r = client.post("/orgs/lee/deposit", json={"depositor": "sam", "amount_usd": 100})
    assert r.status_code == 409 and VAULT in r.json()["detail"]


class FakeInfo:
    def __init__(self):
        self.calls = []

    def post(self, path, body):
        self.calls.append(body)
        return {"leader": "0xMASTER", "name": "Lee's Legion", "followers": [{"user": "0xsam", "vaultEquity": "120.5", "pnl": "20.5", "allTimePnl": "20.5", "daysFollowing": 3}]}

    def user_state(self, address, dex=""):
        return {"marginSummary": {"accountValue": "1000"}, "assetPositions": []}


class Org:
    def __init__(self, vault):
        self.hl_vault = vault


class DB:
    def __init__(self, org):
        self.org = org

    def get(self, model, key):
        return self.org


class Agent:
    org_id = "org1"
    hl_subaccount = "0xsub"


def test_adapter_routes_vault_members_to_the_vault_account():
    ex = hl.TestnetExchange.__new__(hl.TestnetExchange)
    ex.info = FakeInfo()
    ex._dexs = [""]
    assert ex._account_for(DB(Org(VAULT)), Agent()) == VAULT
    assert ex._account_for(DB(Org(None)), Agent()) == "0xsub"
    assert ex.equity(DB(Org(VAULT)), Agent()) == 1000.0
    assert ex.vault_details(VAULT)["followers"][0]["user"] == "0xsam"
