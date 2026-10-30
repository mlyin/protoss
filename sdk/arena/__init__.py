"""arena — give any agent a Hyperliquid account it cannot blow up.

    from arena import Agent
    agent = Agent.connect(api_key="ar_live_…", base_url="http://localhost:8000")
    agent.order("BTC", side="buy", size=0.1, reason="momentum breakout")
"""
from .client import Agent, ArenaError, Book, OrderResult, Position

__all__ = ["Agent", "ArenaError", "Book", "OrderResult", "Position"]
__version__ = "0.1.0"
