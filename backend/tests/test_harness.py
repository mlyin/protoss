"""The harness's pure parts: gate tiers by undo cost, feedback that converges, loop exits."""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))

gate = importlib.import_module("gate")
feedback = importlib.import_module("feedback")


def test_gate_prices_the_undo_not_the_confidence():
    g = gate.load_gates(ROOT / "harness" / "graph.yaml")
    assert gate.gate(["docs/index.html"], g).tier == "one_click_undo"
    assert gate.gate(["web/src/App.jsx", "brand/copy.md"], g).requires == ["green"]
    v = gate.gate(["web/src/App.jsx", "backend/app/risk.py"], g)
    assert v.tier == "cleanup_undo" and "review" in v.requires
    v = gate.gate(["backend/app/risk.py", "backend/migrations/0003_x.sql"], g)
    assert v.tier == "no_undo" and v.human_required
    # an unlisted path is treated as cleanup, never as free
    assert gate.gate(["mystery/thing.py"], g).tier == "cleanup_undo"
    assert gate.gate([], g).tier == "one_click_undo"


RED = """CHECK tests FAIL  EXPECTED pytest exit 0  SAW FAILED tests/test_lab.py::test_dca - assert 1 == 12;
CHECK voice ok
RESULT RED fails=1
"""
GREEN = "CHECK tests ok\nCHECK voice ok\nRESULT GREEN fails=0\n"


def test_feedback_turns_a_verdict_into_a_direction():
    fb = feedback.build(RED, fence="backend/app/backtest.py")
    assert not fb.green and fb.failures[0]["name"] == "tests"
    text = fb.render()
    assert "EXPECTED pytest exit 0" in text and "SAW FAILED tests/test_lab.py::test_dca" in text and "FENCE backend/app/backtest.py" in text
    assert fb.exit is None  # first failure: keep looping


def test_same_saw_twice_escalates_and_dead_ends_are_remembered():
    first = feedback.build(RED)
    attempts = [{"signature": feedback.signature(first.failures), "summary": "counted closes instead of buys", "failures": first.failures}]
    fb = feedback.build(RED, attempts=attempts)
    assert fb.exit and fb.exit.startswith("escalate: same result twice")
    assert "counted closes instead of buys" in fb.render()


def test_budget_exit_and_green():
    attempts = [{"signature": "x", "summary": f"try {i}", "failures": []} for i in range(3)]
    fb = feedback.build(RED, attempts=attempts, max_attempts=4)
    assert fb.exit == "escalate: budget spent"
    assert feedback.build(GREEN).green and feedback.build(GREEN).exit == "done"
