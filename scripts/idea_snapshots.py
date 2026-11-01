"""Run the four demo ideas on live Hyperliquid data and write what the website shows before anyone asks:
web/public/ideas/ideas.json (verdicts, events, dates) and web/public/ideas/<id>.png (the card the Telegram bot posts).

    python scripts/idea_snapshots.py

Refuses to write anything when Hyperliquid is unreachable: the site never shows simulated numbers.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("ARENA_MODE", "paper")  # paper = real Hyperliquid prices, no orders

from app.backtest import get_source, load_events, run_backtest  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.huddle import _test_summary, _verdict  # noqa: E402
from app.lab import EXAMPLES, plan, theme  # noqa: E402
from app.share import card_png  # noqa: E402

IDS = ["hacks", "robots", "anthropic", "dwarkesh"]  # same order as lab.EXAMPLES
OUT = ROOT / "web" / "public" / "ideas"


def main() -> None:
    src = get_source(get_settings())
    if src.name != "hyperliquid":
        sys.exit("Hyperliquid is unreachable: no snapshot written")
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for n, (idea_id, said) in enumerate(zip(IDS, EXAMPLES), 1):
        spec = plan(said, known=set(src.markets()))
        res = run_backtest(spec, src)
        s = _test_summary(spec, res)
        verdict = _verdict(SimpleNamespace(n=n, text=said, label=res.label, spec=spec.model_dump(mode="json")), s)
        (OUT / f"{idea_id}.png").write_bytes(card_png({"n": n, "author": "", "label": res.label, "test": s, "kind": "rule", "status": "proposed",
                                                       "outcome": None, "pledged_usd": None, "record": {"closed": 0, "up": 0, "pnl_usd": 0}, "backers": []}))
        names: dict[str, list[str]] = {}
        if s.get("event_set") in ("major_hacks", "dwarkesh"):
            for r in load_events(s["event_set"]):
                names.setdefault(r["date"].isoformat(), []).append(r.get("company") or r.get("title") or "")
        events = [{"date": d, "move_pct": m, "what": " / ".join(names.get(d, []))} for d, m in ((s.get("events") or {}).get("per_event") or [])]
        rows.append({"id": idea_id, "said": said, "label": res.label, "why": (theme(said) or (None, ""))[1], "verdict": verdict,
                     "market": s["market"], "start": s["start"], "end": s["end"], "hold_days": s.get("hold_days"), "events": events})
        print(f"{idea_id}: {res.label} | {verdict[0][:90]}")
    as_of = dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")
    (OUT / "ideas.json").write_text(json.dumps({"as_of": as_of, "source": "Hyperliquid candles, fees and slippage included, funding not", "ideas": rows}, indent=1) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)} as of {as_of}")


if __name__ == "__main__":
    main()
