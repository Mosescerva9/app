"""Market data provider factory."""

from __future__ import annotations

from trading_system.config import Settings
from trading_system.data.base import MarketDataProvider
from trading_system.data.mock import MockMarketDataProvider
from trading_system.data.webull import WebullMarketDataProvider


def build_market_data_provider(settings: Settings) -> MarketDataProvider:
    provider = settings.market_data_provider
    if provider == "mock":
        return MockMarketDataProvider()
    if provider == "webull":
        return WebullMarketDataProvider(
            app_key=settings.webull_app_key,
            app_secret=settings.webull_app_secret,
            region=settings.webull_region,
            api_endpoint=settings.webull_api_endpoint,
        )
    raise ValueError(f"Unknown MARKET_DATA_PROVIDER={provider!r} (use mock|webull)")
