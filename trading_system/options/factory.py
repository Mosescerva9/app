"""Build the option-chain provider from settings. Mock stays the offline default."""

from __future__ import annotations

from trading_system.config import Settings
from trading_system.data.base import MarketDataProvider
from trading_system.options.chain import MockOptionChainProvider, OptionChainProvider


def build_option_chain_provider(
    settings: Settings,
    market_data: MarketDataProvider | None = None,
) -> OptionChainProvider:
    if settings.market_data_provider != "webull":
        return MockOptionChainProvider()

    data_client = getattr(market_data, "data_client", None)
    from trading_system.options.webull_chain import WebullOptionChainProvider

    return WebullOptionChainProvider(
        data_client=data_client,
        app_key=settings.webull_app_key,
        app_secret=settings.webull_app_secret,
        region=settings.webull_region,
        api_endpoint=settings.webull_api_endpoint,
    )
