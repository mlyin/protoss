# Runbooks

- 2026-10-31: Two-account Telegram and browser demo: `docs/telegram-demo.md`. `scripts/telegram_demo.py`
  starts an isolated sim API and optional Telegram bridge. It forces mainnet execution off. Browser entry: `/#/demo`.
  Each participant gets a separate practice trade. Wallet signatures prove ownership only.

- 2026-10-31: Anthropic / Messages acceptance steps are in `docs/live-imessage-test.md`. `scripts/live_check.py`
  reads mainnet market metadata, public-account positions and fills for `xyz:ANT`, without keys or signing.
  Explicit mainnet vault mode now exists with execution off by default. Live verification and chat reconciliation of real fills remain outstanding.

## Run locally
`pip install -r requirements.txt` then `python scripts/demo.py` (any OS; `run_protoss.bat` on Windows).
Sim mode, SQLite, opens http://localhost:8000. `DATABASE_URL=postgresql+psycopg://... python scripts/demo.py` for Postgres (truncates tables).

## Tests
`cd backend && python -m pytest -q` (SQLite). `TEST_DATABASE_URL=postgresql+psycopg://... python -m pytest -q` runs the same suite on Postgres.
Local Postgres for that: `/usr/lib/postgresql/16/bin/initdb` + `pg_ctl` on port 5433 (see git history 2026-10-31).

## Mac mini (always-on)
`cd ~/protoss && DATABASE_URL='...' bash deploy/macmini/install.sh`. Then `deploy/macmini/protossctl status|logs|restart|mode|funnel|url`.
Services `com.protoss.api`, `com.protoss.fleet`; logs in `logs/`. Public URL: `protossctl funnel` (Tailscale Funnel).
- 2026-10-31: Installed on aaaas-mac-mini (paper mode, SQLite, 1057 markets). Live app: https://aaaas-mac-mini.tailb9b0ef.ts.net
  (the API serves web/dist, so the dashboard and API share that origin). Funnel serves only its own ts.net name, so
  `app.protoss.trade` cannot be a CNAME to it; a custom app domain needs a Cloudflare Tunnel (`cloudflared`) instead.
- 2026-10-31: app.protoss.trade is a Cloudflare Tunnel (`protoss`, id f4016e23) to 127.0.0.1:8000, run by launchd
  `com.protoss.tunnel` (`cloudflared tunnel run protoss`, config in ~/.cloudflared/config.yml, log logs/com.protoss.tunnel.log).
  `PUBLIC_URL=https://app.protoss.trade` in backend/.env so checkout redirects land on the live app. Recreate on a new
  machine: `cloudflared tunnel login` (Matthew clicks Authorize on protoss.trade), `tunnel create`, `tunnel route dns`.
- 2026-10-31: Refresh the Lab's offline candles with `.venv/bin/python scripts/candles.py [MARKETS]` (default BTC ETH SOL HYPE XMR,
  daily, full history, drops the bar still forming). Lab tests pin their own cache to XMR, so shipping a market does not move them.
- 2026-10-31: Tail-wallet verified on real fills from the mini: `scripts/lab.py "tail 0x... with $10k over the last 7 days"` replayed 65 fills across 14 markets. Vault addresses like HLP trade through sub-accounts and have no fills of their own, so the Lab synthesizes for them and says so.
- 2026-10-31: Privy turns on by setting `PRIVY_APP_ID=` in backend/.env, then `protossctl restart`. The Join page lazy-loads web/src/PrivyWallet.jsx (1.6 MB chunk) only when the id is set; email sign-in makes an embedded wallet and the Stake button signs with it. In the Privy dashboard, allow the app's origins (the Funnel URL, protoss.trade).
- 2026-10-31: The local `gh` token cannot enable Pages (403 on POST /pages); that switch needs Matthew's browser login.

## Supabase
Project `koinon` (ref hgegigtdjkkclexqnuoy, us-east-1; the project keeps the old name). Migrations in `backend/migrations/`,
applied with the Supabase MCP `apply_migration`. RLS is on for every table; the API connects as the DB owner.
Connection string: dashboard Connect > Transaction pooler, scheme `postgresql+psycopg://`.

## Builder code
`python scripts/builder.py keygen` (on the host that keeps the key) > fund >= 100 USDC, standard mode >
`HL_BUILDER_ADDRESS` in `backend/.env` > `builder.py status` says ELIGIBLE > `builder.py approve` from the master wallet.
Outside wallets approve on `#/approve`. Fills CSV: `builder.py fills --date YYYYMMDD`.

## Release a zip
`git ls-files -z | xargs -0 cp --parents -t out/protoss/` + `web/dist` > zip `protoss-vX.Y.zip` > attach in chat / sync to the PC.

