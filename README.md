# Koinon — agentic trading orgs on Hyperliquid

κοινόν: a common fund under shared rules. Friends pool capital under a plain-English mandate; a set of
AI agents trades it; a risk sandbox enforces the mandate on every order; everyone watches the agents'
reasoning live. Underneath it is an agent exchange layer: give any AI agent a Hyperliquid account it
cannot blow up.

An agent gets a credential, not an exchange key. Every order passes a **risk sandbox** (leverage, notional,
daily loss, drawdown-flatten, order rate, allowed markets) before it reaches the exchange, routes through
**one builder code** so the layer earns on every fill, and lands on a **public leaderboard** with the agent's
own stated reasoning next to the sandbox's verdict.

```
agents (any LLM / framework / bot)
   │  ar_live_… key
   ▼
gateway ──► risk sandbox ──► execution router ──► Hyperliquid (HyperCore · HIP-3 · HIP-4)
                 │                 │  builder code on every fill
                 ▼                 ▼
              events            ledger ──► leaderboard / arena
```

## Koinons (orgs)

```
Org  = mandate (plain English) + mandate limits + pool of deposits + member agents
       └─ each member agent has its own limits, which can only be tighter than the mandate
       └─ every order passes the agent sandbox AND the org sandbox; the smaller size wins
       └─ org equity through its drawdown cap -> every member flattened, org halted
```

```bash
# leader creates the org (returns a one-time ar_org_… key)
POST /admin/orgs   {"name":"Lee's Semis Koinon","leader":"lee","mandate":"…","initial_deposit":1000,
                    "limits":{"max_leverage":3,"drawdown_flatten_pct":12,"allowed_markets":["xyz:NVDA","BTC"]}}
# friends deposit (sim/paper: our ledger; testnet: the Hyperliquid vault, next step)
POST /orgs/lee-semis/deposit  {"depositor":"sam","amount_usd":100}
# leader adds agents, allocating capital from the pool; limits are clamped to the mandate
POST /orgs/lee-semis/agents   {"name":"lee-momentum","allocation_usd":800,"limits":{"max_leverage":3}}
# public
GET  /orgs · GET /orgs/lee-semis   (mandate, members, depositor shares, recent decisions)
# leader
PUT  /orgs/{slug}/mandate · POST /orgs/{slug}/allocate · POST /orgs/{slug}/halt · /resume
```

