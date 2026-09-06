"""Webull OpenAPI catalyst adapter — official Fundamentals methods only.

Calls (do not invent paths):
- DataClient.fundamentals.get_earnings_calendar  GET /openapi/fundamentals/stock/earnings-calendar
- DataClient.fundamentals.get_sec_filings         GET /openapi/fundamentals/stock/filings

These are Market Data Fundamentals (Non-Display) endpoints. Missing SDK
methods, entitlement errors, or empty calendars become unavailable notes.
Never fabricates headlines.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from trading_system.data.bars import resolve_equity_category
from trading_system.events.base import CatalystProvider
from trading_system.events.mock import unavailable_snapshot
from trading_system.events.parse import aware_utc, parse_earnings_rows, parse_filing_rows
from trading_system.events.scoring import snapshot_from_events
from trading_system.events.types import CatalystSnapshot
from trading_system.webull_support import WebullApiError, require_ok

logger = logging.getLogger(__name__)

_ETF_NOTE = (
    "ETFs typically have no corporate earnings calendar; treating as "
    "not_applicable rather than inventing a date."
)


class WebullCatalystProvider(CatalystProvider):
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
                    "WebullCatalystProvider requires a DataClient or "
                    "WEBULL_APP_KEY / WEBULL_APP_SECRET"
                )
            from webull.core.client import ApiClient
            from webull.data.data_client import DataClient

            api_client = ApiClient(app_key, app_secret, region)
            api_client.add_endpoint(region, api_endpoint)
            data_client = DataClient(api_client)
        self._data = data_client
        self._endpoint = api_endpoint

    def get_catalyst(
        self,
        symbol: str,
        *,
        as_of: datetime | None = None,
    ) -> CatalystSnapshot:
        now = aware_utc(as_of)
        key = symbol.upper()
        fundamentals = getattr(self._data, "fundamentals", None)
        if fundamentals is None:
            return unavailable_snapshot(
                key,
                source=self.name,
                note=(
                    "DataClient.fundamentals is not present on this SDK build. "
                    "Upgrade webull-openapi-python-sdk; do not invent a calendar."
                ),
            )
        category = resolve_equity_category(key)
        notes: list[str] = [
            "Source: DataClient.fundamentals.get_earnings_calendar "
            "(GET /openapi/fundamentals/stock/earnings-calendar).",
            "Filings: DataClient.fundamentals.get_sec_filings "
            "(GET /openapi/fundamentals/stock/filings). Title/url/date only.",
        ]
        earnings_error = ""
        filings_error = ""
        earnings_rows: list = []
        filing_rows: list = []

        try:
            res = fundamentals.get_earnings_calendar(key, category)
            payload = require_ok(res, "get_earnings_calendar", endpoint=self._endpoint)
            earnings_rows = parse_earnings_rows(payload)
        except WebullApiError as exc:
            earnings_error = str(exc)
            logger.info("Earnings calendar %s failed: %s", key, exc)
            notes.append(f"earnings_calendar unavailable: {exc}")
        except Exception as exc:  # noqa: BLE001
            earnings_error = str(exc)
            logger.info("Earnings calendar %s failed: %s", key, exc)
            notes.append(f"earnings_calendar unavailable: {exc}")

        try:
            res = fundamentals.get_sec_filings(key, category)
            payload = require_ok(res, "get_sec_filings", endpoint=self._endpoint)
            filing_rows = parse_filing_rows(payload)
        except WebullApiError as exc:
            filings_error = str(exc)
            logger.info("SEC filings %s failed: %s", key, exc)
            notes.append(f"sec_filings unavailable: {exc}")
        except Exception as exc:  # noqa: BLE001
            filings_error = str(exc)
            logger.info("SEC filings %s failed: %s", key, exc)
            notes.append(f"sec_filings unavailable: {exc}")

        raw_error = "; ".join(p for p in (earnings_error, filings_error) if p)
        if category == "US_ETF" and not earnings_rows:
            notes.append(_ETF_NOTE)
            return snapshot_from_events(
                key,
                source=self.name,
                as_of=now.date(),
                earnings=[],
                filings=filing_rows,
                notes=notes,
                available=True,
                earnings_status_override="not_applicable",
                raw_error=raw_error,
            )
        if not earnings_rows and earnings_error:
            return unavailable_snapshot(
                key,
                source=self.name,
                note=(
                    "Official earnings calendar call failed. "
                    "Decision package continues without a fabricated date."
                ),
                error=raw_error,
            )
        available = bool(earnings_rows) or bool(filing_rows) or category == "US_ETF"
        if not earnings_rows:
            notes.append(
                "No upcoming/published earnings rows in the official calendar window "
                "(±6 months). Not inventing a date."
            )
        return snapshot_from_events(
            key,
            source=self.name,
            as_of=now.date(),
            earnings=earnings_rows,
            filings=filing_rows,
            notes=notes,
            available=available or not earnings_error,
            raw_error=raw_error,
        )
