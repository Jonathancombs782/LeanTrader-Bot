"""Tradable asset universe for the paper-trading brain.

The universe is just a list — swap it for any set of assets. BLUE_CHIPS is the
default seed (Jonathan's personal watchlist); whether it stays the bot's
universe is his call.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Asset:
    symbol: str          # e.g. "SOL"
    name: str            # e.g. "Solana"
    coingecko_id: str | None  # None => no public price feed mapping yet
    tier: str = "mid"    # "major" | "mid" | "small" — drives slippage


BLUE_CHIPS: list[Asset] = [
    Asset("BTC", "Bitcoin", "bitcoin", "major"),
    Asset("ETH", "Ethereum", "ethereum", "major"),
    Asset("SOL", "Solana", "solana", "major"),
    Asset("XRP", "XRP", "ripple", "major"),
    Asset("LINK", "Chainlink", "chainlink", "major"),
    Asset("UNI", "Uniswap", "uniswap", "major"),
    Asset("USDC", "USD Coin", "usd-coin", "major"),
    Asset("PAXG", "PAX Gold", "pax-gold", "major"),
    Asset("XAUT", "Tether Gold", "tether-gold", "major"),
    Asset("HBAR", "Hedera", "hedera-hashgraph", "mid"),
    Asset("HNT", "Helium", "helium", "mid"),
    Asset("ONDO", "Ondo Finance", "ondo-finance", "mid"),
    Asset("SUI", "Sui", "sui", "mid"),
    Asset("TAO", "Bittensor", "bittensor", "mid"),
    Asset("XMR", "Monero", "monero", "mid"),
    Asset("ZEC", "Zcash", "zcash", "mid"),
    Asset("HYPE", "Hyperliquid", "hyperliquid", "mid"),
    Asset("ARB", "Arbitrum", "arbitrum", "mid"),
    Asset("AZTEC", "Aztec", None, "small"),   # no stable feed mapping yet
    Asset("ESP", "Espresso", None, "small"),  # no stable feed mapping yet
]


def by_symbol(symbol: str, universe: list[Asset] = BLUE_CHIPS) -> Asset:
    for asset in universe:
        if asset.symbol == symbol:
            return asset
    raise KeyError(f"{symbol} not in universe")