## X thread
Draft in `brand/x-thread.md` style, run the anti-slop audit in [[voice]] (or the `x-anti-slop` skill), 7 to 9 posts,
one ask at the end, screenshots from the running app, status honesty. Save the shipped version under `brain/content/`.

## Adding a strategy to the Lab
Spec type + parser rule in `backend/app/lab.py` (pydantic, discriminated on `type`), engine logic in `backend/app/backtest.py`, a test in
`backend/tests/test_lab.py`, an example in `/lab/examples`. Deployable maps to `fleet.yaml` semantics.

## Agents on the Mac minis (to do)
Matthew runs Claude Code, Codex and Hermes on 4 Mac minis. Evaluate **agent-desktop** by Chris Tate (@ctatedev, Oct 30 2026:
computer use for any coding agent, runs in the background, parallel agents each with their own cursor, macOS/Windows/Linux)
as the way agents use the minis without taking over his screen. Every agent reads this brain first (`CLAUDE.md` / `AGENTS.md`).

## First real strategy run (XMR on hacks) and pooling into a vault (added 2026-10-31)

The cloud container cannot reach Hyperliquid, so real-data backtests run on a machine of Matthew's:
    cd protoss/backend && .venv\Scripts\activate (Windows) or . .venv/bin/activate (Mac)
    python ../scripts/lab.py "what if I bought XMR every time a major institution got hacked and held 7 days" --days 730
XMR is a Hyperliquid perp; candleSnapshot serves daily bars from 2023-04-22 (checked 2026-10-31), so candles only exist from then; the CLI reports the bars it found and the
hack events that fell inside them. `--markets` prints what Hyperliquid lists; for an unlisted name the CLI exits with the three
closest listed markets so the question can be rephrased as "what this transfers to on Hyperliquid". `--json` for the raw result.
Event list is `backend/app/data/hacks.csv`; add rows (date, org, note) to widen the study.

Pool money from another Hyperliquid account without custody:
1. From the master wallet on app.hyperliquid.xyz: Vaults -> Create vault (name = the legion, 100 USDC minimum, leader keeps >= 5%).
2. Deposit from the other account: Vaults -> that vault -> Deposit (any Hyperliquid account can; withdrawals are self-serve after the lock-up).
3. Point the legion at it: `PUT /orgs/<slug>/vault {"address": "0x<vault>"}` with the owner key; the API checks the vault's leader is our master.
4. `ARENA_MODE=testnet` (or live later) so agents in that legion route orders with `vault_address`; the legion page then shows TVL and each depositor from Hyperliquid, not from our ledger. API deposits for that legion return 409 on purpose.

## iMessage group chat (huddle) on the Mac mini (added 2026-10-31)
Engine: `backend/app/huddle.py` (thesis -> Lab card -> tapback/"in" approvals -> "$50 each" -> paper agent -> fires on
`protoss hack: ...` or a feed headline -> closes after the hold -> result + score). Web demo: https://app.protoss.trade/#/huddle/demo
(or `/#/huddle/<legion-slug>` to pool into that legion). Link previews: `/l/<slug>`, `/t/<thesis id>`, `/h/<name>`.
Bridge (stdlib, runs on the mini):
1. Messages.app signed into iMessage (best: a separate Apple ID for the bot, added to the group like a friend).
2. System Settings, Privacy & Security, Full Disk Access: add the Python that runs the bridge (`~/protoss/.venv/bin/python3`
   resolves to a real binary; add that, or Terminal for a manual run). Without it chat.db will not open.
3. `cd ~/protoss && .venv/bin/python scripts/imessage_bridge.py chats` and copy the group's guid (`iMessage;+;chat...`).
4. Names: `~/.protoss/names.json` like `{"+15551234567": "Lee"}`.
5. Dry run: `ADMIN_TOKEN=<from backend/.env> BRIDGE_ME=Matthew .venv/bin/python scripts/imessage_bridge.py run --chat '<guid>' --title 'the boys' --legion <slug> --dry-run`
6. Drop `--dry-run`; the first send pops one Automation prompt (allow control of Messages). Then run it under launchd.
Env: `PROTOSS_API` (default http://127.0.0.1:8000), `ADMIN_TOKEN`, `BRIDGE_ME`. Optional backend env: `HUDDLE_HACK_FEEDS`
(JSON list of RSS URLs read for hack headlines), `HUDDLE_QUORUM` (default 2), `APP_URL` (links in chat).
- 2026-10-31: iMessage extension (in-thread cards) scaffolded in `ios/` (XcodeGen spec, SwiftUI). Build and Simulator steps in
  `ios/README.md`. Written without a Mac in the loop: the first `xcodebuild` on the mini is its first compile.
