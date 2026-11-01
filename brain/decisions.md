# Decisions

- 2026-11-01: The demo is four ideas, everywhere (homepage, Lab examples, Telegram /demo), in this order (Matthew):
  1. "Let's buy XMR every time a major company gets hacked": buy XMR after each hack, hold 1 day.
  2. "I think robots are going to take over the world": buy and hold xyz:UNITREE.
  3. "The Anthropic bubble is going to pop": short xyz:ANT.
  4. "Dwarkesh is always right": research a specific episode or claim, then identify a market and direction. A release alone does not imply buying NVDA. Episode monitoring and transcript analysis remain unconnected. An explicitly requested market/direction rule can still be backtested against release dates.
  The website (PR #6) is Home (the four ideas as chat previews, Open Telegram) and Friends & positions (the connected wallet's
  positions read from Hyperliquid; no registry addresses shipped). Practice app, Activity and the web group chat are gone. The
  backend side (PR #7): the Lab parses the four sentences, shorts, Dwarkesh episode dates, the bot's /demo menu.
- 2026-10-31: Concurrent API-wallet work arrived as e4a6a3c. Preserve its existing `--live` flag and `copies` mode. The browser approval flow uses `--wallet-review`, a separate database/checkpoint, and cannot be combined with `--live`. This avoids silently changing the authorization model.

- 2026-10-31: Live Telegram copies: each participant authorizes an API wallet on their own Hyperliquid account once; the bridge in `copies` mode (`backend/app/copies.py`) sends one real order per person from that account, 1x, capped per order, receipts read back from Hyperliquid fill history. No master key, nothing pooled. The shared-vault adapter stays the legion path; copies are the group-chat path.
- 2026-10-31: Matthew wants the Probe to animate with product state: thinking during a backtest, two Probes talking during the group flow, working during wallet/exchange checks, and a completion state. Add native standalone SVG exports, a preview gallery, and reduced-motion support. Keep generated PNG art for the bot avatar and compact brand mark.

- 2026-10-31: Matthew explicitly selected real trades with individual wallet approval. Implement a separate opt-in Telegram live review path, private links bound to each participant, live mainnet quotes, browser-only signatures/submission, and exact exchange-fill reconciliation. The first version is one buy market per idea, $12–$100, with an explicit user choice of 1× cross margin. Do not relabel simulation as real execution. Mainnet acceptance remains user-operated.
- 2026-10-31: Matthew requested a cartoon StarCraft Protoss Probe for the Telegram bot and website. Generated gold/cyan Probe artwork replaces the website mark and hero. Local avatar-upload script changes only @ProtossTradingDemoBot using its locally supplied token. This supersedes the Spartan mark for these surfaces.

- 2026-10-31: Matthew requested buy/long xyz:ANT with a $20 position per person. Public trading addresses were later supplied in chat and checked read-only. The checker supports core BTC/ETH and HIP-3 markets. Live execution must be distinguished from the practice bot.

- 2026-10-31: Matthew wants the idea-to-portfolio flow demonstrated socially in the website and Telegram. Start with an explicit 60% BTC / 40% ETH practice basket, separate budgets and approvals, and independent receipts. Label perpetual markets and simulation clearly. Add guided local bot setup so the token never needs to enter chat. Real per-account execution remains a separate acceptance step.

- 2026-10-31: Matthew chose Telegram for the working two-account demo, with a playable browser version. iMessage stays a visual demo for now. Each person copies the same idea into a separate account; no shared stake or payout split. Use simple product language: idea, group, practice money, trade copy. Implementation names can stay unchanged.

- 2026-10-31: Staking signs vaultTransfer in the browser with web/src/hlsign.js (L1 phantom-agent EIP-712, hash and r/s/v verified against hyperliquid-python-sdk). Provider is window.protossWallet (Privy embedded, still to wire, needs PRIVY_APP_ID) or an injected wallet; injected wallets may refuse chain-1337 typed data and the UI says so.
- 2026-10-31: Product name is Protoss (was Coliseum, was Koinon) as of Oct 31; domain protoss.trade; repo mlyin/protoss. Legion = the pooled org.
- 2026-10-31: Dev process runs on harness/ (check.sh GREEN, feedback with dead ends, gates by undo cost, rooms per task). CI runs the same check on PRs.
- 2026-10-31: Ad headline is 'Your friends. One wall.'; brand files live in brand/, posters also on the 'Protoss Ads' Design canvas.
- 2026-10-31: Shared brain lives in brain/ (LLM-wiki pattern); CLAUDE.md and AGENTS.md point every agent at it. Corrections go in corrections.md, one line, dated.
- 2026-10-31: Rebrand Koinon -> **Protoss**; pooled org -> **legion**. Design motto: black-and-white comic Spartans. (Matthew)
- 2026-10-31: Add a social layer (profiles, follows, derived feed, legion pages with invite + deposit) and the Lab
  (plain-English backtesting chat). Anyone can open a legion in sim/paper; testnet needs the admin API until wallet auth.
- 2026-10-31: First host is a Mac mini with launchd + Tailscale Funnel; Render/Fly later once the GitHub repo exists.
- 2026-10-31: Database is Supabase Postgres (project `koinon`). SQLite stays for local demos.
- 2026-10-31: Builder code = a dedicated wallet, not Matthew's personal account (public address, company revenue,
  must stay in standard mode). Fee 0.03%.
- 2026-10-31: We do not install or operate VPNs to get around Hyperliquid's jurisdiction block, and we need an
  entity / eligibility answer for the US-person question before the Imran call.
- 2026-10-30: Build the "agent exchange layer" idea (risk-sandboxed hosted execution + SDK + public leaderboard,
  builder-code revenue) rather than cross-venue portfolio margin, which overlaps an existing company Matthew spoke with.
- 2026-10-30: FastAPI >= 0.118 runs yield-dependency teardown after the response; DB sessions use a function-scoped
  dependency (`DbDep`) so commits land before the next request. Lost-update bug found in pool accounting.
- 2026-10-31: iMessage route. Matthew wants the legion to feel like friends in a group chat: someone says a thesis, a friend
  thumbs it up, "$50 each", the rule trades and the result comes back to the chat. Options weighed: (1) iMessage app extension
  (Xcode, Apple Developer account, App Review for anyone outside our devices; shows cards in the thread; Simulator demo works
  without review), (2) Messages for Business (needs an approved provider, not for friend groups), (3) paid relay APIs
  (Sendblue, LoopMessage: work, cost per message, third party sees every message), (4) a Mac-side bridge on the mini reading
  chat.db and sending with AppleScript, (5) Shortcuts automations (run on one person's phone only). Chosen: the bridge (4) plus
  link previews, because it works in any existing group chat with no app install, the mini is already always-on, and the
  engine is transport-agnostic (`backend/app/huddle.py`), so an iMessage extension later reuses it. The web group chat at
  `#/huddle/<name>` is the same engine for demos without a phone. Pledges are paper only; with real money each person stakes
  into the vault themselves.
