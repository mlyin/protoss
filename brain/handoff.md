# Handoff (written 2026-11-01, for the session that picks this up next)

Read `CLAUDE.md` and `brain/INDEX.md` first. This page is the state of the repo today. Memory about Matthew himself lives in
his Claude memory and follows him.

## What Protoss is
Friends share a trading idea in a group chat. Each person picks their own amount and approves from their own wallet; the
money is never combined (Matthew, 2026-10-31, see [[decisions]]). The pooled **legion** (code says `org`; do not rename)
and vault-backed legions still exist in code. Every fill is public. Revenue: a builder code on every fill. The **Lab**
answers plain-English backtest questions. **Join with card** gets a person from fiat to a stake.

## Where things are (2026-11-01)
- Live: https://protoss.trade (GitHub Pages from `docs/`, cert approved), https://app.protoss.trade and
  https://api.protoss.trade (Cloudflare Tunnel to the mini, paper mode, ~1070 markets),
  https://aaaas-mac-mini.tailb9b0ef.ts.net (Tailscale Funnel, same API).
- Repo: github.com/mlyin/protoss. `main` is e62a51d plus whatever lands from the open PRs below.
- Open PRs, in the order they were opened:
  - #1 `claude/project-thread-495i0w` and #2 `codex/anthropic-imessage-e2e` (draft): superseded by #4, close them once #4 lands.
  - #3 `codex/pages-consolidation`: homepage and app from one React build in `web/`, app at `/app/`, API at
    api.protoss.trade, Playwright in the Pages workflow. Notes in `brain/pages-deployment-2026-11-01.md` on that branch.
  - #4 `integrate/2026-11-01`: everything backend, scripts, iOS and brain from #1 and #2, plus the 34-market candle cache and
    the Lab dip study. Leaves `web/` to #3 except `web/src/hlsign.js` (newer than #3's copy; backend tests check it).
    Against #3 only `.gitignore` (keep both) and `hlsign.js` (keep #4's) conflict. Either can land first.
- Mac mini (user `aaaa`): API and fleet run under launchd from `/Users/aaaa/protoss` on `claude/project-thread-495i0w`
  **with a large uncommitted tree** (huddle, onboarding, data-quality gate, iOS edits) that is on no remote. The release
  checkout for #3 is `/Users/aaaa/protoss-pages`. Do not pull main over the running checkout until that tree is committed.
- MacBook: `~/Documents/protoss2` is a clone (no launchd services). No SSH or Tailscale CLI from here to the mini.
- Supabase project `koinon` (ref hgegigtdjkkclexqnuoy): migrations 0001 to 0004 applied, RLS on.

## Waiting on Matthew
1. On the mini: commit and push the dirty `/Users/aaaa/protoss` tree to a branch (a session there, or
   `git -C ~/protoss switch -c mini/wip-2026-11-01 && git -C ~/protoss add -A && git -C ~/protoss commit -m wip && git -C ~/protoss push -u origin HEAD`
   after checking `git status` for anything that should not be committed). Until then that work exists in one place.
2. Merge #4 and #3 (or say which one waits).
3. Builder wallet: a separate standard-mode Hyperliquid account with >= 100 USDC; its address goes in `HL_BUILDER_ADDRESS`.
4. Keys in the mini's `backend/.env`, then `protossctl restart`: `PRIVY_APP_ID`, `ONRAMP_MOONPAY_KEY/SECRET/WEBHOOK_KEY`
   (currency `usdc_hypercore` once MoonPay Gateway is on), `ONRAMP_COINBASE_APP_ID`.
5. X thread in `brand/x-thread.md`: drafted, his to post.

## Open threads, in order
1. Land #4 and #3, then bring the mini's uncommitted tree onto main (it overlaps `backend/app/backtest.py` and the Lab tests).
2. Join with card: code-complete apart from keys (Privy wallet, vaultTransfer signing, signed MoonPay webhook).
3. First real trades: `scripts/trade.py` places an order from an API wallet acting for a master account; live Telegram copies
   per participant (`docs/telegram-demo.md`). Matthew runs anything that signs.
4. Lab: dip study done, tail-wallet verified on real fills, 34 markets cached. Next: refresh the cache on a schedule (the mini's
   data-quality gate rejects stale history), an hourly cache for the last 208 days if hourly questions matter.
5. agent-desktop (Chris Tate) evaluation on the minis; harness loop for routine tasks (`harness/README.md`).
6. Brand: the Design canvas and the old handoff doc still say Coliseum.

## Rules that do not change
Shell and files only, never his screen. Never move money or sign with his keys. Keys never in chat, commits or the brain.
Copy follows `brain/voice.md`; UI follows `brain/design.md`. GREEN before done. Commits end with the attribution trailer.
