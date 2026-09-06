"""Webull OpenAPI fundamentals adapter — official forecast-EPS only.

Calls (do not invent paths):
- DataClient.fundamentals.get_forecast_eps  GET /openapi/fundamentals/stock/forecast-eps

SDK: last four disclosed actuals plus latest consensus estimate when present.
Missing method, entitlement errors, or empty rows → unavailable. No fake ratios.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from trading_system.data.bars import resolve_equity_category
from trading_system.fundamentals.base import FundamentalsProvider
from trading_system.fundamentals.mock import unavailable_fundamentals
from trading_system.fundamentals.parse import beat_miss_and_score, parse_forecast_eps_rows
from trading_system.fundamentals.types import FundamentalsSnapshot
from trading_system.webull_support import WebullApiError, require_ok

logger = logging.getLogger(__name__)


class WebullFundamentalsProvider(FundamentalsProvider):
    name = "webull"

    def __init__(
        self,
        *,
        data_client: Any | None = None,
        app_key: str = "",
        app_secret: str = "",
        region: str = "us",
        api_endpoint: str = "api.sandbox.webull.com",
    ) -> None:
        if data_client is None:
            if not app_key or not app_secret:
                raise ValueError(
                    "WebullFundamentalsProvider requires a DataClient or "
                    "WEBULL_APP_KEY / WEBULL_APP_SECRET"
                )
            from webull.core.client import ApiClient
            from webull.data.data_client import DataClient

            api_client = ApiClient(app_key, app_secret, region)
            api_client.add_endpoint(region, api_endpoint)
            data_client = DataClient(api_client)
        self._data = data_client
        self._endpoint = api_endpoint

    def get_fundamentals(
        self,
        symbol: str,
        *,
        as_of: datetime | None = None,
    ) -> FundamentalsSnapshot:
        key = symbol.upper()
        fundamentals = getattr(self._data, "fundamentals", None)
        if fundamentals is None or not hasattr(fundamentals, "get_forecast_eps"):
            return unavailable_fundamentals(
                key,
                source=self.name,
                note=(
                    "DataClient.fundamentals.get_forecast_eps is not present on this "
                    "SDK build. Not inventing financials."
                ),
            )
        category = resolve_equity_category(key)
        notes = [
            "Source: DataClient.fundamentals.get_forecast_eps "
            "(GET /openapi/fundamentals/stock/forecast-eps).",
            "Minimal Phase 8 slice: official EPS actual/estimate only. "
            "Full statements remain deferred.",
        ]
        if category == "US_ETF":
            return FundamentalsSnapshot(
                symbol=key,
                available=True,
                source=self.name,
                score=55.0,
                beat_miss="not_applicable",
                notes=tuple(
                    notes
                    + ["ETF: corporate forecast-EPS is not applicable; not inventing holdings analytics."]
                ),
            )
        try:
            res = fundamentals.get_forecast_eps(key, category)
            payload = require_ok(res, "get_forecast_eps", endpoint=self._endpoint)
        except (WebullApiError, Exception) as exc:  # noqa: BLE001
            logger.info("Forecast EPS %s failed: %s", key, exc)
            return unavailable_fundamentals(
                key,
                source=self.name,
                note="Official forecast-EPS call failed; not inventing a print.",
                error=str(exc),
            )
        rows = parse_forecast_eps_rows(payload)
        if not rows:
            return unavailable_fundamentals(
                key,
                source=self.name,
                note="Official forecast-EPS returned no rows. Not inventing EPS.",
            )
        beat_miss, score, actual, estimate = beat_miss_and_score(rows)
        return FundamentalsSnapshot(
            symbol=key,
            available=True,
            source=self.name,
            score=score,
            latest_actual_eps=actual,
            latest_estimate_eps=estimate,
            beat_miss=beat_miss,
            rows=tuple(rows),
            notes=tuple(notes),
        )
