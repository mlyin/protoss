"""Runtime configuration. Everything comes from environment variables (or a .env file).

ARENA_MODE
  sim      synthetic prices, simulated fills, no network. Default. Good for tests and demos anywhere.
  paper    real Hyperliquid prices (Info API), simulated fills and ledger. Needs network, no funds.
  testnet  real orders on Hyperliquid testnet via the official SDK. Needs HL_MASTER_PRIVATE_KEY
           funded with testnet USDC; each agent gets its own sub-account.
  mainnet  mainnet vault accounts; execution is off unless MAINNET_TRADING_ENABLED=true.
  copies   mainnet, one API wallet per participant (copies.py); each order leaves that person's own account.
           Off unless MAINNET_TRADING_ENABLED=true. Wallets come from ~/.protoss/wallets.json (scripts/wallets.py).
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    arena_mode: Literal["sim", "paper", "testnet", "mainnet", "copies"] = "sim"
    mainnet_trading_enabled: bool = False
    telegram_live_enabled: bool = False  # browser-signed, independent orders; server has no signing role

    @model_validator(mode="after")
    def check_network(self):
        if self.telegram_live_enabled and self.arena_mode not in ("sim", "paper"):
            raise ValueError("browser wallet review must run separately from server-side exchange execution")
        expected = {"testnet": "https://api.hyperliquid-testnet.xyz", "mainnet": "https://api.hyperliquid.xyz", "copies": "https://api.hyperliquid.xyz"}
        if self.arena_mode in expected and self.hl_api_url and self.hl_api_url.rstrip("/") != expected[self.arena_mode]:
            raise ValueError(f"{self.arena_mode} requires {expected[self.arena_mode]}")
        if self.arena_mode in ("mainnet", "copies") and self.admin_token == "change-me":
            raise ValueError("mainnet requires a configured ADMIN_TOKEN")
        return self
    database_url: str = "sqlite:///./arena.db"
    admin_token: str = "change-me"
    redirect_legacy_frontend: bool = False  # enable only after Pages /app/ is verified

    # Hyperliquid
    hl_master_private_key: str | None = None
    hl_api_url: str | None = None  # defaults to testnet URL in testnet mode, mainnet in paper mode
    hl_builder_address: str | None = None  # defaults to the master address in testnet mode
    hl_builder_fee_tenths_bp: int = 30  # 30 tenths of a bp = 3 bp = 0.03% per fill
    hl_perp_dexs: list[str] = Field(default_factory=lambda: ["xyz"])  # HIP-3 dexs to load markets from

    # Sandbox defaults applied to a new agent
    default_max_leverage: float = 5.0
    default_max_notional_usd: float = 150_000.0
    default_daily_loss_pct: float = 4.0
    default_drawdown_flatten_pct: float = 10.0
    default_max_orders_per_min: int = 30
    default_allowed_markets: list[str] = Field(default_factory=lambda: ["BTC", "ETH", "SOL", "HYPE"])

    # Fees (exchange side; builder fee is separate)
    taker_fee_bps: float = 4.5
    maker_fee_bps: float = 1.5

    # Worker
    tick_seconds: float = 5.0
    snapshot_seconds: float = 60.0

    # Sim market universe: symbol -> seed price
    sim_markets: dict[str, float] = Field(
        default_factory=lambda: {
            "BTC": 112_000.0,
            "ETH": 3_850.0,
            "SOL": 190.0,
            "HYPE": 89.0,
            "XMR": 330.0,
            "xyz:NVDA": 214.0,
            "xyz:ANT": 111.0,  # synthetic demo seed; never presented as a live quote
            "xyz:TSLA": 420.0,
            "xyz:SP500": 6_900.0,
            "xyz:SOXL": 41.0,
        }
    )
    sim_vol_per_tick: float = 0.0015  # 0.15% per tick, roughly crypto-like at 5 s ticks

    # Join with card (onboard.py). Keys are publishable/secret pairs from the partner dashboards; never commit them.
    public_url: str = "https://protoss.trade"
    privy_app_id: str | None = None  # embedded wallets in the browser; the key never leaves the user's device
    onramp_moonpay_key: str | None = None  # publishable key (pk_live_...)
    onramp_moonpay_secret: str | None = None  # signs hosted-checkout URLs that carry a wallet address
    onramp_moonpay_webhook_key: str | None = None  # wk_live_...; verifies Moonpay-Signature-V2 on /onboard/webhooks/moonpay
    onramp_moonpay_currency: str = "usdc_arbitrum"  # usdc_hypercore once MoonPay Gateway is enabled on the account
    onramp_coinbase_app_id: str | None = None  # Coinbase Onramp project id; URLs also need a session token (see onboard.py)
    onboard_min_usd: float = 20.0
    # Huddle (huddle.py): the group chat that turns a thesis into a backed, staked rule
    app_url: str = "https://app.protoss.trade"  # where links in chat messages and link previews point
    huddle_quorum: int = 2  # people backing a thesis, author included, before it arms
    huddle_max_pledge_usd: float = 1_000.0  # per person per thesis, paper money
    huddle_hack_feeds: list[str] = Field(default_factory=list)  # RSS/Atom URLs read for hack headlines; empty = off
    # podcast feeds whose new episodes fire "Dwarkesh is always right" rules (read outside sim mode only)
    huddle_podcast_feeds: list[str] = Field(default_factory=lambda: ["https://api.substack.com/feed/podcast/69345.rss"])
    onboard_blocked_regions: list[str] = Field(default_factory=lambda: ["US"])  # ISO 3166-1 alpha-2; perps are not offered here


@lru_cache
def get_settings() -> Settings:
    return Settings()
