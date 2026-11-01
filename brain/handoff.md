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
- Website (`web/src/IdeaChat.jsx`, `AccountWorkspace.jsx`): Home shows the four ideas; each shows its backtest card, verdict and
  events from `web/public/ideas` (written by `scripts/idea_snapshots.py` on live candles, dated; rerun it to refresh), with
  Run it now (live Lab) and Trade it in Telegram. Friends & positions shows the group's two accounts (lando, second) from
  Hyperliquid, then the visitor's own connected wallet. Run it now on protoss.trade calls the mini's Lab, which still runs old
  code: it works once the mini runs main.
- Telegram bot (@ProtossTradingDemoBot): a launchd agent on Matthew's MacBook, `com.protoss.telegram`
  (`deploy/macbook/install_telegram.sh`), running from `~/Documents/protoss2` (the working copy: a fix goes live on
  `launchctl kickstart -k gui/$(id -u)/com.protoss.telegram`). It waits for `~/.protoss/telegram.env` (TELEGRAM_BOT_TOKEN, mode
  600, written by Matthew; never read it). Group "protoss beta testing" became a supergroup when the bot was made admin: chat id
  -1004329810936. Log: `~/.protoss/telegram-live.log`. Python comes from `~/protoss-demo/.venv`; needs `web/dist` built.
  In the chat: cards are a chart image with a plain verdict; "show the events" or the button lists an event rule's events;
  status shows live P&L; copies are numbered from 1001; the bot calls `POST /huddle/tick` every minute (closes holds, reads the
  hack and Dwarkesh feeds).
- Mac mini (user `aaaa`): API and fleet under launchd from `/Users/aaaa/protoss` on `claude/project-thread-495i0w` with a large
  uncommitted tree (huddle, onboarding, a data-quality gate that refuses incomplete history, iOS). On no remote. The live Lab
  runs that code, so it still fails long windows until the mini runs main.
- MacBook clone: `~/Documents/protoss2`. Node there is 18; run Playwright with a temporary Node 20
  (`npx -y -p node@20 -c 'command -v node'`, then that node on `node_modules/@playwright/test/cli.js test`).
- Supabase project `koinon` (ref hgegigtdjkkclexqnuoy): migrations 0001 to 0004 applied, RLS on.

## Waiting on Matthew
1. Save the bot token once: `read -rs "T?Bot token: " && mkdir -p ~/.protoss && umask 077 && printf 'TELEGRAM_BOT_TOKEN=%s\n' "$T" > ~/.protoss/telegram.env && unset T`.
   The launchd agent starts the bot within 5 seconds.
2. Mac mini: commit and push the dirty `/Users/aaaa/protoss` tree to a branch, then run main there (`protossctl restart`), so the
   live Lab gets the bar-size fix and the four ideas. Stop the demo fleet (`protossctl`), nothing shows it any more.
3. Builder wallet: a separate standard-mode Hyperliquid account with >= 100 USDC; address in `HL_BUILDER_ADDRESS`.
4. Keys when ready: `PRIVY_APP_ID`, `ONRAMP_MOONPAY_KEY/SECRET/WEBHOOK_KEY`, `ONRAMP_COINBASE_APP_ID`.
5. X thread in `brand/x-thread.md`: drafted, his to post.

## Open threads, in order
1. With the token saved: run the four ideas in the group from a phone, one real stake per account, and check the fills show in the chat and on Friends & positions.
2. Move the bot onto the mini next to the API so its links can be public (`APP_URL`), instead of a laptop terminal.
3. Mini: merge its uncommitted tree onto main (overlaps `backend/app/backtest.py`, `huddle.py` and the Lab tests).
4. Lab: refresh `backend/app/data/dwarkesh.csv` (`scripts/podcast_dates.py`) and the candle cache on a schedule.
5. agent-desktop (Chris Tate) evaluation on the minis; harness loop for routine tasks (`harness/README.md`).

## Rules that do not change
Shell and files only, never his screen. Never move money or sign with his keys. Keys never in chat, commits or the brain.
Copy follows `brain/voice.md`; UI follows `brain/design.md`. GREEN before done, and test what the site offers against the live
API. Commits end with the attribution trailer.
