"""Webull OpenAPI market-data adapter (read-only).

Uses the official `webull-openapi-python-sdk` DataClient only.
Requires OpenAPI Advanced Quotes subscription for live/sandbox market data.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from trading_system.data.base import MarketDataProvider
from trading_system.models import Bar, QuoteSnapshot, ms_to_datetime, to_float

logger = logging.getLogger(__name__)


class WebullMarketDataProvider(MarketDataProvider):
    name = "webull"

    def __init__(
        self,
        *,
        app_key: str,
        app_secret: str,
        region: str = "us",
        api_endpoint: str = "api.sandbox.webull.com",
    ) -> None:
        if not app_key or not app_secret:
            raise ValueError("WebullMarketDataProvider requires WEBULL_APP_KEY and WEBULL_APP_SECRET")

        from webull.core.client import ApiClient
        from webull.data.data_client import DataClient

        api_client = ApiClient(app_key, app_secret, region)
        api_client.add_endpoint(region, api_endpoint)
        self._data = DataClient(api_client)
        self._endpoint = api_endpoint
        logger.info("Webull market data client ready (endpoint=%s)", api_endpoint)

    def ping(self) -> dict:
        return {"provider": self.name, "ok": True, "endpoint": self._endpoint}

    def get_history_bars(
        self,
        symbol: str,
        *,
        timespan: str = "D",
        count: int = 60,
        category: str = "US_STOCK",
    ) -> list[Bar]:
        ts = _map_timespan(timespan)
        res = self._data.market_data.get_history_bar(
            symbol.upper(),
            category,
            ts,
            count=str(count),
        )
        payload = _require_ok(res, "get_history_bar")
        rows = _extract_bar_rows(payload)
        bars: list[Bar] = []
        for row in rows:
            bars.append(
                Bar(
                    symbol=symbol.upper(),
                    timestamp=ms_to_datetime(
                        row.get("timestamp")
                        or row.get("time")
                        or row.get("startTime")
                        or row.get("date")
                    ),
                    open=float(to_float(row.get("open") or row.get("o")) or 0.0),
                    high=float(to_float(row.get("high") or row.get("h")) or 0.0),
                    low=float(to_float(row.get("low") or row.get("l")) or 0.0),
                    close=float(to_float(row.get("close") or row.get("c")) or 0.0),
                    volume=float(to_float(row.get("volume") or row.get("v")) or 0.0),
                    timespan=ts,
                )
            )
        return bars

    def get_snapshots(
        self,
        symbols: Sequence[str],
        *,
        category: str = "US_STOCK",
    ) -> list[QuoteSnapshot]:
        symbol_list = [s.upper() for s in symbols]
        # SDK accepts list or comma-separated depending on request helper; pass list.
        res = self._data.market_data.get_snapshot(symbol_list, category)
        payload = _require_ok(res, "get_snapshot")
        rows = payload if isinstance(payload, list) else payload.get("data") or payload.get("snapshots") or []
        out: list[QuoteSnapshot] = []
        for row in rows:
            sym = str(row.get("symbol") or row.get("ticker") or "").upper()
            last = to_float(row.get("price") or row.get("last") or row.get("close") or row.get("tradePrice"))
            out.append(
                QuoteSnapshot(
                    symbol=sym,
                    last=last,
                    open=to_float(row.get("open")),
                    high=to_float(row.get("high")),
                    low=to_float(row.get("low")),
                    prev_close=to_float(row.get("pre_close") or row.get("prevClose") or row.get("pPrice")),
                    volume=to_float(row.get("volume")),
                    change=to_float(row.get("change")),
                    change_ratio=to_float(row.get("change_ratio") or row.get("changeRatio")),
                    bid=to_float(row.get("bid") or row.get("bidPrice")),
                    ask=to_float(row.get("ask") or row.get("askPrice")),
                    raw=dict(row),
                )
            )
        return out

    def get_option_snapshots(
        self,
        option_symbols: Sequence[str],
        *,
        category: str = "US_OPTION",
    ) -> list[QuoteSnapshot]:
        symbols = [s.upper() for s in option_symbols]
        res = self._data.option_market_data.get_option_snapshot(symbols, category)
        payload = _require_ok(res, "get_option_snapshot")
        rows = payload if isinstance(payload, list) else payload.get("data") or payload.get("snapshots") or []
        out: list[QuoteSnapshot] = []
        for row in rows:
            sym = str(row.get("symbol") or row.get("ticker") or "").upper()
            last = to_float(row.get("price") or row.get("last") or row.get("close"))
            out.append(
                QuoteSnapshot(
                    symbol=sym,
                    last=last,
                    open=to_float(row.get("open")),
                    high=to_float(row.get("high")),
                    low=to_float(row.get("low")),
                    prev_close=to_float(row.get("pre_close") or row.get("prevClose")),
                    volume=to_float(row.get("volume")),
                    change=to_float(row.get("change")),
                    change_ratio=to_float(row.get("change_ratio") or row.get("changeRatio")),
                    bid=to_float(row.get("bid") or row.get("bidPrice")),
                    ask=to_float(row.get("ask") or row.get("askPrice")),
                    raw=dict(row),
                )
            )
        return out


def _map_timespan(timespan: str) -> str:
    """Map friendly aliases to official SDK Timespan names (D, M1, M5, ...)."""
    key = timespan.strip().upper()
    aliases = {
        "1D": "D",
        "DAY": "D",
        "DAILY": "D",
        "1W": "W",
        "WEEK": "W",
        "WEEKLY": "W",
        "1MO": "M",
        "MONTH": "M",
        "MONTHLY": "M",
        "1MIN": "M1",
        "MIN1": "M1",
        "5MIN": "M5",
        "MIN5": "M5",
        "15MIN": "M15",
        "30MIN": "M30",
        "60MIN": "M60",
        "1H": "M60",
        "HOUR": "M60",
    }
    mapped = aliases.get(key, key)
    # Accept already-correct SDK names.
    valid = {"S5", "S15", "M1", "M5", "M15", "M30", "M60", "M120", "M240", "D", "W", "M", "Y"}
    if mapped not in valid:
        raise ValueError(f"Unsupported timespan={timespan!r}; expected one of {sorted(valid)}")
    return mapped


def _require_ok(res: Any, action: str) -> Any:
    status = getattr(res, "status_code", None)
    body = res.json() if hasattr(res, "json") else res
    if status is not None and int(status) >= 400:
        raise RuntimeError(f"Webull {action} failed HTTP {status}: {body}")
    return body


def _extract_bar_rows(payload: Any) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        if payload and isinstance(payload[0], dict) and "symbol" in payload[0] and "bars" in payload[0]:
            rows: list[dict[str, Any]] = []
            for item in payload:
                rows.extend(item.get("bars") or [])
            return rows
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for key in ("bars", "data", "result"):
            value = payload.get(key)
            if isinstance(value, list):
                return [r for r in value if isinstance(r, dict)]
        # Single-symbol envelope
        if "open" in payload or "c" in payload:
            return [payload]
    return []
