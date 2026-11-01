"""Publish dated research from real Hyperliquid candles without mixing old charts and new results.

    python scripts/idea_snapshots.py

All studies and images are prepared before publishing. Content-addressed images are written first;
the manifest is replaced last. A failed study leaves the previous public snapshot intact.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("ARENA_MODE", "paper")

from app.backtest import get_source, load_events, run_backtest  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.huddle import _test_summary, _verdict  # noqa: E402
from app.lab import Clarify, EXAMPLES, plan, theme  # noqa: E402
from app.share import card_png  # noqa: E402

IDS = ["hacks", "robots", "anthropic", "dwarkesh"]
OUT = ROOT / "web" / "public" / "ideas"
METHODOLOGY = 2  # completed history, publication-aware event entries, full holds, visible caveats


def prepare(src, now=None):
    if src.name != "hyperliquid":
        raise ValueError("Hyperliquid is unreachable: no snapshot written")
    now = now or dt.datetime.now(dt.timezone.utc)
    rows, assets = [], {}
    known = set(src.markets())
    for n, (idea_id, said) in enumerate(zip(IDS, EXAMPLES), 1):
        spec = plan(said, known=known)
        if isinstance(spec, Clarify):
            rows.append({"id": idea_id, "said": said, "status": "needs_research", "why": spec.question})
            continue
        res = run_backtest(spec, src, now=now)
        s = _test_summary(spec, res)
        coverage = s.get("coverage") or {}
        if not s.get("real") or coverage.get("source") != "historical" or coverage.get("contiguous") is not True:
            raise ValueError(f"{idea_id}: verified historical coverage is unavailable")
        if spec.type == "event_buy" and not (s.get("events") or {}).get("observations"):
            raise ValueError(f"{idea_id}: publication-aware event observations are unavailable")
        verdict = _verdict(SimpleNamespace(n=n, text=said, label=res.label, spec=spec.model_dump(mode="json")), s)
        card = {"n": n, "author": "", "label": res.label, "test": s, "kind": "rule", "status": "proposed",
                "outcome": None, "pledged_usd": None, "record": {"closed": 0, "up": 0, "pnl_usd": 0}, "backers": []}
        images = {}
        for key, phone in (("desktop", False), ("phone", True)):
            data = card_png(card, phone=phone)
            name = f"{idea_id}-{key}-{hashlib.sha256(data).hexdigest()[:16]}.png"
            assets[name] = data
            images[key] = name
        names: dict[str, list[str]] = {}
        if s.get("event_set") in ("major_hacks", "dwarkesh"):
            for r in load_events(s["event_set"]):
                names.setdefault(r["date"].isoformat(), []).append(r.get("company") or r.get("title") or "")
        events = [{"date": d, "move_pct": m, "what": " / ".join(names.get(d, []))} for d, m in ((s.get("events") or {}).get("per_event") or [])]
        rows.append({"id": idea_id, "said": said, "label": res.label, "why": (theme(said) or (None, ""))[1], "verdict": verdict,
                     "market": s["market"], "start": s["start"], "end": s["end"], "hold_days": s.get("hold_days"), "events": events,
                     "notes": s["notes"], "coverage": coverage, "images": images,
                     "observations": (s.get("events") or {}).get("observations", [])})
    as_of = now.isoformat(timespec="minutes")
    return {"methodology": METHODOLOGY, "as_of": as_of, "source": "Hyperliquid candles, fees and slippage included, funding not", "ideas": rows}, assets


def atomic_write(path, data):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temp = Path(handle.name)
        handle.write(data)
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def publish(src, out=OUT):
    manifest, assets = prepare(src)  # No writes if any study fails.
    out.mkdir(parents=True, exist_ok=True)
    for name, data in assets.items():
        atomic_write(out / name, data)
    atomic_write(out / "ideas.json", (json.dumps(manifest, indent=1) + "\n").encode())
    # Retired unversioned cards must not continue advertising a different strategy.
    for idea_id in IDS:
        for suffix in (".png", "-phone.png"):
            (out / f"{idea_id}{suffix}").unlink(missing_ok=True)
    return manifest


def main():
    manifest = publish(get_source(get_settings()))
    for row in manifest["ideas"]:
        print(f"{row['id']}: {row.get('label') or row['status']}")
    print(f"wrote {OUT.relative_to(ROOT)} as of {manifest['as_of']}")


if __name__ == "__main__":
    main()
