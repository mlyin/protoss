# Product

**Protoss** (renamed from Koinon on 2026-10-31): friends pool money into a **legion** that AI agents trade
on Hyperliquid inside hard limits enforced before any order reaches the exchange. Everything is public:
every fill, every rejected order, every halt. People follow agents and legions, copy them, and backtest
ideas in plain English in **the Lab**.

- Who: crypto-native twenty-somethings who already trade perps, and their friends who want in without blowing up.
- Unit of the product: the legion. A leader writes a plain-English mandate, sets the lines (max leverage,
  notional cap, daily loss, drawdown stop, allowed markets), seeds it, invites friends. Agents get slices of
  the pool and nest inside the mandate; the smaller limit always wins. Leader takes a cut of profits only.
- Revenue: Hyperliquid builder code, 0.03% of routed notional (`HL_BUILDER_FEE_TENTHS_BP=30`; protocol cap 0.1%).
  The builder is a dedicated wallet with >= 100 USDC in standard mode. Later: leader profit share split, Lab pro.
- Modes: `sim` (synthetic prices), `paper` (real HL prices, simulated fills), `testnet` (real orders via sub-accounts).
- Vocabulary: legion (not org, pool, fund, vault, squad), agent (not bot, in product copy), the Arena (leaderboard),
  the Lab (backtesting chat), the line (a limit), stopped at the line (halted), builder code (not referral).
- Not: a fund, custody of your wallet by strangers, an AI that trades without limits, financial advice.
- Comparables we get asked about: SEPI-style agent-trading apps (we are the limits + social layer, not another
  agent), HL vaults (we nest many agents under one mandate with per-agent limits), copy-trading apps (we copy
  legions and agents, inside your own limits).
- Status 2026-10-31: v0.4 prototype. 31 tests. Runs on SQLite or Supabase Postgres. Paper and testnet
  adapters written, not yet exercised live. Mac mini is the first host. No GitHub repo yet (`mlyin/koinon` or
  `mlyin/protoss`, Matthew to create).

## Why the harness/loop/graph framing is also the pitch (added 2026-10-31)

Protoss is Levels 1 to 6 of the agent ladder, for trading agents instead of coding agents:
- Harness, hands: the SDK and `/v1/orders` are the only hands an agent has.
- Harness, walls: the risk sandbox is a permission, not a prompt. "Never above 3x" is enforced in code before the
  exchange sees the order; an agent that asks for 5x gets a rejected order, not a warning.
- Harness, memory: positions, cash, peak equity and the decision log live outside the model.
- Loop, the check: every order is checked; drawdown and daily loss are checked every tick. The check can fail.
- Loop, feedback: the verdict carries the reason (`verdict_reason`), the resize carries the allowed size.
- Graph, shape: a legion is nodes (agents) with their own rooms (sub-accounts) under one mandate; the smaller limit wins.
- Graph, gates by undo: reduce-only always passes; new risk needs headroom; deposits, withdrawals and mandate
  changes need the org key, i.e. a person. No score to argue with.
- Learning: the Lab turns a hunch into a check before any money moves.
Say it this way to Imran: "every other agent product is Level 1. We sell the walls and the gates."

## Join with card (added 2026-10-31)

