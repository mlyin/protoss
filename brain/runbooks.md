# Runbooks

- 2026-11-01: Preserve Telegram's private `/#/telegram/connect?token=...` and `/#/trade?token=...` links. They canonicalize to `/app/#/...`; tokens stay in fragments and authorization headers, never browser storage or query strings. These screens are private entry points, not extra public navigation. Pages uses its configured API origin. An API-hosted/local build without an explicit `VITE_API_ORIGIN` keeps private requests on its issuing origin; URL parameters cannot choose a backend. The bot's `APP_URL` and the frontend's private API must resolve to the same database. Do not point a local bot's links at Pages while its tokens exist only in a local database.

- 2026-11-01: Iterate on a locally rendered preview before publishing, per Matthew. The current preview runs at `http://127.0.0.1:4374/`; its local-only proxy sends `/lab` research requests to the public API. This avoids requiring a deployment for UI feedback. Keep CI as the release check, not the edit-preview loop.
- 2026-11-01: Telegram launcher no longer requires a website build for bot-only operation. `--web-only` and `--wallet-review` require the current `web/pages-dist` build (preferred by the API) or legacy `web/dist`. The API serves the same index at `/app/` even with a plain Vite build. Uvicorn receives an explicit `--app-dir backend` so a shared virtualenv cannot import another checkout. `--state` and `--previous-chat` are forwarded to the bridge; explicitly retain the intended checkpoint/huddle after a group upgrade. `--prompt-token` uses a hidden interactive prompt without saving the token. SIGTERM stops both children. A per-bot OS lock prevents two local pollers; a Telegram 409 exits instead of fighting another connection. `inspect` does not poll; `inspect --pending` and setup acquire the same lock. The lock file may remain after exit; the OS lock, not the file or PID text, is authoritative.

- 2026-11-01: The homepage XMR study requests an explicit 180-day window and displays that scope in its button. This succeeds against the current public API without weakening its history-completeness checks. Show the ordinary-day baseline when returned, alongside the result and its data caveats. The current public backend uses hourly candles for this event rule. A longer window is not silently substituted.

- 2026-11-01: Telegram private messages now answer greetings, offer the four research ideas, and use the read-only Lab in copies mode. Private research never posts into the group, creates a huddle, backs an idea, or places an order. Private positions link to the connected-wallet website. Ordinary group greetings also receive a reply. Existing group approval commands retain their behavior.
- 2026-11-01: Promoting the bot upgraded `protoss beta testing` to a supergroup. The bridge supports `--previous-chat <original-group-id>` with `--chat <current-group-id>` and the existing `--state` file to retain its original huddle, participants, delivery receipts, and update offset. Do not start a new room or reset the checkpoint after a Telegram upgrade. Confirm the new group ID from Telegram's migration response. The bot is an administrator with deletion, banning, invitations, video-chat management, and adding admins disabled.
- 2026-11-01: MacBook runtime: the bridge now runs independently from `~/protoss-demo`, with PID in `~/.protoss/telegram-bridge.pid` and private log `~/.protoss/telegram-bridge.log`. Its existing API on port 8001 was preserved in copies mode. Credentials remain in process memory; no new token file or boot service was installed. This is not an always-on deployment: sleep/reboot can interrupt it. Never launch a second poller against the same bot.

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
- 2026-11-01: `scripts/candles.py` with no arguments now refreshes every market already in `backend/app/data/candles/` plus the
  defaults. 34 markets cached (top perps by volume, every HIP-3 name in the Lab's alias list), 1.8 MB. xyz:ANT has 6 bars (listed 2026-10-26).
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

## Live Telegram copies (added 2026-10-31)

See docs/telegram-demo.md, section "Live copies". Short form: per participant `scripts/wallets.py add tg:<id> --name .. --address 0x..`
(key at a hidden prompt), `scripts/wallets.py check tg:<id>`, collateral on the xyz dex, then
`scripts/telegram_demo.py --live --chat <group> --users <id1>,<id2>` and type LIVE. Receipts come from Hyperliquid fill history.
Matthew's rule: the only thing a participant should touch is Telegram; the one-time authorization is the exception because it is their signature.

## Run the live Telegram bot on the MacBook (added 2026-11-01)
1. Once: Matthew saves the bot token to `~/.protoss/telegram.env` (mode 600) himself. Agents never read that file.
2. Once: clone the dev checkout to `~/protoss-bot` (launchd cannot read ~/Documents), then run
   `~/protoss-bot/deploy/macbook/install_telegram.sh <chat id> <user id>,<user id>`.
3. After a change in `~/Documents/protoss2`: commit, then `deploy/macbook/update_bot.sh` (local fetch, restart). No push needed.
4. Watch `~/.protoss/telegram-live.log`. Stop: `launchctl bootout gui/$(id -u)/com.protoss.telegram`.
   Anything off: `deploy/macbook/doctor.sh` (read-only; token file, service, polling, awake hold, admin, webhook, public API).
5. Before shipping chat changes, drive the flow with fake Telegram and exchange (`backend/tests/test_copies.py` has the
   pattern) and read every message the group would see.

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

## Episode research (2026-11-01)

`POST /research/podcast` is an admin-authenticated, read-only route for the Telegram bridge. It reads a supplied public Dwarkesh episode URL or the latest published audio episode, extracts public article text, and asks the existing Anthropic provider for cited claims and an optional hypothesis. `PODCAST_ANTHROPIC_API_KEY` configures episode research only. Existing `ANTHROPIC_API_KEY` is a compatibility fallback and also enables the Lab model planner; do not set it merely to configure episode research. `LAB_MODEL` is optional. Never put provider keys in chat or Git. No key means an explicit unavailable response, not a template trade.

This initial version serves configured invited Telegram users only. One research call runs at a time, provider calls are at least 60 seconds apart, and the same public text plus current active-market catalog reuses a result for 15 minutes (at most eight cached episodes). These limits are process-local. Sources are restricted to public Dwarkesh article URLs; every redirect is revalidated. Public text is capped at 30,000 characters and truncated coverage is disclosed. Claims are not independently verified; paywalled content is not inferred. Active-market metadata is fetched anew, excluding delisted entries. The output has no trading spec, thesis, approval, allocation or order.

Both the private and configured group paths deliver research directly, before any trade handler. Telegram delivery checkpoints preserve the exact remaining text after a partial send. Automatic episode monitoring is not implemented by this route; the existing explicitly configured release-date rules and runtime trading settings remain unchanged. A real provider-backed response still needs acceptance verification on the configured runtime before calling transcript research operational.
