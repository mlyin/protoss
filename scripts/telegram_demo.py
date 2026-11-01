#!/usr/bin/env python3
"""Run practice, API-wallet copies, or individual browser wallet review on your computer."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--web-only", action="store_true")
    parser.add_argument("--setup", action="store_true", help="guided local token, group and two-account setup")
    parser.add_argument("--wallet-review", action="store_true", help="individual mainnet review links; users sign in their own browser")
    parser.add_argument("--brand", action="store_true", help="apply the Probe profile photo to @ProtossTradingDemoBot")
    parser.add_argument("--chat", type=int)
    parser.add_argument("--users")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--live", action="store_true",
                        help="REAL orders: each participant's own Hyperliquid account through the API wallet they authorized (~/.protoss/wallets.json)")
    args = parser.parse_args()
    if args.live and args.wallet_review:
        parser.error("choose --live for API wallets OR --wallet-review for per-trade browser approval")
    if args.setup:
        if args.web_only or args.chat or args.users:
            parser.error("use --setup on its own, without --web-only, --chat or --users")
        from telegram_bridge import setup_demo, APIError
        try:
            args.chat, args.users = setup_demo(live=args.live, wallet_review=args.wallet_review)
        except (APIError, ValueError, EOFError) as exc:
            parser.exit(1, str(exc) + "\n")
    if not args.web_only and (not args.chat or not args.users or not os.environ.get("TELEGRAM_BOT_TOKEN")):
        parser.error("set TELEGRAM_BOT_TOKEN locally and supply --chat and --users, or use --web-only")
    if args.brand:
        from telegram_brand import main as apply_brand
        apply_brand()
    root = Path(__file__).resolve().parents[1]
    if not (root / "web/dist/index.html").exists():
        parser.error("build the website first: cd web && npm ci && npm run build")
    directory = Path.home() / ".protoss"
    directory.mkdir(exist_ok=True)
    api_url = f"http://127.0.0.1:{args.port}"
    mode = "copies" if args.live else "sim"
    if args.live:
        if args.web_only:
            parser.error("--live is for the Telegram bridge, not the browser practice room")
        sys.path.insert(0, str(root / "backend"))
        from app.copies import load_wallets, WALLETS_FILE
        wallets = load_wallets()
        missing = [u for u in args.users.split(",") if f"tg:{u}" not in wallets]
        if missing:
            parser.exit(1, f"no wallet registered for tg:{', tg:'.join(missing)} in {WALLETS_FILE}. Run: python scripts/wallets.py add tg:<id> --name <who> --address 0x...\n")
        for u in args.users.split(","):
            w = wallets[f"tg:{u}"]
            if not (w.get("agent_key") or (w.get("agent_key_env") and os.environ.get(w["agent_key_env"]))):
                parser.exit(1, f"tg:{u} ({w['name']}) has no API wallet key loaded.\n")
        print("LIVE: orders will leave each participant's own Hyperliquid account. Per-order cap", os.environ.get("COPIES_MAX_USD", "100"), "USD.")
        for u in args.users.split(","):
            w = wallets[f"tg:{u}"]
            print(f"  tg:{u} -> {w['name']} {w['address']}")
        if input("Type LIVE to continue: ").strip() != "LIVE":
            parser.exit(1, "stopped.\n")
    env = {**os.environ, "ARENA_MODE": mode, "MAINNET_TRADING_ENABLED": "true" if args.live else "false", "TICK_SECONDS": "0",
           "TELEGRAM_LIVE_ENABLED": "true" if args.wallet_review else "false",
           "DATABASE_URL": "sqlite:///" + str(directory / ("telegram-wallet-review.db" if args.wallet_review else "telegram-live.db" if args.live else "telegram-practice.db")),
           "ADMIN_TOKEN": secrets.token_urlsafe(32), "PROTOSS_API": api_url,
           "APP_URL": os.environ.get("DEMO_PUBLIC_URL", api_url)}
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(args.port)], cwd=root, env=env)
    worker = None
    try:
        for attempt in range(40):
            if server.poll() is not None:
                parser.exit(1, "Practice API could not start. Check whether the demo port is already in use.\n")
            try:
                with urllib.request.urlopen(api_url + "/health", timeout=1) as response:
                    ready = json.load(response).get("mode") == mode
                if ready:
                    break
            except (urllib.error.URLError, TimeoutError):
                pass
            time.sleep(0.25)
        else:
            parser.exit(1, "Practice API did not become ready.\n")
        # Check the child is still ours before allowing the bridge to use this port.
        time.sleep(0.25)
        if server.poll() is not None:
            parser.exit(1, "Practice API exited; refusing to attach to another process.\n")
        print(f"Website: {api_url}/", flush=True)
        print("Real-trade review links enabled. Each user signs in their own browser. No server signing." if args.wallet_review
              else "LIVE: real orders from each participant's account through their API wallet." if args.live
              else "Practice accounts only. No real deposits or orders.", flush=True)
        print("Ctrl-C stops this process. It does not close any real exchange position.", flush=True)
        if args.web_only:
            server.wait()
        else:
            command = [sys.executable, str(root / "scripts/telegram_bridge.py"), "run", "--chat", str(args.chat), "--users", args.users]
            if args.wallet_review:
                command += ["--state", str(directory / f"telegram-wallet-review-{args.chat}.json")]
            worker = subprocess.Popen(command, cwd=root, env=env)
            parser.exit(worker.wait())
    except KeyboardInterrupt:
        pass
    finally:
        for process in (worker, server):
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    main()
