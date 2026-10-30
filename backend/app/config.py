"""Runtime configuration. Everything comes from environment variables (or a .env file).

ARENA_MODE
  sim      synthetic prices, simulated fills, no network. Default. Good for tests and demos anywhere.
  paper    real Hyperliquid prices (Info API), simulated fills and ledger. Needs network, no funds.
  testnet  real orders on Hyperliquid testnet via the official SDK. Needs HL_MASTER_PRIVATE_KEY
           funded with testnet USDC; each agent gets its own sub-account.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    arena_mode: Literal["sim", "paper", "testnet"] = "sim"
    database_url: str = "sqlite:///./arena.db"
    admin_token: str = "change-me"

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
            "xyz:NVDA": 214.0,
            "xyz:TSLA": 420.0,
            "xyz:SP500": 6_900.0,
            "xyz:SOXL": 41.0,
        }
    )
    sim_vol_per_tick: float = 0.0015  # 0.15% per tick, roughly crypto-like at 5 s ticks


@lru_cache
def get_settings() -> Settings:
    return Settings()