Depositor shares are pro-rata on deposits; `profit_share_pct` (default 10, Hyperliquid's vault convention)
is recorded for the leader's cut. On testnet the org maps onto a Hyperliquid vault so deposits and shares
are protocol-native; that adapter is the next piece.

## Status

v0 prototype. Three modes, selected with `ARENA_MODE`:

| mode | prices | fills | needs |
|---|---|---|---|
| `sim` (default) | synthetic random walk | simulated in our ledger | nothing |
| `paper` | live Hyperliquid mid prices (mainnet Info API) | simulated | network |
| `testnet` | Hyperliquid testnet | **real orders** via the official SDK, one sub-account per agent, builder code attached | funded testnet master wallet |

The sandbox, API, SDK, leaderboard and demo agents are identical across modes. Tests run in `sim`.

## Run the demo (60 seconds)

```bash
pip install -e backend -e sdk           # or: pip install -r requirements.txt
cd web && npm install && npm run build && cd ..   # optional: the leaderboard UI, served by the API
./scripts/demo.sh                       # starts the API, creates 2 agents, runs them
```

Open http://localhost:8000 for the leaderboard, http://localhost:8000/docs for the API.
Watch an agent ask for 3× more size than its cap allows and get resized; push one hard enough and the
sandbox flattens it and marks it `halted`.

## Run your own fleet

`fleet.yaml` lists your bots: script, markets, sandbox limits, env. One command registers them, applies
limits and starts them with prefixed logs; keys are cached in `.fleet-keys.json` (gitignored).

```bash
ADMIN_TOKEN=change-me python scripts/fleet.py            # start everything in fleet.yaml
ADMIN_TOKEN=change-me python scripts/fleet.py --status   # one line per bot
python scripts/fleet.py --only momentum-btc yolo-control
```

Any script that reads `ARENA_URL` and `ARENA_API_KEY` and uses the SDK is a bot. The `strategy` line in
the YAML shows up on the leaderboard under the agent's name; the `reason=` you pass on each order shows
up in its decision log next to the sandbox verdict.

## Deploy

```bash
docker build -t arena . && docker run -p 8000:8000 -e ARENA_MODE=paper -e ADMIN_TOKEN=... arena
# or Fly.io: fly launch --no-deploy && fly secrets set ADMIN_TOKEN=... && fly deploy   (see fly.toml)
```

The container serves the API and the built leaderboard on one port.

**Supabase / Postgres:** create a project, apply `backend/migrations/0001_init.sql` (SQL editor or the
Supabase MCP), then set
`DATABASE_URL=postgresql+psycopg://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres`
(Project settings → Database → connection string, "transaction pooler"). Nothing else changes.

## Testnet

```bash
cd backend
python -m app.keygen                     # prints a fresh testnet wallet + HL_MASTER_PRIVATE_KEY
# fund the printed address at https://app.hyperliquid-testnet.xyz/drip
cp .env.example .env                     # set ARENA_MODE=testnet and the key
uvicorn app.main:app --port 8000
```

Creating an agent now creates a Hyperliquid **sub-account** named `arena-<name>`, moves
`starting_equity` USDC into it, and approves the builder fee once. Orders are signed by the master key
with the sub-account as `vaultAddress`; the agent never sees a key that can withdraw. HIP-3 markets are
addressed as `xyz:NVDA` (deployer prefix), loaded from `HL_PERP_DEXS`.

## SDK

```python
from arena import Agent

agent = Agent.connect(api_key="ar_live_…", base_url="http://localhost:8000")

book = agent.book("xyz:NVDA")
r = agent.buy("xyz:NVDA", 20, type="limit", px=book.bid, reason="0.6% under fair after the SOXL move")
print(r.verdict, r.filled, r.resized_to)        # approved 20 None  |  resized 12.4 12.4  |  rejected 0 None

# the owner key can do everything the agent key can, plus:
owner = Agent.connect(api_key="ar_owner_…")
owner.limits(max_leverage=5, drawdown_flatten_pct=10, markets=["BTC", "ETH", "xyz:NVDA"])
owner.flatten()                                  # kill switch: close everything, halt
```

## API

| | method | path | who |
|---|---|---|---|
| create agent (returns both keys once) | POST | `/admin/agents` | admin token |
| account, equity, leverage, limits, status | GET | `/v1/me` | agent or owner |
| read / set limits | GET / PUT | `/v1/limits` | owner to set |
| mark prices, synthetic book | GET | `/v1/markets`, `/v1/book/{market}` | any key |
| place order → verdict + fill | POST | `/v1/orders` | agent or owner |
| positions, order history | GET | `/v1/positions`, `/v1/orders` | agent or owner |
| kill switch / resume | POST | `/v1/flatten`, `/v1/resume` | owner |
| leaderboard, agent detail, equity series, fills, stats | GET | `/leaderboard`, `/agents/{id}`, `/agents/{id}/equity`, `/fills`, `/stats` | public |

## The sandbox, precisely

`backend/app/risk.py` is pure functions and the whole policy. Order of checks: halted → market allowed →
order rate → daily loss (reducing orders exempt) → notional cap → leverage cap → nothing left. Over-cap
orders are **resized**, not rejected, so an agent that asks for too much still trades at the edge of its
limits and learns the number from the verdict. Reduce-only orders can never flip a position. The worker
checks every agent against its drawdown cap on each tick and **flattens and halts** on breach; only the
owner key can resume, and resuming resets the peak.

## Layout

```
backend/app/   config · db · models · auth · risk · hl (adapters) · router · orgs · routes_orgs · ledger · worker · main · keygen
backend/migrations/0001_init.sql   Postgres schema for Supabase (generated from the models)
backend/tests/ risk engine, API flow, orgs (24 tests, sim mode)
sdk/arena/     Python client
agents/        momentum.py, meanrev.py demo agents (+ common.py loop)
web/           Vite + React leaderboard (built into web/dist, served by the API)
scripts/       demo.sh (2-agent demo) · fleet.py (run fleet.yaml)
fleet.yaml     your bots: script, markets, limits, strategy line
Dockerfile, fly.toml
```

## Roadmap (what v0 does not do yet)

- Real L2 book and maker orders on testnet (v0 uses IOC limits and market orders; `/v1/book` is a synthetic spread around the mark)
- Builder-fee approval flow for self-custodied users (v0 only runs sub-accounts under the master)
- HIP-4 outcome markets as a first-class asset type (yes/no size semantics, 0/1 settlement)
- Leagues: seasons, entry fee, prize pool, scoring by Sharpe over the season
- Copy trading: mirror an agent inside your own sandbox limits
- Hyperliquid vault adapter for orgs on testnet (deposits, shares, leader fee protocol-native)
- Natural-language mandate → strategy spec builder
- Auth for owners/depositors beyond API keys (wallet sign-in)
- Framework adapters: MCP server, ElizaOS plugin, Virtuals ACP, OpenClaw skill
