"""Builder-code behaviour of the testnet adapter, exercised offline with fakes for the Hyperliquid SDK."""
import os

os.environ.setdefault("ARENA_MODE", "sim")
os.environ["ADMIN_TOKEN"] = "test-admin"

from app import hl  # noqa: E402
from app.config import get_settings  # noqa: E402


class FakeInfo:
    def __init__(self, approved):
        self.approved = approved
        self.calls = []

    def post(self, path, body):
        self.calls.append(body)
        if body["type"] == "maxBuilderFee":
            if isinstance(self.approved, Exception):
                raise self.approved
            return self.approved
        raise AssertionError(body)


class FakeExchange:
    def __init__(self, approve_result="ok", reject_builder=False):
        self.approve_result = approve_result
        self.reject_builder = reject_builder
        self.orders = []

    def approve_builder_fee(self, builder, max_fee_rate):
        self.last_approval = (builder, max_fee_rate)
        if isinstance(self.approve_result, Exception):
            raise self.approve_result
        return {"status": self.approve_result}

    def _resp(self, status):
        return {"status": "ok", "response": {"data": {"statuses": [status]}}}

    def market_open(self, market, is_buy, size, px, slippage, builder=None):
        self.orders.append(("open", market, is_buy, size, builder))
        if builder and self.reject_builder:
            return self._resp({"error": "Builder fee has not been approved"})
        return self._resp({"filled": {"avgPx": "100.0", "totalSz": str(size), "oid": 1}})

    def market_close(self, market, size, px, slippage, builder=None):
        self.orders.append(("close", market, None, size, builder))
        return self._resp({"filled": {"avgPx": "100.0", "totalSz": str(size), "oid": 2}})

    def order(self, *a, builder=None, **k):
        raise AssertionError("not used")


class Master:
    address = "0xmaster"


def make(approved, exchange: FakeExchange) -> hl.TestnetExchange:
    ex = hl.TestnetExchange.__new__(hl.TestnetExchange)
    ex.settings = get_settings()
    ex.master = Master()
    ex.builder = "0xbuilder"
    ex.info = FakeInfo(approved)
    ex._ex_cache = {None: exchange, "0xsub": exchange}
    ex.builder_warning = None
    return ex


class A:
    hl_subaccount = "0xsub"


def test_already_approved_means_no_new_signature():
    fx = FakeExchange()
    ex = make(approved=100, exchange=fx)
    ex.ensure_builder_approved()
    assert not hasattr(fx, "last_approval")
    assert ex.builder_warning is None
    assert ex._builder() == {"b": "0xbuilder", "f": get_settings().hl_builder_fee_tenths_bp}


def test_approves_when_missing_and_formats_rate():
    fx = FakeExchange()
    ex = make(approved=0, exchange=fx)
    ex.ensure_builder_approved()
    assert fx.last_approval == ("0xbuilder", "0.030%")  # 30 tenths of a bp
    assert ex.builder_warning is None


def test_approval_failure_is_not_fatal_and_orders_skip_builder():
    fx = FakeExchange(approve_result=RuntimeError("builder must have at least 100 USDC"))
    ex = make(approved=RuntimeError("down"), exchange=fx)
    ex.ensure_builder_approved()
    assert "not approved" in ex.builder_warning
    fill = ex.place(None, A(), "BTC", "buy", 0.5, "market", None, False)
    assert fx.orders[-1][4] is None  # sent without a builder code
    assert fill is not None and fill.builder_fee_usd == 0.0


def test_exchange_rejecting_builder_retries_without_it():
    fx = FakeExchange(reject_builder=True)
    ex = make(approved=100, exchange=fx)
    ex.ensure_builder_approved()
    fill = ex.place(None, A(), "ETH", "buy", 2, "market", None, False)
    assert [o[4] for o in fx.orders] == [{"b": "0xbuilder", "f": 30}, None]
    assert fill is not None and fill.size == 2 and fill.builder_fee_usd == 0.0
    assert "rejected builder code" in ex.builder_warning
    # and it stays off for the next order instead of failing every time
    ex.place(None, A(), "ETH", "sell", 2, "market", None, True)
    assert fx.orders[-1][4] is None
