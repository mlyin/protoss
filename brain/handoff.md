# Handoff (written 2026-11-01, for the session that picks this up next)

Read `CLAUDE.md` and `brain/INDEX.md` first. This page is the state of the repo today. Memory about Matthew himself lives in
his Claude memory and follows him.

## What Protoss is
Friends say a trading idea in a Telegram group. Protoss tests it on real Hyperliquid history, then each person picks their own
amount and the order goes out from their own account; the money is never combined. The demo is **four ideas** (see
[[decisions]] 2026-11-01): XMR on hacks, robots to Unitree, short the Anthropic bubble, NVDA on every Dwarkesh episode.
**Nothing on the website is simulated** (see [[corrections]]). Revenue: a builder code on every fill. The pooled **legion**
(code says `org`; do not rename) and vault-backed legions still exist in the backend but are not on the website.

## Where things are (2026-11-01)
- Live: https://protoss.trade (Pages, built from `web/` on every push to main; app at `/app/`), https://api.protoss.trade and
  https://app.protoss.trade (Cloudflare Tunnel to the mini, paper mode). The website reads marks and positions straight from
  api.hyperliquid.xyz in the browser; research calls api.protoss.trade.
- Website (PR #6, `web/src/IdeaChat.jsx`, `AccountWorkspace.jsx`): Home shows the four ideas as chat previews with live
  Hyperliquid marks and an Open Telegram link; Friends & positions reads a connected wallet's positions on every perp dex. The
  hacks idea calls `/lab/chat` for its history test; that works once the mini runs main (daily-bar fallback, PR #7).
- Telegram bot (@ProtossTradingDemoBot): runs on Matthew's MacBook from `~/protoss-demo` in a terminal, live mode, group
  "protoss beta testing". As of 2026-11-01 00:30 it ran commit 505f4ba, which ignores plain chat, and it was a plain member with
  privacy mode on, so Telegram delivered only slash commands. Its links point to 127.0.0.1:8001 (its own local API).
- Mac mini (user `aaaa`): API and fleet under launchd from `/Users/aaaa/protoss` on `claude/project-thread-495i0w` with a large
  uncommitted tree (huddle, onboarding, a data-quality gate that refuses incomplete history, iOS). On no remote. The live Lab
  runs that code, so it still fails long windows until the mini runs main.
- MacBook clone: `~/Documents/protoss2`. Disk was full on 2026-11-01 (130 MB); keep installs lean. Node there is 18, so
  Playwright (needs 20) runs in CI only.
- Supabase project `koinon` (ref hgegigtdjkkclexqnuoy): migrations 0001 to 0004 applied, RLS on.

## Waiting on Matthew
1. Telegram: make @ProtossTradingDemoBot an admin of the group (or `/setprivacy` Disable in BotFather, then re-add it). Then in the
   bot's terminal: Ctrl-C, `git -C ~/protoss-demo fetch && git -C ~/protoss-demo switch main && git -C ~/protoss-demo pull --ff-only`,
   start it again (same command) and type LIVE.
2. Mac mini: commit and push the dirty `/Users/aaaa/protoss` tree to a branch, then run main there (`protossctl restart`), so the
   live Lab gets the bar-size fix and the four ideas. Stop the demo fleet (`protossctl`), nothing shows it any more.
3. Builder wallet: a separate standard-mode Hyperliquid account with >= 100 USDC; address in `HL_BUILDER_ADDRESS`.
4. Keys when ready: `PRIVY_APP_ID`, `ONRAMP_MOONPAY_KEY/SECRET/WEBHOOK_KEY`, `ONRAMP_COINBASE_APP_ID`.
5. X thread in `brand/x-thread.md`: drafted, his to post.

## Open threads, in order
1. Get the bot answering the four ideas in the group (item 1 above), then a real order per participant shows on Friends & positions.
2. Move the bot onto the mini next to the API so its links can be public (`APP_URL`), instead of a laptop terminal.
3. Mini: merge its uncommitted tree onto main (overlaps `backend/app/backtest.py`, `huddle.py` and the Lab tests).
4. Lab: refresh `backend/app/data/dwarkesh.csv` (`scripts/podcast_dates.py`) and the candle cache on a schedule.
5. agent-desktop (Chris Tate) evaluation on the minis; harness loop for routine tasks (`harness/README.md`).

## Rules that do not change
Shell and files only, never his screen. Never move money or sign with his keys. Keys never in chat, commits or the brain.
Copy follows `brain/voice.md`; UI follows `brain/design.md`. GREEN before done, and test what the site offers against the live
API. Commits end with the attribution trailer.
