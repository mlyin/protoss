"""Mainnet selection, signing boundaries and real-money API guards."""
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.config import Settings
from app import hl


def test_network_cannot_be_disguised_as_testnet():
    with pytest.raises(ValidationError, match="testnet requires"):
        Settings(arena_mode="testnet", hl_api_url="https://api.hyperliquid.xyz")
    with pytest.raises(ValidationError, match="configured ADMIN_TOKEN"):
        Settings(arena_mode="mainnet", admin_token="change-me")
    with pytest.raises(ValidationError, match="mainnet requires"):
        Settings(arena_mode="mainnet", admin_token="configured", hl_api_url="https://api.hyperliquid-testnet.xyz")


def test_mainnet_startup_does_not_sign(monkeypatch):
    import hyperliquid.info
    calls = []
    class Info:
        def __init__(self, url, **kwargs):
            calls.append(url)
        def all_mids(self, dex):
            return {"xyz:ANT": "111"}
        def post(self, path, body):
            assert body["type"] == "maxBuilderFee"
            return 0
    monkeypatch.setattr(hyperliquid.info, "Info", Info)
    def forbidden(*args, **kwargs):
        pytest.fail("startup tried to construct a signing exchange")
    monkeypatch.setattr(hl.TestnetExchange, "_exchange", forbidden)
    # A synthetic test key, never an account key.
    ex = hl.MainnetExchange(Settings(arena_mode="mainnet", admin_token="configured", hl_master_private_key="0x" + "1" * 64))
    assert calls == ["https://api.hyperliquid.xyz"]
    assert ex.mark("xyz:ANT") == 111
    assert ex.builder_warning


def test_mainnet_orders_disabled_by_default(monkeypatch):
    ex = hl.MainnetExchange.__new__(hl.MainnetExchange)
    ex.settings = SimpleNamespace(mainnet_trading_enabled=False)
    def forbidden(*args, **kwargs):
        pytest.fail("disabled mainnet tried to submit an order")
    monkeypatch.setattr(hl.TestnetExchange, "place", forbidden)
    with pytest.raises(RuntimeError, match="execution disabled"):
        ex.place(None, None, "xyz:ANT", "buy", 1, "market", None, False)


def test_mainnet_requires_vault_and_matching_leader():
    ex = hl.MainnetExchange.__new__(hl.MainnetExchange)
    agent = SimpleNamespace(id="a", org_id=None)
    with pytest.raises(ValueError, match="existing Hyperliquid vault"):
        ex.on_agent_created(None, agent)
    agent.org_id = "org"
    db = SimpleNamespace(get=lambda *args: SimpleNamespace(hl_vault="0xVAULT"), scalar=lambda query: None)
    ex.master = SimpleNamespace(address="0xOWNER")
    ex.vault_details = lambda vault: {"leader": "0xOTHER"}
    with pytest.raises(ValueError, match="leader"):
        ex.on_agent_created(db, agent)
    ex.vault_details = lambda vault: {"leader": "0xOWNER"}
    ex.on_agent_created(db, agent)  # registration performs no transfers or account creation
    db.scalar = lambda query: "another-agent"
    with pytest.raises(ValueError, match="one agent per vault"):
        ex.on_agent_created(db, agent)


def test_mainnet_huddle_requires_auth(monkeypatch):
    from app import huddle
    from fastapi import HTTPException
    monkeypatch.setattr(huddle, "get_settings", lambda: SimpleNamespace(arena_mode="mainnet", admin_token="configured"))
    with pytest.raises(HTTPException) as exc:
        huddle._guard(SimpleNamespace(is_web=True), None)
    assert exc.value.status_code == 403
    huddle._guard(SimpleNamespace(is_web=True), "configured")


def test_mainnet_read_failures_do_not_become_empty_accounts():
    ex = hl.MainnetExchange.__new__(hl.MainnetExchange)
    ex._dexs = ["", "xyz"]
    def unavailable(*args):
        raise RuntimeError("exchange unavailable")
    ex.info = SimpleNamespace(user_state=unavailable, all_mids=unavailable)
    with pytest.raises(RuntimeError, match="unavailable"):
        ex.account_equity("0xVAULT")
    with pytest.raises(RuntimeError, match="unavailable"):
        ex.tick()
