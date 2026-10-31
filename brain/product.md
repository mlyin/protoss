# Product

**Coliseum** (renamed from Koinon on 2026-10-31): friends pool money into a **phalanx** that AI agents trade
on Hyperliquid inside hard limits enforced before any order reaches the exchange. Everything is public:
every fill, every rejected order, every halt. People follow agents and phalanxes, copy them, and backtest
ideas in plain English in **the Lab**.

- Who: crypto-native twenty-somethings who already trade perps, and their friends who want in without blowing up.
- Unit of the product: the phalanx. A leader writes a plain-English mandate, sets the lines (max leverage,
  notional cap, daily loss, drawdown stop, allowed markets), seeds it, invites friends. Agents get slices of
  the pool and nest inside the mandate; the smaller limit always wins. Leader takes a cut of profits only.
- Revenue: Hyperliquid builder code, 0.03% of routed notional (`HL_BUILDER_FEE_TENTHS_BP=30`; protocol cap 0.1%).
  The builder is a dedicated wallet with >= 100 USDC in standard mode. Later: leader profit share split, Lab pro.
- Modes: `sim` (synthetic prices), `paper` (real HL prices, simulated fills), `testnet` (real orders via sub-accounts).
- Vocabulary: phalanx (not org, pool, fund, vault, squad), agent (not bot, in product copy), the Arena (leaderboard),
  the Lab (backtesting chat), the line (a limit), stopped at the line (halted), builder code (not referral).
- Not: a fund, custody of your wallet by strangers, an AI that trades without limits, financial advice.
- Comparables we get asked about: SEPI-style agent-trading apps (we are the limits + social layer, not another
  agent), HL vaults (we nest many agents under one mandate with per-agent limits), copy-trading apps (we copy
  phalanxes and agents, inside your own limits).
- Status 2026-10-31: v0.4 prototype. 31 tests. Runs on SQLite or Supabase Postgres. Paper and testnet
  adapters written, not yet exercised live. Mac mini is the first host. No GitHub repo yet (`mlyin/koinon` or
  `mlyin/coliseum`, Matthew to create).
