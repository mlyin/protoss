"""Market identity and actual-fill filtering for the read-only acceptance CLI."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("live_check", Path(__file__).resolve().parents[2] / "scripts/live_check.py")
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


def test_market_identity_and_delisting():
    data = [{"universe": [{"name": "xyz:ANT"}, {"name": "xyz:TSLA"}]}, [{"markPx": "111"}, {"markPx": "400"}]]
    assert check.market_snapshot("xyz:ANT", data)["context"]["markPx"] == "111"
    with pytest.raises(ValueError, match="not listed"):
        check.market_snapshot("xyz:ANTHROPIC", data)
    data[0]["universe"][0]["isDelisted"] = True
    with pytest.raises(ValueError, match="delisted"):
        check.market_snapshot("xyz:ANT", data)


def test_only_matching_recent_fills_count(monkeypatch):
    calls = []
    def info(body):
        calls.append(body)
        if body["type"] == "clearinghouseState":
            return {"assetPositions": [{"position": {"coin": "xyz:ANT", "szi": "1"}}]}
        return [{"coin": "xyz:ANT", "time": 100, "oid": 1},
                {"coin": "xyz:ANT", "time": 99, "oid": 2},
                {"coin": "xyz:TSLA", "time": 101, "oid": 3}]
    monkeypatch.setattr(check, "info", info)
    result = check.account_snapshot("0x" + "1" * 40, "xyz:ANT", 100)
    assert [f["oid"] for f in result["fills"]] == [1]
    assert calls[0]["dex"] == "xyz"
