"""Webull OpenAPI fundamentals adapter — official SDK methods only.

Calls (do not invent paths). All live on DataClient.fundamentals in
webull-openapi-python-sdk 2.0.x:

- get_forecast_eps              GET /openapi/fundamentals/stock/forecast-eps
- get_financials_indicators     GET /openapi/fundamentals/financial/indicators
- get_financials_income         GET /openapi/fundamentals/financial/income
- get_financials_cashflow       GET /openapi/fundamentals/financial/cash-flow
- get_financials_balance_sheet  GET /openapi/fundamentals/financial/balance-sheet
- get_industry_comparison       GET /openapi/fundamentals/stock/industry-comparison

Missing method, entitlement errors, or empty rows → that slice is unavailable.
No fabricated ratios, statements, or industry ranks.

Analyst target/rating live on DataClient.instrument (not fundamentals.*) and
are left unused here.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from trading_system.data.bars import resolve_equity_category
from trading_system.fundamentals.base import FundamentalsProvider
from trading_system.fundamentals.mock import unavailable_fundamentals
from trading_system.fundamentals.parse import (
    beat_miss_and_score,
    blend_fundamental_score,
    parse_balance_periods,
    parse_cashflow_periods,
    parse_forecast_eps_rows,
    parse_income_periods,
    parse_indicators,
    parse_industry_comparison,
)
from trading_system.fundamentals.types import (
    FundamentalsSnapshot,
    IndustryComparison,
    StatementPeriod,
)
from trading_system.webull_support import WebullApiError, require_ok

logger = logging.getLogger(__name__)

# Official SDK: type=ANNUAL|QUARTERLY, count default 5 max 20. Integer count only.
_STATEMENT_TYPE = "QUARTERLY"
_STATEMENT_COUNT = 4
_INDUSTRY_SORT = "ROE"  # official sort_by enum on get_industry_comparison


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
        if fundamentals is None:
            return unavailable_fundamentals(
                key,
                source=self.name,
                note=(
                    "DataClient.fundamentals is not present on this SDK build. "
                    "Not inventing financials."
                ),
            )
        category = resolve_equity_category(key)
        notes = [
            "Official DataClient.fundamentals only: forecast-EPS, indicators, "
            "income, cash-flow, balance-sheet, industry-comparison.",
            "Analyst targets/ratings are DataClient.instrument methods and are not called.",
        ]
        if category == "US_ETF":
            return FundamentalsSnapshot(
                symbol=key,
                available=True,
                source=self.name,
                score=55.0,
                beat_miss="not_applicable",
                statements_status="not_applicable",
                notes=tuple(
                    notes
                    + [
                        "ETF: official stock financials endpoints document US_STOCK only. "
                        "Not inventing holdings analytics or corporate statements."
                    ]
                ),
            )

        errors: list[str] = []
        eps_rows = []
        beat_miss, eps_score, actual, estimate = "unavailable", None, None, None
        if hasattr(fundamentals, "get_forecast_eps"):
            try:
                res = fundamentals.get_forecast_eps(key, category)
                payload = require_ok(res, "get_forecast_eps", endpoint=self._endpoint)
                eps_rows = parse_forecast_eps_rows(payload)
                beat_miss, eps_score, actual, estimate = beat_miss_and_score(eps_rows)
                notes.append(
                    "forecast-EPS: DataClient.fundamentals.get_forecast_eps "
                    "(GET /openapi/fundamentals/stock/forecast-eps)."
                )
            except (WebullApiError, Exception) as exc:  # noqa: BLE001
                logger.info("Forecast EPS %s failed: %s", key, exc)
                errors.append(f"get_forecast_eps: {exc}")
                notes.append("Official forecast-EPS call failed; not inventing a print.")
        else:
            notes.append("get_forecast_eps missing on this SDK build.")

        indicators, points = {}, ()
        if hasattr(fundamentals, "get_financials_indicators"):
            try:
                res = fundamentals.get_financials_indicators(
                    key, category, _STATEMENT_TYPE, _STATEMENT_COUNT
                )
                payload = require_ok(res, "get_financials_indicators", endpoint=self._endpoint)
                latest, pts = parse_indicators(payload)
                indicators, points = latest, tuple(pts)
                notes.append(
                    "indicators: DataClient.fundamentals.get_financials_indicators "
                    "(GET /openapi/fundamentals/financial/indicators)."
                )
            except (WebullApiError, Exception) as exc:  # noqa: BLE001
                logger.info("Indicators %s failed: %s", key, exc)
                errors.append(f"get_financials_indicators: {exc}")
                notes.append("Official indicators call failed; not inventing ROE/margins.")
        else:
            notes.append("get_financials_indicators missing on this SDK build.")

        income = self._optional_statement(
            fundamentals,
            "get_financials_income",
            key,
            category,
            parse_income_periods,
            notes,
            errors,
            "income",
            "GET /openapi/fundamentals/financial/income",
        )
        cashflow = self._optional_statement(
            fundamentals,
            "get_financials_cashflow",
            key,
            category,
            parse_cashflow_periods,
            notes,
            errors,
            "cashflow",
            "GET /openapi/fundamentals/financial/cash-flow",
        )
        balance = self._optional_statement(
            fundamentals,
            "get_financials_balance_sheet",
            key,
            category,
            parse_balance_periods,
            notes,
            errors,
            "balance",
            "GET /openapi/fundamentals/financial/balance-sheet",
        )

        industry: IndustryComparison | None = None
        if hasattr(fundamentals, "get_industry_comparison"):
            try:
                res = fundamentals.get_industry_comparison(key, category, _INDUSTRY_SORT)
                payload = require_ok(res, "get_industry_comparison", endpoint=self._endpoint)
                industry = parse_industry_comparison(payload, symbol=key)
            except (WebullApiError, Exception) as exc:  # noqa: BLE001
                logger.info("Industry comparison %s failed: %s", key, exc)
                errors.append(f"get_industry_comparison: {exc}")
                notes.append("Official industry-comparison call failed; not inventing peers.")
        else:
            notes.append("get_industry_comparison missing on this SDK build.")

        present = sum(
            1
            for item in (bool(eps_rows), bool(indicators), income, cashflow, balance)
            if item
        )
        if present >= 3:
            statements_status = "present"
        elif present:
            statements_status = "partial"
        else:
            statements_status = "unavailable"

        score = blend_fundamental_score(
            eps_score=eps_score,
            indicators=indicators,
            income=income,
        )
        available = present > 0 or (industry is not None and industry.available)
        if not available:
            return unavailable_fundamentals(
                key,
                source=self.name,
                note="All official fundamentals calls failed or returned empty. Not inventing numbers.",
                error="; ".join(errors),
                statements_status="unavailable",
            )
        if beat_miss == "unavailable" and available:
            beat_miss = "unknown"
        return FundamentalsSnapshot(
            symbol=key,
            available=True,
            source=self.name,
            score=score,
            latest_actual_eps=actual,
            latest_estimate_eps=estimate,
            beat_miss=beat_miss,
            rows=tuple(eps_rows),
            statements_status=statements_status,
            latest_indicators=indicators,
            indicator_points=points if isinstance(points, tuple) else tuple(points),
            income=income,
            cashflow=cashflow,
            balance=balance,
            industry=industry,
            notes=tuple(notes),
            raw_error="; ".join(errors),
        )

    def _optional_statement(
        self,
        fundamentals: Any,
        method_name: str,
        symbol: str,
        category: str,
        parser,
        notes: list[str],
        errors: list[str],
        label: str,
        path: str,
    ) -> StatementPeriod | None:
        if not hasattr(fundamentals, method_name):
            notes.append(f"{method_name} missing on this SDK build.")
            return None
        try:
            method = getattr(fundamentals, method_name)
            res = method(symbol, category, _STATEMENT_TYPE, _STATEMENT_COUNT)
            payload = require_ok(res, method_name, endpoint=self._endpoint)
            periods = parser(payload)
        except (WebullApiError, Exception) as exc:  # noqa: BLE001
            logger.info("%s %s failed: %s", method_name, symbol, exc)
            errors.append(f"{method_name}: {exc}")
            notes.append(f"Official {label} call failed; not inventing statement rows.")
            return None
        if not periods:
            notes.append(f"Official {label} returned no periods. Not inventing {label} numbers.")
            return None
        notes.append(f"{label}: DataClient.fundamentals.{method_name} ({path}).")
        return periods[-1]