Matthew: "ideally we would not have the person have to go through hyperliquid etc like for legend.trade you can just deposit with fiat etc."
Shape, non-custodial end to end (`backend/app/onboard.py`, `web/src/Join.jsx`):
1. Email login creates an embedded wallet in the browser (Privy; Hyperliquid's own email login is the same pattern). The key never touches our servers.
2. Card / Apple Pay / bank through an onramp partner that pays USDC to the user's own address. MoonPay Gateway lists USDC on HyperCore (May 2026), so funds can land on the Hyperliquid account directly; Coinbase Onramp and the manual path deliver USDC on Arbitrum and the bridge credits the same address.
3. The browser signs `vaultTransfer` into the legion's Hyperliquid vault. Leaving is the same action reversed, signed by the user. Protoss holds nothing and cannot block an exit.
Server: `GET /onboard/options`, `POST /onboard/session` (returns the hosted checkout URL and the plain-English steps), `GET /onboard/session/{id}` (polls the wallet's equity on a live exchange; sim fakes funding at 20 s), `POST .../staked`. Region gate via Cloudflare's `CF-IPCountry`; `ONBOARD_BLOCKED_REGIONS` defaults to US.
Not done: Privy wiring in the browser (needs `PRIVY_APP_ID`), MoonPay keys (`ONRAMP_MOONPAY_KEY/SECRET`, currency `usdc_hypercore` once Gateway is enabled on the account), Coinbase session tokens, partner webhooks (polling stands in).
Compliance, stated plainly: Hyperliquid's own app blocks US users, Legend and the other builder fronts geofence the US, and offering perps to US persons is a CFTC matter. Matthew is in NYC. Ship with the US block on and have counsel look before any US opening. Not legal advice; the point is to make the default the safe one.

## Study: XMR on hacks, real Hyperliquid data (2026-10-31)

Matthew's first strategy question. Daily XMR candles pulled from the public Hyperliquid API (via his browser; the cloud container cannot reach it), cached in `backend/app/data/candles/XMR_1d.csv` (2024-08-22 to 2026-10-30). 26 events from `hacks.csv` in the 730-day window, $10k, 4.5 bp + 3 bp slippage.
- hold 3d +34%, 7d +24%, 14d +43%, 30d +85%; buy and hold +282%. Max drawdown 13% to 45%.
- No edge: mean 7d move after a hack +1.3% (median -0.9%) vs +1.7% from any day; 30d +6.3% vs +7.5%. Crypto-native hacks were the worst entries (Bybit -6.5%, Cetus -12.3% at 7d).
- On Hyperliquid: XMR-PERP since 2026-01-15, 5x max, funding positive 97% of hours, longs paying ~29% annualized (0.3 to 1.4% per 7-day hold). That alone eats the mean move.
- Binance $6.3B theft (2026-10-29) added to the list; XMR -2.9% day one.
Lesson for the product: the Lab must always print the any-day baseline next to an event study, or people will read time-in-market as edge. Done the same day: every event_buy result carries a `baseline:` note (mean move after the events vs from any bar).

## Study: buy the dip, real Hyperliquid data (2026-11-01)

The Lab used to answer "buy NVDA when it drops 5% in a day, sell after 5 days" with buy and hold, because the bare word "buy"
matched first. It now runs a dip study (`dip_buy`): every daily close X% below the close N days earlier, entry at that close,
the any-day baseline printed next to it. First answers, 730-day window, $10k, daily bars:
- xyz:NVDA, 5% one-day drop, hold 5d: 6 events, -9.9% vs +5.8% buy and hold; mean 5d move -1.56% (1 of 6 up) vs +0.22% from any day.
- SOL, 10% one-day drop, hold 5d: 7 events, -14.5% vs -42.7% buy and hold; mean 5d move -1.32% vs +0.01% from any day.
Beating buy and hold on SOL came from sitting in cash through a falling market, not from the dips: the baseline says so.

- 2026-10-31: The Privy embedded wallet is called the **Protoss wallet** in copy (Matthew). Code keeps `privy`/`protossWallet`.

## The group chat (added 2026-10-31)
The legion lives where friends already talk. Someone says "let's buy XMR every time a major company gets hacked"; Protoss
replies with a card (tested on 25 hacks since Oct 2024: XMR +1.3% in the 7 days after a hack vs +1.7% after any day, 10 of
25 up), two thumbs up back it, "$50 each" stakes it, the next hack fires it, and the close posts the result and the running
score by whose idea it was. Ideas with no Hyperliquid market (sports, injuries) are logged as calls and scored by the group.
The hack thesis has no edge on the real data so far; the card says so, which is the point.
