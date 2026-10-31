#!/usr/bin/env python3
"""Run a fleet of bots from fleet.yaml.

    python scripts/fleet.py                 # register missing bots, apply limits, start all, stream logs
    python scripts/fleet.py --status        # one-line status per bot and exit
    python scripts/fleet.py --only momentum-btc meanrev-alts

Needs: pip install pyyaml httpx   (both already in requirements.txt)
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]
KEYS = ROOT / ".fleet-keys.json"
COLORS = ["\033[36m", "\033[32m", "\033[33m", "\033[35m", "\033[34m", "\033[91m", "\033[92m", "\033[93m"]
RESET = "\033[0m"


def load_cfg(path: Path) -> dict:
    cfg = yaml.safe_load(path.read_text())
    cfg["api"] = os.environ.get("ARENA_URL") or cfg.get("api") or "http://localhost:8000"
    cfg.setdefault("owner", "fleet")
    cfg.setdefault("starting_equity", 10_000)
    return cfg


def load_keys() -> dict:
    return json.loads(KEYS.read_text()) if KEYS.exists() else {}


def save_keys(keys: dict) -> None:
    KEYS.write_text(json.dumps(keys, indent=2))
    try:
        KEYS.chmod(0o600)
    except OSError:
        pass


def ensure_agent(client: httpx.Client, cfg: dict, bot: dict, keys: dict, admin: str) -> dict:
    if bot["name"] in keys:
        return keys[bot["name"]]
    body = {
        "name": bot["name"],
        "owner": bot.get("owner", cfg["owner"]),
        "runtime": bot.get("runtime", "Python SDK"),
        "strategy": bot.get("strategy"),
        "starting_equity": bot.get("starting_equity", cfg["starting_equity"]),
        "limits": dict(bot.get("limits", {}), allowed_markets=bot.get("markets")),
    }
    r = client.post("/admin/agents", json=body, headers={"x-admin-token": admin})
    if r.status_code == 409:
        sys.exit(f"{bot['name']} exists on the server but its keys are not in {KEYS.name}; delete it or restore the keys file")
    r.raise_for_status()
    j = r.json()
    keys[bot["name"]] = {"id": j["id"], "owner_key": j["owner_key"], "agent_key": j["agent_key"]}
    save_keys(keys)
    print(f"registered {bot['name']} ({j['id'][:8]})")
    return keys[bot["name"]]


def ensure_org(client: httpx.Client, org: dict, keys: dict, admin: str) -> dict:
    """Create a koinon (org) once and remember its owner key; on later runs just return the cached record."""
    orgs = keys.setdefault("orgs", {})
    if org["slug"] in orgs:
        return orgs[org["slug"]]
    body = {
        "name": org["name"],
        "slug": org["slug"],
        "leader": org["leader"],
        "mandate": org["mandate"],
        "limits": org.get("limits", {}),
        "profit_share_pct": org.get("profit_share_pct", 10),
        "initial_deposit": org.get("initial_deposit", 0),
    }
    r = client.post("/admin/orgs", json=body, headers={"x-admin-token": admin})
    if r.status_code == 409:
        sys.exit(f"org {org['slug']} exists on the server but its key is not in {KEYS.name}; delete it or restore the keys file")
    r.raise_for_status()
    j = r.json()
    orgs[org["slug"]] = {"id": j["id"], "org_key": j["org_key"], "members": {}}
    save_keys(keys)
    for who, amt in (org.get("deposits") or {}).items():
        d = client.post(f"/orgs/{org['slug']}/deposit", json={"depositor": who, "amount_usd": float(amt)})
        if d.status_code >= 400:
            print(f"  deposit {who} -> {org['slug']}: {d.status_code} {d.text}")
    print(f"created koinon {org['slug']} ({j['id'][:8]})")
    return orgs[org["slug"]]


def ensure_member(client: httpx.Client, org: dict, rec: dict, m: dict, keys: dict) -> dict:
    if m["name"] in rec["members"]:
        return rec["members"][m["name"]]
    body = {
        "name": m["name"],
        "runtime": m.get("runtime", "Python SDK"),
        "strategy": m.get("strategy"),
        "allocation_usd": m["allocation_usd"],
        "limits": dict(m.get("limits", {}), **({"allowed_markets": m["markets"]} if m.get("markets") else {})),
    }
    r = client.post(f"/orgs/{org['slug']}/agents", json=body, headers={"authorization": f"Bearer {rec['org_key']}"})
    if r.status_code == 409:
        sys.exit(f"{m['name']} exists on the server but its keys are not in {KEYS.name}")
    r.raise_for_status()
    j = r.json()
    rec["members"][m["name"]] = {"id": j["id"], "owner_key": j["owner_key"], "agent_key": j["agent_key"]}
    save_keys(keys)
    print(f"registered {m['name']} in {org['slug']} ({j['id'][:8]}, ${m['allocation_usd']:,.0f})")
    return rec["members"][m["name"]]


def apply_limits(client: httpx.Client, bot: dict, k: dict) -> None:
    lim = dict(bot.get("limits", {}))
    if bot.get("markets"):
        lim["allowed_markets"] = bot["markets"]
    if lim:
        r = client.put("/v1/limits", json=lim, headers={"authorization": f"Bearer {k['owner_key']}"})
        if r.status_code >= 400:
            print(f"  limits for {bot['name']}: {r.status_code} {r.text}")


def status(client: httpx.Client, runnables: list[tuple[dict, dict | None]]) -> None:
    for b, k in runnables:
        if not k:
            print(f"{b['name']:<20} not registered")
            continue
        me = client.get("/v1/me", headers={"authorization": f"Bearer {k['agent_key']}"}).json()
        flag = "live  " if me["status"] == "live" else "HALTED"
        org = me.get("org")
        org = f"[{org['slug'] if isinstance(org, dict) else org}] " if org else ""
        print(f"{b['name']:<20} {flag} equity {me['equity']:>10,.2f}  lev {me['leverage'] or 0:>5.2f}  {org}{me.get('halted_reason') or ''}")


def stream(name: str, proc: subprocess.Popen, color: str) -> None:
    assert proc.stdout is not None
    for line in proc.stdout:
        sys.stdout.write(f"{color}[{name}]{RESET} {line}")
        sys.stdout.flush()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "fleet.yaml"))
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--only", nargs="*", default=None)
    args = ap.parse_args()

    cfg = load_cfg(Path(args.config))
    bots = [b for b in cfg["bots"] if not args.only or b["name"] in args.only]
    admin = os.environ.get(cfg.get("admin_token_env", "ADMIN_TOKEN"), "change-me")
    client = httpx.Client(base_url=cfg["api"], timeout=10)
    try:
        client.get("/health").raise_for_status()
    except Exception as e:
        sys.exit(f"API not reachable at {cfg['api']}: {e}\nStart it: cd backend && uvicorn app.main:app --port 8000")

    keys = load_keys()
    runnables: list[tuple[dict, dict]] = []  # (bot config, key record) for standalone bots and koinon members alike
    for b in bots:
        k = ensure_agent(client, cfg, b, keys, admin)
        apply_limits(client, b, k)
        runnables.append((b, k))
    for org in cfg.get("orgs") or []:
        rec = ensure_org(client, org, keys, admin)
        for m in org.get("members") or []:
            if args.only and m["name"] not in args.only:
                continue
            runnables.append((m, ensure_member(client, org, rec, m, keys)))

    if args.status:
        status(client, runnables)
        return

    procs: list[tuple[str, subprocess.Popen]] = []
    env_base = dict(os.environ, ARENA_URL=cfg["api"], PYTHONPATH=str(ROOT / "sdk") + os.pathsep + os.environ.get("PYTHONPATH", ""))
    for i, (b, k) in enumerate(runnables):
        env = dict(env_base, ARENA_API_KEY=k["agent_key"])
        env.update({k: str(v) for k, v in (b.get("env") or {}).items()})
        if b.get("markets") and "MARKETS" not in env:
            env["MARKETS"] = ",".join(b["markets"])
        p = subprocess.Popen([sys.executable, str(ROOT / b["script"])], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        procs.append((b["name"], p))
        threading.Thread(target=stream, args=(b["name"], p, COLORS[i % len(COLORS)]), daemon=True).start()
    print(f"fleet up: {', '.join(n for n, _ in procs)}  (leaderboard: {cfg['api']}/)  Ctrl-C to stop")

    def stop(*_):
        for _, p in procs:
            p.terminate()
        time.sleep(1)
        status(client, runnables)
        sys.exit(0)

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    while True:
        time.sleep(30)
        status(client, runnables)


if __name__ == "__main__":
    main()
