# Handoff (written 2026-10-31, for the session that picks this up next)

Read `CLAUDE.md` and `brain/INDEX.md` first. This page is the state of the world on the day the work moved from a cloud
session (linked to Matthew's Windows PC) to a session on his Mac mini. Memory about Matthew himself lives in his Claude memory
and follows him; this page is about the repo.

## Update 2026-10-31 (afternoon, Mac mini session)
Blocked on Matthew, in order:
1. Done 16:06: gh on the mini now has repo scope; branch `claude/project-thread-495i0w` is pushed; Pages is on (Actions)
   with custom domain protoss.trade and the workflow is green. It serves nothing at protoss.trade until DNS exists.
2. Cloudflare sign-in: DNS (`CNAME @` and `www` to mlyin.github.io, proxy off) and a Cloudflare Tunnel for
   `app.protoss.trade`. Funnel cannot carry a custom domain. `cloudflared` is installed.
3. Master wallet: create the first legion's vault (runbooks, "pooling into a vault").
4. Keys: `PRIVY_APP_ID`, `ONRAMP_MOONPAY_KEY/SECRET/WEBHOOK_KEY` in backend/.env, then `protossctl restart`.

Running: API + fleet as launchd services on aaaas-mac-mini, paper mode, https://aaaas-mac-mini.tailb9b0ef.ts.net (Funnel).
Done since the morning handoff: candle cache for BTC ETH SOL HYPE XMR (`scripts/candles.py`); tail-wallet verified on real
fills; MoonPay webhook (signed, forward-only); Stake button signing vaultTransfer (`web/src/hlsign.js`, verified against the
Python SDK); Privy email wallet lazy-loaded behind `PRIVY_APP_ID`. Open threads 2 and 4 below are code-complete apart from keys.

## What Protoss is
Friends pool money into a **legion** (code says `org`; do not rename). Agents trade it on Hyperliquid inside hard limits the
leader drew. Every fill and every rejected order is public. Revenue: a builder code on every fill. The **Lab** answers
plain-English backtest questions. **Join with card** gets a person from fiat to a stake without touching the Hyperliquid UI.

## Where things are
- Repo: github.com/mlyin/protoss, branch `main`, last commit f6fa30b, `harness/check.sh` GREEN (54 tests).
- Domain: protoss.trade on Cloudflare. GitHub Pages workflow (`.github/workflows/pages.yml`) publishes `docs/` on every push.
- Supabase project `koinon` (ref hgegigtdjkkclexqnuoy): migrations 0001 to 0004 applied, RLS on. DB password: Matthew has it.
- Design canvas and the old handoff doc still carry the Coliseum name; cosmetic.

## Done today
- Rename Coliseum to Protoss everywhere (services `com.protoss.*`, `protossctl`, `run_protoss.bat`).
- Vault-backed legions: `PUT /orgs/{slug}/vault`, adapter routes member orders to the vault, legion page reads TVL and
  depositors from Hyperliquid. Non-custodial by construction.
- Join with card backend (`backend/app/onboard.py`): options, hosted checkout URL (MoonPay signed URL, Coinbase preview,
  manual path), region gate (US blocked by default via `CF-IPCountry`), polling to funded, staked. Web page `#/join`.
- Dashboard restyle: home with hero and live strip, paper theme toggle, phone layout, skeletons, empty states.
- Lab on real data offline: `FileCandles` reads `backend/app/data/candles/<MARKET>_1d.csv`; XMR daily history
  2024-08-22 to 2026-10-30 is shipped. Event studies print an any-day baseline. 2026 hacks (Binance $6.3B included) added.
- Study result: buying XMR on hack days has no edge over any day; details in `brain/product.md`.
- One-line Mac mini install: `deploy/macmini/bootstrap.sh`.

## Waiting on Matthew (only his logins can do these)
1. GitHub: repo Settings, Pages, Source = GitHub Actions; custom domain `protoss.trade`. Until then the Pages run fails at
   `configure-pages`.
2. Cloudflare DNS: `CNAME @ -> mlyin.github.io`, `CNAME www -> mlyin.github.io`, proxy off.
3. Builder wallet: a standard-mode Hyperliquid account with >= 100 USDC; its address goes in `HL_BUILDER_ADDRESS`.
4. Keys for Join with card when ready: `PRIVY_APP_ID`, `ONRAMP_MOONPAY_KEY/SECRET` (currency `usdc_hypercore` once
   MoonPay Gateway is enabled on the account), `ONRAMP_COINBASE_APP_ID`.

## First things to do on the Mac mini
```
curl -fsSL https://raw.githubusercontent.com/mlyin/protoss/main/deploy/macmini/bootstrap.sh | bash
~/protoss/deploy/macmini/protossctl status
~/protoss/deploy/macmini/protossctl funnel        # public https URL; point app.protoss.trade at it
```
Then, with the API up: run `python scripts/lab.py "..."` for real Hyperliquid answers, refresh the candle cache for more
markets (`candleSnapshot`, 1d, write `backend/app/data/candles/<MARKET>_1d.csv`), and wire Privy in `web/src/Join.jsx`.

## Open threads, in order
1. Live site: Pages on, DNS, then `app.protoss.trade` to the mini's Funnel URL; `VITE_API`/CORS as needed.
2. Join with card: Privy embedded wallet in the browser, `vaultTransfer` signing, MoonPay webhook instead of polling.
3. First real legion: create a Hyperliquid vault from the master wallet, deposit from Matthew's other account,
   `PUT /orgs/<slug>/vault`, `ARENA_MODE=testnet`.
4. Lab: `static_demo.py` should snapshot `/onboard/options`; more cached markets; tail-wallet on real fills.
5. agent-desktop (Chris Tate) evaluation on the minis; harness loop for routine tasks (`harness/README.md`).
6. Brand: Design canvas and old handoff doc still say Coliseum; X thread in `brand/x-thread.md` is drafted, unposted.

## Rules that do not change
Shell and files only, never his screen. Never move money or sign with his keys. Keys never in chat, commits or the brain.
Copy follows `brain/voice.md`; UI follows `brain/design.md`. GREEN before done. Commits end with the attribution trailer.
