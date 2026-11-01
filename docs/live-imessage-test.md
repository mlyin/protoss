# Anthropic and Messages acceptance test

2026-10-31. Target: trade.xyz `xyz:ANT`, mainnet. Messages bridge on the Mac mini first.

Current boundary: Protoss supports sim, paper and testnet. Huddle pledges trade only in sim/paper.
An explicit mainnet mode is now available, with execution disabled by default. Do not override `HL_API_URL` in testnet mode to point at mainnet:
startup can sign builder approval and agent creation can transfer funds. The first live test below uses a
trade Matthew places himself on trade.xyz, with independent read-only verification. This is a staged test;
chat-to-live-order and automatic posting of real fills remain unimplemented.

## 1. Check the Mac host

Run from the checkout on the Mac mini:

```sh
cd ~/protoss
git status --short
deploy/macmini/protossctl status
curl --fail --show-error http://127.0.0.1:8000/health
.venv/bin/python scripts/imessage_bridge.py chats
```

Expected: API is up, mode is paper, and the test group appears in `chats`. If chat.db is denied, give
the Python binary Full Disk Access. If localhost works but the public app returns 403, inspect the
Cloudflare Tunnel/access configuration before changing the API. Do not expose the admin token.

## 2. Verify the market and both accounts

`scripts/live_check.py` uses only the mainnet Info API. It takes public addresses, never keys.

```sh
python3 scripts/live_check.py
python3 scripts/live_check.py --account 0xPUBLIC_ACCOUNT_ONE --account 0xPUBLIC_ACCOUNT_TWO
```

Replace the placeholder addresses. Check the returned `xyz` margin, positions, market metadata and
current price. Capture a start timestamp immediately before the manual trade:

```sh
python3 -c 'import time; print(int(time.time() * 1000))'
```

If trading a shared vault, verify the vault's public address rather than treating either depositor's
address as the trading account. HIP-3 funding and margin availability must be checked on the actual
trading account; a balance elsewhere does not establish that it can open this position.

## 3. Exercise Messages with paper money

Keep the API in paper mode. Load `ADMIN_TOKEN` locally using your existing secret setup. Use a private
test group and its exact GUID from `chats`. Set `BRIDGE_ME` to your name. Start with the existing bridge:

```sh
.venv/bin/python scripts/imessage_bridge.py run --chat 'iMessage;+;REPLACE_WITH_TEST_CHAT' --title 'Protoss test'
```

Starting the bridge enables replies into this group. Matthew runs it when ready to send. Grant the
Messages Automation prompt on the first reply. From the two participants send:

1. `protoss buy and hold xyz:ANT`
2. `in`
3. `$20 each`

Expected: a backtest card, two backers, a $40 paper allocation and a paper fill. The market needs live
price/history access from the Mac. If history is unavailable, the card must explain the failure; do not
interpret synthetic history as market evidence. These messages do not place a mainnet trade.

## 4. Place and verify the real trade

Matthew selects `ANT` on trade.xyz, reviews the displayed market/instrument, account, collateral,
side, size, leverage and price limit, then signs locally. No agent runs the signing step. Repeat with
the second account only if the test is intended to demonstrate two independent fills. For pooling,
both deposits and the subsequent vault fill must be verified separately.

After the trade, substitute the captured timestamp and real public addresses:

```sh
python3 scripts/live_check.py --account 0xPUBLIC_ACCOUNT_ONE --account 0xPUBLIC_ACCOUNT_TWO --since-ms START_TIMESTAMP --require-fill
```

Success: each supplied account has a matching `xyz:ANT` exchange fill in the window. Record the fill's
order ID, transaction hash, time, side, price and size. Exit 1 means at least one supplied account has
no matching fill. An existing position, chat pledge or submitted order is insufficient. Exchange time
queries are bounded; use a narrow window and inspect the reported fills.

## Remaining acceptance work

- Connect the Mac runtime to this session or collect its local checks.
- Observe an actual round trip through Messages.app on that host.
- Exercise the new mainnet vault adapter on the Mac after local owner setup.
- Add local wallet confirmation and fill reconciliation into the huddle.
- Verify confirmed real fills return to the correct chat, without replaying or duplicating messages.
- Build the iPhone extension separately after the bridge path works.

## Mainnet host configuration (owner runs locally)

Use a separate checkout/database for mainnet. Keep the existing paper host available for chat demos.
In the mainnet host environment set `ARENA_MODE=mainnet`, a distinct `DATABASE_URL`, a configured
`ADMIN_TOKEN`, `HL_PERP_DEXS=["xyz"]`, and `TICK_SECONDS=0` for the first manual test. Configure the
vault leader signing key only on the host. Keep `MAINNET_TRADING_ENABLED=false` during setup.
Do not paste keys into chat. Mainnet startup reads account/market data without signing builder approval.

Create the legion through the admin API with `initial_deposit=0`, allow `xyz:ANT`, then link an existing
vault with the legion owner key. Deposits happen on Hyperliquid, signed by each account holder. Add
one agent whose `allocation_usd` equals the current vault equity; cap order exposure with its notional
and leverage limits. Mainnet permits one agent per vault because separate agent attribution for a
shared position is not implemented. Ledger deposits and reallocations are disabled in mainnet.

After reviewing the vault, balances, market and limits, the owner can set
`MAINNET_TRADING_ENABLED=true` and restart that host. This enables server-side signed orders via
the authenticated agent API. It does not add a per-order browser confirmation. Leave the worker off
for the first test and submit the intended order manually from the owner-controlled machine.
No live execution or vault funding was performed in the cloud checkout.
