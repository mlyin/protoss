# Protoss demo: two accounts, two separate trades

The website and Telegram use the same practice engine. Each person confirms their own amount and
gets a separate practice account and fill. Money is not pooled. Neither demo places a real order.
The browser's You / Your friend buttons are demo roles. Telegram uses two allowlisted numeric user IDs.

The default crypto example is 60% Bitcoin and 40% Ethereum. The complete percentage split is shown before
confirmation and kept with each copy. These are Hyperliquid perpetual markets, not ownership of BTC or ETH.
Each participant confirms their own practice amount. Copying version 1 does not authorize future changes.

## Install the demo in a separate folder on the Mac

Once the branch is available on GitHub, run these commands in Terminal. Keep your existing live checkout running.

```sh
git -C ~/protoss fetch origin codex/anthropic-imessage-e2e
git -C ~/protoss worktree add ~/protoss-demo origin/codex/anthropic-imessage-e2e
cd ~/protoss-demo
python3 -m venv .venv
.venv/bin/pip install -r requirements-demo.txt
cd web
npm ci
npm run build
cd ..
```

The demo needs Python 3.11 or newer and Node/npm. If `~/protoss-demo` already exists, use another new folder name.

## Try the website first

```sh
.venv/bin/python scripts/telegram_demo.py --web-only
```

Open http://127.0.0.1:8001/#/demo on the same computer. Pick Crypto starter, click Test this idea,
review the 60/40 split and confirm $20 as You. Switch to Your friend and confirm $50. The two result
cards each show independently simulated BTC and ETH fills. A small allowance is left for trading costs.
Share this demo copies the room link; the other browser must be able to reach the same host.
Stop with Ctrl-C before running the Telegram version on the same port.

## Connect the Telegram bot

The easiest route after installation is the guided setup:

```sh
.venv/bin/python scripts/telegram_demo.py --setup
```

Paste the bot token into the hidden terminal prompt. The setup prints your bot's username. Add that bot
and both accounts to a private Telegram group, send the displayed `/help@YOUR_BOT_USERNAME` command from
each account, then press Enter in Terminal. The setup finds and pins the group and two human user IDs,
then starts the isolated practice server and bridge. The token stays in process memory and is not saved.
If you prefer to enter the IDs yourself, use the manual route below.

1. Create a private group. Add your two Telegram accounts and the bot. Keep bot privacy mode on.
2. In that group, send `/help@YOUR_BOT_USERNAME` once from each account. Replace the username with the bot's real username.
3. Load the token locally. Do not paste it into chat, put it into a command argument or commit it.

In Terminal, enter `bash`, then:

```sh
cd ~/protoss-demo
read -r -s -p 'Telegram bot token: ' TELEGRAM_BOT_TOKEN
export TELEGRAM_BOT_TOKEN
.venv/bin/python scripts/telegram_bridge.py inspect
```

Paste the token at the hidden prompt, then press Enter. `inspect` prints the bot username and pending
numeric chat/user IDs. It sends no messages. Pick the negative group `chat_id` and the two positive
`user_id` values. The bot must have no webhook; use this dedicated demo bot rather than removing an
unrelated application's webhook. Do not run two pollers against the same bot.

Start with those IDs substituted:

```sh
.venv/bin/python scripts/telegram_demo.py --chat -100123456789 --users 111111111,222222222
```

The wrapper starts an isolated sim API on port 8001, with a separate SQLite database in
`~/.protoss/telegram-practice.db` and an ephemeral admin credential. It forces live execution off.
It does not change the live server's environment. First startup skips old Telegram commands.

## Send fresh commands after the bridge says it is running

From the first Telegram account:

```text
/demo
/idea buy and hold 60% BTC and 40% ETH
/pledge 20
```

From the second:

```text
/back 1
/pledge 50
```

`/demo` shows crypto example buttons; tapping the 60/40 button replaces typing the `/idea` command.
Do one or the other to create a single idea. You can tap Back this idea instead of `/back 1`. Idea numbers increase on later runs; use the number
on the current card. After both participants confirm amounts, expect two separate practice-fill
receipts: a BTC/ETH copy with a $20 practice budget for the first account, and a separate BTC/ETH copy
with a $50 budget for the second. The exact fill values can be smaller because of costs. Same display names do not merge the accounts.
`/status` shows the ideas and wallet connections. `/help` lists commands. Plain messages are ignored.

## Optional: prove that each participant controls their wallet

Each participant sends `/join` in the group, taps Connect my wallet privately and presses Start
in the private bot conversation. The bot sends a personal connection link that expires in 15 minutes.
Open it in a browser with the wallet extension, or a supported wallet browser, and sign the ownership
message. The message contains the Telegram user ID, group, nonce and expiry. It authorizes no deposit
or trade. One wallet cannot be claimed by both participants in this demo group.

Default links point to localhost and work on the Mac running the demo. For phones or remote browsers,
serve the practice API through a separate public HTTPS tunnel and set `DEMO_PUBLIC_URL` to that URL
before starting. Do not repoint the production tunnel. Telegram's in-app browser may not expose an
Ethereum wallet; use a wallet browser or the desktop extension. Keep personal connection links private.

Wallet ownership is distinct from verified funding. No copy is executed against a real wallet. Mainnet
copy execution needs separate per-account authorization and exchange-fill reconciliation before it can
be described as working. The existing shared-vault adapter is a different product path.

## Reliability and scope

- Only the selected group and two allowlisted users can drive the bridge. No anonymous channel posts.
- Incoming Telegram update IDs are deduplicated before applying a pledge. Restart checkpoints live in `~/.protoss/`.
- Outgoing chunks are checkpointed before acknowledging the API outbox. A crash between Telegram accepting
  a send and the local checkpoint can duplicate a receipt; Telegram sendMessage has no idempotency key.
- The website uses the same idea/backing/copy engine, in its own browser demo room. It is not a live mirror of the Telegram group.
- Basket history uses overlapping candles for every asset, includes estimated fees/slippage, and does not model funding. It does not rebalance automatically. Unknown assets or invalid percentages are rejected rather than silently substituted.
- Cryptographic wallet checks are tested locally. Live Telegram delivery still requires your token and the two accounts.
