#!/usr/bin/env python3
"""Cross-platform demo: start the API in sim mode, create two standalone agents and a sample koinon,
run the bots, open the leaderboard in a browser. Ctrl-C stops everything.

    python scripts/demo.py              # runs until Ctrl-C
    python scripts/demo.py --duration 120
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = "http://localhost:8000"
ADMIN = os.environ.get("ADMIN_TOKEN", "demo-admin")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration", type=float, default=None)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    try:
        import httpx
    except ImportError:
        sys.exit("pip install -r requirements.txt first")

    for f in ("demo.db", "demo.db-wal", "demo.db-shm"):
        try:
            (ROOT / f).unlink()
        except FileNotFoundError:
            pass

    env = dict(
        os.environ,
        ARENA_MODE=os.environ.get("ARENA_MODE", "sim"),
        ADMIN_TOKEN=ADMIN,
        DATABASE_URL=f"sqlite:///{(ROOT / 'demo.db').as_posix()}",
        TICK_SECONDS=os.environ.get("TICK_SECONDS", "2"),
        SNAPSHOT_SECONDS=os.environ.get("SNAPSHOT_SECONDS", "10"),
        ARENA_URL=API,
        PYTHONPATH=str(ROOT / "sdk") + os.pathsep + os.environ.get("PYTHONPATH", ""),
    )
    procs: list[subprocess.Popen] = []
    api = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", "8000", "--log-level", "warning"], cwd=ROOT / "backend", env=env)
    procs.append(api)

    def stop(*_, code: int = 0):
        for p in procs:
            try:
                p.terminate()
            except Exception:
                pass
        sys.exit(code)

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    c = httpx.Client(base_url=API, timeout=10)
    for _ in range(60):
        try:
            if c.get("/health").status_code == 200:
                break
        except Exception:
            time.sleep(0.5)
        if api.poll() is not None:
            break
    else:
        print("API did not come up on port 8000 (is something else using it?)")
        stop(code=1)
    if api.poll() is not None:
        print("API process exited early; scroll up for the error.")
        stop(code=1)

    H = {"x-admin-token": ADMIN}

    def agent(name, owner, markets, **limits):
        r = c.post("/admin/agents", json={"name": name, "owner": owner, "starting_equity": 10_000, "limits": {"allowed_markets": markets, **limits}}, headers=H)
        r.raise_for_status()
        return r.json()["agent_key"]

    def bot(script, key, **extra):
        e = dict(env, ARENA_API_KEY=key, INTERVAL="2", **{k: str(v) for k, v in extra.items()})
        procs.append(subprocess.Popen([sys.executable, str(ROOT / "agents" / script)], env=e, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))

    # two standalone agents
    bot("momentum.py", agent("momentum-7", "quantbros", ["BTC", "ETH"]))
    bot("meanrev.py", agent("meanrev-owl", "0xlena", ["ETH", "SOL", "HYPE"]))

    # a sample koinon: Lee's mandate, two agents inside it, three friends deposited
    org = c.post("/admin/orgs", json={
        "name": "Lee's Semis Koinon", "slug": "lee-semis", "leader": "lee", "initial_deposit": 1000, "profit_share_pct": 10,
        "mandate": "Memory and AI chips are mispriced vs demand. Trade xyz:NVDA and xyz:SP500 perps plus BTC as a hedge. Never above 3x. Stop everything at 12% drawdown.",
        "limits": {"max_leverage": 3, "max_notional_usd": 40000, "drawdown_flatten_pct": 12, "daily_loss_pct": 5, "allowed_markets": ["xyz:NVDA", "xyz:SP500", "BTC"]},
    }, headers=H)
    org.raise_for_status()
    ok = {"authorization": f"Bearer {org.json()['org_key']}"}
    for who in ("matthew", "sam", "priya"):
        c.post("/orgs/lee-semis/deposit", json={"depositor": who, "amount_usd": 100})
    m1 = c.post("/orgs/lee-semis/agents", json={"name": "lee-momentum", "allocation_usd": 800, "strategy": "Crossover on NVDA + SP500 inside Lee's mandate", "limits": {"max_leverage": 3}}, headers=ok).json()
    m2 = c.post("/orgs/lee-semis/agents", json={"name": "lee-hedge", "allocation_usd": 400, "strategy": "Mean-reversion BTC hedge leg", "limits": {"max_leverage": 2}}, headers=ok).json()
    bot("momentum.py", m1["agent_key"], MARKETS="xyz:NVDA,xyz:SP500", RISK_FRACTION="0.8")
    bot("meanrev.py", m2["agent_key"], MARKETS="BTC", RISK_FRACTION="0.5")

    print(f"\nKoinon demo is up: {API}   (API docs: {API}/docs)\nCtrl-C to stop.\n")
    if not args.no_browser:
        webbrowser.open(API)

    t0 = time.time()
    while args.duration is None or time.time() - t0 < args.duration:
        time.sleep(1)
        if api.poll() is not None:
            print("API exited")
            break
    stop()


if __name__ == "__main__":
    main()
