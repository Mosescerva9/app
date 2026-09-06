"""Build a catalyst provider from settings. Mock is the offline default."""

from __future__ import annotations

from trading_system.config import Settings
from trading_system.data.base import MarketDataProvider
from trading_system.events.base import CatalystProvider
from trading_system.events.mock import MockCatalystProvider


def build_catalyst_provider(
    settings: Settings,
    market_data: MarketDataProvider | None = None,
) -> CatalystProvider:
    choice = (settings.catalyst_provider or "auto").strip().lower()
    use_webull = choice == "webull" or (
        choice == "auto" and settings.market_data_provider == "webull"
    )
    if not use_webull:
        return MockCatalystProvider()

    data_client = getattr(market_data, "data_client", None)
    from trading_system.events.webull import WebullCatalystProvider

    return WebullCatalystProvider(
        data_client=data_client,
        app_key=settings.webull_app_key,
        app_secret=settings.webull_app_secret,
        region=settings.webull_region,
        api_endpoint=settings.webull_api_endpoint,
    )
