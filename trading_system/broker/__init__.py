"""Broker client factory."""

from __future__ import annotations

from trading_system.broker.base import BrokerReadClient
from trading_system.broker.mock import MockBrokerReadClient
from trading_system.broker.webull import WebullBrokerReadClient
from trading_system.config import Settings


def build_broker_client(settings: Settings) -> BrokerReadClient:
    provider = settings.broker_provider
    if provider == "mock":
        return MockBrokerReadClient(equity=settings.account_equity_usd)
    if provider == "webull":
        return WebullBrokerReadClient(
            app_key=settings.webull_app_key,
            app_secret=settings.webull_app_secret,
            region=settings.webull_region,
            api_endpoint=settings.webull_api_endpoint,
        )
    raise ValueError(f"Unknown BROKER_PROVIDER={provider!r} (use mock|webull)")
