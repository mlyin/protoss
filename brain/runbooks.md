# Runbooks

## Run locally
`pip install -r requirements.txt` then `python scripts/demo.py` (any OS; `run_coliseum.bat` on Windows).
Sim mode, SQLite, opens http://localhost:8000. `DATABASE_URL=postgresql+psycopg://... python scripts/demo.py` for Postgres (truncates tables).

## Tests
`cd backend && python -m pytest -q` (SQLite). `TEST_DATABASE_URL=postgresql+psycopg://... python -m pytest -q` runs the same suite on Postgres.
Local Postgres for that: `/usr/lib/postgresql/16/bin/initdb` + `pg_ctl` on port 5433 (see git history 2026-10-31).

## Mac mini (always-on)
`cd ~/coliseum && DATABASE_URL='...' bash deploy/macmini/install.sh`. Then `deploy/macmini/coliseumctl status|logs|restart|mode|funnel|url`.
Services `com.coliseum.api`, `com.coliseum.fleet`; logs in `logs/`. Public URL: `coliseumctl funnel` (Tailscale Funnel).

## Supabase
Project `koinon` (ref hgegigtdjkkclexqnuoy, us-east-1; the project keeps the old name). Migrations in `backend/migrations/`,
applied with the Supabase MCP `apply_migration`. RLS is on for every table; the API connects as the DB owner.
Connection string: dashboard Connect > Transaction pooler, scheme `postgresql+psycopg://`.

## Builder code
`python scripts/builder.py keygen` (on the host that keeps the key) > fund >= 100 USDC, standard mode >
`HL_BUILDER_ADDRESS` in `backend/.env` > `builder.py status` says ELIGIBLE > `builder.py approve` from the master wallet.
Outside wallets approve on `#/approve`. Fills CSV: `builder.py fills --date YYYYMMDD`.

## Release a zip
`git ls-files -z | xargs -0 cp --parents -t out/coliseum/` + `web/dist` > zip `coliseum-vX.Y.zip` > attach in chat / sync to the PC.

## X thread
Draft in `brand/x-thread.md` style, run the anti-slop audit in [[voice]] (or the `x-anti-slop` skill), 7 to 9 posts,
one ask at the end, screenshots from the running app, status honesty. Save the shipped version under `brain/content/`.

## Adding a strategy to the Lab
Spec type in `backend/app/backtest.py` (pydantic, discriminated on `type`), parser rule in `backend/app/lab.py`, a test in
`backend/tests/test_lab.py`, an example in `/lab/examples`. Deployable maps to `fleet.yaml` semantics.

## Agents on the Mac minis (to do)
Matthew runs Claude Code, Codex and Hermes on 4 Mac minis. Evaluate **agent-desktop** by Chris Tate (@ctatedev, Oct 30 2026:
computer use for any coding agent, runs in the background, parallel agents each with their own cursor, macOS/Windows/Linux)
as the way agents use the minis without taking over his screen. Every agent reads this brain first (`CLAUDE.md` / `AGENTS.md`).
