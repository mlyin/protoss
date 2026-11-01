# Real Telegram trades, approved by each person

This flow supports separate buy positions in `xyz:ANT`, BTC, or ETH. Each person chooses $12 to $100
of position value, reviews a live quote, explicitly accepts 1× cross margin, and signs in their own
wallet. ANT is an Anthropic-linked perpetual, not shares. Exchange fees and funding are additional.
Cross margin shares collateral within the exchange account. No stop-loss, automatic exit, ongoing
copying, basket execution, deposits, or transfers are performed by this flow.

The existing `--live` command is a separate API-wallet mode from the concurrent branch work.
Use **`--wallet-review`** for the per-trade wallet approval flow described here. The flags are mutually exclusive.

## Update and start on your Mac

Stop the existing Telegram runner with Ctrl-C. Do not run two pollers for the same bot. In the actual
project folder (for example `~/protoss-telegram-demo`), after the branch has been published:

```sh
git pull --ff-only origin codex/anthropic-imessage-e2e
.venv/bin/pip install -r requirements-demo.txt
npm --prefix web ci
npm --prefix web run build
.venv/bin/python scripts/telegram_demo.py --setup --wallet-review --brand
```

The local token prompt is hidden. Send the displayed `/help@ProtossTradingDemoBot` from both accounts
when setup asks. It pins the two IDs and group. Use a fresh command after the bridge starts.
The live flow has its own SQLite database `~/.protoss/telegram-wallet-review.db` and checkpoint file. The
general practice arena remains simulated and server-side mainnet execution remains disabled.
`TELEGRAM_LIVE_ENABLED=true` enables only the separate user-signed review endpoints. The server
reads `/info`; it never receives private keys or posts to `/exchange`.

Private review links point to the Mac on port 8001 by default. Open them in a browser with the wallet
extension on that same Mac. For phones, first serve this instance through a separate HTTPS tunnel
and set `DEMO_PUBLIC_URL` to that HTTPS origin. Do not point phones at their own `127.0.0.1`, and do
not repoint an existing production tunnel. Telegram's built-in browser may not expose a wallet.

## Two people, one idea

1. In the group, one person sends `/idea@ProtossTradingDemoBot buy and hold ANT`.
2. Each account sends `/pledge@ProtossTradingDemoBot 20`.
3. Each uses their own **Review my trade privately** button and presses **Start** in the bot DM.
4. Open the private review page, connect the intended wallet, and sign the ownership message.
5. Get the current quote. Check the wallet, market, quantity, maximum cost, and 1× cross-margin terms.
6. Explicitly select the consent checkbox. Approve the 1× setting in the wallet, then separately
   approve the buy. Both signatures and exchange requests happen in the user's browser.
7. The page and `/status@ProtossTradingDemoBot` show independently verified exchange fills.

A pledge only creates a request. Nobody waits for a friend's signature, and nobody can approve for
a friend. One Telegram identity is bound to one wallet per group; the second identity must use a
different wallet. Links expire after one hour. Opening another person's group button does not grant
access to their private request. The first version refuses to add to an existing position in the
same market, so it cannot silently change leverage on that position.

The quote expires in two minutes. The buy is an immediate-or-cancel limit order with a ceiling no
more than 0.5% above the current ask. Size rounds down so price times size stays within the chosen
position budget. This can result in spending less than $20. An unfilled portion cancels immediately.

Standard accounts need enough collateral in the selected DEX. Unified accounts also display their
spot balances; Hyperliquid makes the final collateral decision. Portfolio margin and other account
modes are blocked in this first version. An API failure never falls back to generated prices.

## Interrupted approvals and verification

Preparing an order freezes its wallet, amount, price, size, expiry and unique client order ID. The
page makes at most one buy submission attempt, with no automatic resubmission. After reloading, only
verification is offered. A missing or delayed response means the result is unknown, not that the
order failed. Check Hyperliquid order history before starting a new idea. A rejected wallet prompt
may leave a prepared request without any trade. Stopping the bot does not close an exchange position.

Receipts require the exact wallet's client order ID, market, side, original size, limit price,
execution times and fills. Partial fills are labeled. Messages are queued once per verified receipt;
Telegram delivery retains the bridge's documented at-least-once crash behavior.

## Probe avatar

The native vector states are in `web/public/probe/`: `idle.svg`, `thinking.svg`, `talking.svg`,
`working.svg`, `success.svg`, and `conversation.svg`. Open `/#/probe` to preview and download them.
Edit `brand/probe.svg` and run `python scripts/build_probe_svgs.py` to regenerate exports. The React
component prefixes SVG IDs so several Probes can share a page without gradient collisions. CSS
respects reduced motion. Backtest requests drive the thinking state; the group/demo flow shows two
Probes talking; wallet/exchange requests use working; completed results use success. The animations
illustrate actual UI states and do not imply multiple AI agents or profitable results.

The website uses native Probe SVGs for its animations and favicon, with PNG/ICO exports for mobile
icons and link previews. The header and Telegram avatar use `web/public/probe.png`, the generated
cartoon Probe artwork. Set the dedicated Telegram bot's profile photo locally:

```sh
.venv/bin/python scripts/telegram_brand.py
```

Enter the bot token at the hidden prompt. The script verifies the username is
`ProtossTradingDemoBot` before uploading a JPG conversion through Telegram's `setMyProfilePhoto`.
Alternatively use BotFather `/setuserpic`, select the bot, and upload `web/public/probe.png`.
The asset being present in Git does not mean the bot profile has already been updated.

## Verification status

Automated tests use fake exchange responses and test wallets. They do not submit mainnet orders.
Read-only checks can confirm current mainnet metadata and account state. Actual wallet compatibility,
exchange acceptance, and Telegram delivery still require a user-operated acceptance run on the Mac.

## Implementation checks (October 31, 2026)

- Python suite and production web build run through `bash harness/check.sh`.
- Browser acceptance used an isolated local API with fake exchange responses and ephemeral test wallets.
  Both desktop (1440px) and mobile (390px) completed ownership verification, a frozen quote, separate
  leverage/order approvals and an exchange-verified receipt. One case exercised a partial fill.
- Exchange requests were intercepted by the test harness. Switching to a different wallet blocked
  submission. Reloading a completed request offered no buy button and sent no further order.
- Browser action hashes for orders, leverage changes and existing vault transfers match the official
  Python SDK, including action expiry. Replayed quote preparation is rejected.
- The Probe gallery was checked at both widths: unique SVG IDs, downloadable state files, reduced
  motion, and the backtest's real pending-to-result transition. No JavaScript errors or page overflow.
- Read-only mainnet quote checks reached xyz:ANT. The standard account was refused for insufficient
  DEX collateral at 1×; the unified account was recognized and returned a quote. No real order was sent.
- The concurrently added API-wallet implementation was retained. Its `--live` behavior is distinct
  from this document's `--wallet-review` option. Tests exercise both paths independently.
- PostgreSQL was not exercised in this session. Mainnet wallet prompts, orders, the Mac rollout and
  the Telegram avatar upload have not been executed by the assistant. Keep the PR draft until review.
