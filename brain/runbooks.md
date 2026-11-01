# Runbooks

## Run locally
`pip install -r requirements.txt` then `python scripts/demo.py` (any OS; `run_protoss.bat` on Windows).
Sim mode, SQLite, opens http://localhost:8000. `DATABASE_URL=postgresql+psycopg://... python scripts/demo.py` for Postgres (truncates tables).

## Tests
`cd backend && python -m pytest -q` (SQLite). `TEST_DATABASE_URL=postgresql+psycopg://... python -m pytest -q` runs the same suite on Postgres.
Local Postgres for that: `/usr/lib/postgresql/16/bin/initdb` + `pg_ctl` on port 5433 (see git history 2026-10-31).

## Mac mini (always-on)
`cd ~/protoss && DATABASE_URL='...' bash deploy/macmini/install.sh`. Then `deploy/macmini/protossctl status|logs|restart|mode|funnel|url`.
Services `com.protoss.api`, `com.protoss.fleet`; logs in `logs/`. Public URL: `protossctl funnel` (Tailscale Funnel).

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
XMR is a Hyperliquid perp (listed early 2026), so candles only exist from listing; the CLI reports the bars it found and the
hack events that fell inside them. `--markets` prints what Hyperliquid lists; for an unlisted name the CLI exits with the three
closest listed markets so the question can be rephrased as "what this transfers to on Hyperliquid". `--json` for the raw result.
Event list is `backend/app/data/hacks.csv`; add rows (date, org, note) to widen the study.

Pool money from another Hyperliquid account without custody:
1. From the master wallet on app.hyperliquid.xyz: Vaults -> Create vault (name = the legion, 100 USDC minimum, leader keeps >= 5%).
2. Deposit from the other account: Vaults -> that vault -> Deposit (any Hyperliquid account can; withdrawals are self-serve after the lock-up).
3. Point the legion at it: `PUT /orgs/<slug>/vault {"address": "0x<vault>"}` with the owner key; the API checks the vault's leader is our master.
4. `ARENA_MODE=testnet` (or live later) so agents in that legion route orders with `vault_address`; the legion page then shows TVL and each depositor from Hyperliquid, not from our ledger. API deposits for that legion return 409 on purpose.

## Place a demo order through the API, no clicking (added 2026-10-31)

`scripts/trade.py <account> --coin xyz:ANT --usd 20 --leverage 1` places a market order from an API wallet acting for a master
account (the same mechanism Protoss agents use). One-time per account: app.hyperliquid.xyz -> More -> API -> generate and
authorize an API wallet; export `HL_AGENT_KEY_<NAME>` and `HL_ACCOUNT_<NAME>` in the shell. `--check` is read-only and prints
balances, position and the planned size. HIP-3 margin lives in the dex: move collateral to xyz in the app first (this SDK
has no call for that transfer). Keys never go in chat or files in the repo.

## Unified Pages frontend (2026-11-01)
See `brain/pages-deployment-2026-11-01.md`. The current frontend release source is `web/`, built by GitHub Actions, with `/app/` on the apex and a separate `api.protoss.trade` tunnel. This supersedes older apex-to-tunnel and frozen-docs deployment instructions. Do not restart or replace the fleet to publish the frontend.

## Simplified frontend (2026-11-01)
The homepage now offers four idea previews: hacks/XMR, robotics/UNITREE, an ANT short, and Dwarkesh episode research. `/app/` contains only connected-wallet positions and locally saved Telegram contacts. Legacy practice/hash routes enter this workspace. Market and position reads use the public Hyperliquid info endpoint, with no signatures or exchange calls. Wallet addresses come from the user's explicit browser-wallet connection; never embed the local wallet registry in Pages. All perpetual venues are queried, and partial failures must remain visible. Friends are local bookmarks per connected wallet, not synchronized Telegram memberships. News/podcast monitoring is not enabled. The deployed Lab currently refuses XMR research for incomplete hourly history; do not fabricate results or relax its data-quality check.
