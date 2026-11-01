# Handoff (written 2026-11-01, for the session that picks this up next)

## Update, 2026-11-01

Private account route repair: the simplified frontend had discarded the connection and trade-review links still issued by Telegram. The two private screens are restored without adding public navigation. Browser fixtures cover link preservation/reload, ownership click gating, owner changes, missing/expired links, public API destination, prepared-trade reloads and leaving during preparation. An isolated running API/database trace confirms actual issued links render the correct private records. No real wallet was connected and no trade was signed or submitted. Live acceptance still needs the bot and its issuing API available together; local-only links do not work for remote participants.

Goal audit: at the start of the 12-hour product goal the MacBook bot and its API on port 8001 were stopped after the separate Telegram-card deployment. No token was present in the remaining test API process or this shell. Restoring the bot needs private token entry; never print credentials or reset its databases/checkpoints. The homepage preview runs at port 4374; private account screens are previewed at port 4375. The other session installed `com.protoss.telegram`, but it is stopped with exit 126 and repeated macOS operation-not-permitted errors; its private token file is absent. Do not start a competing poller. PRs #10 and #11 are merged; the public XMR request completes, while the newer backend code still needs deployment. A subsequent research audit found date-only event timestamps can cause entries before publication; study validity is not established and needs correction.

The older runtime checklist below is historical. PR #8 is merged; the user confirmed replies in both private Telegram messages and the group. The bot is now an administrator of the upgraded supergroup. Do not repeat the admin setup or reset the delivery checkpoint.

The fourth idea is research from an episode or specific claim, not a default NVDA purchase. The correction asks for that evidence before a trade card is created. Explicit market/direction release-date backtests remain available and are labeled as release-date studies, not transcript analysis. Podcast monitoring and transcript analysis are still not connected.

Before the later stop, the MacBook bot ran from `~/protoss-demo` under `scripts/telegram_demo.py` with its API on port 8001. A separate session restarted this wrapper after the independent bridge setup described in the runbook. The observed API reports copies mode with `telegram_live_enabled=false`; no runtime or trading settings were changed for this research correction. Inspect the live processes and checkpoint before any restart. PR #9 (`bot-visual`) has merged; preserve its chart cards, link changes, and one-day XMR hold. The Mac mini API is still older than main and has not been updated from this MacBook.

Read `CLAUDE.md` and `brain/INDEX.md` first. This page is the state of the repo today. Memory about Matthew himself lives in
his Claude memory and follows him.

## What Protoss is
Friends say a trading idea in a Telegram group. Protoss tests it on real Hyperliquid history, then each person picks their own
amount and the order goes out from their own account; the money is never combined. The demo is **four ideas** (see
[[decisions]] 2026-11-01): XMR on hacks, robots to Unitree, short the Anthropic bubble, NVDA on each new Dwarkesh episode.
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
