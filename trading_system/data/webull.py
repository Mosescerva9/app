"""Webull OpenAPI market-data adapter (read-only).

Uses the official `webull-openapi-python-sdk` DataClient only.
Requires OpenAPI Advanced Quotes subscription for live/sandbox market data.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from trading_system.data.bars import bars_from_payload, categories_to_try
from trading_system.data.base import MarketDataProvider
from trading_system.models import QuoteSnapshot, to_float
from trading_system.webull_support import require_ok

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

    @property
    def data_client(self) -> Any:
        """Official DataClient — shared with the options-chain adapter."""
        return self._data

    @property
    def endpoint(self) -> str:
        return self._endpoint

    def ping(self) -> dict:
        return {"provider": self.name, "ok": True, "endpoint": self._endpoint}

    def get_history_bars(
        self,
        symbol: str,
        *,
        timespan: str = "D",
        count: int = 60,
        category: str = "US_STOCK",
    ) -> list:
        ts = _map_timespan(timespan)
        last_error: Exception | None = None
        for cat in categories_to_try(symbol, category):
            try:
                bars = self._history_bars_once(
                    symbol.upper(), timespan=ts, count=count, category=cat
                )
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.info("History bars %s category=%s failed: %s", symbol, cat, exc)
                continue
            if bars:
                if cat != category:
                    logger.info(
                        "Resolved %s history via category=%s (requested %s)",
                        symbol.upper(),
                        cat,
                        category,
                    )
                return bars
        if last_error is not None:
            raise last_error
        return []

    def _history_bars_once(
        self,
        symbol: str,
        *,
        timespan: str,
        count: int,
        category: str,
    ) -> list:
        # Production api.webull.com rejects count as str and optional session flags
        # with HTTP 400 "Parameters type miss match". Operator probe: count=int works;
        # real_time_required="Y" and trading_sessions="RTH" do not. SDK still accepts
        # those kwargs, but the HTTP query types must stay native (int count, omit extras).
        # Official defaults already return the latest RTH daily bar.
        res = self._data.market_data.get_history_bar(
            symbol,
            category,
            timespan,
            count=int(count),
        )
        payload = require_ok(res, "get_history_bar", endpoint=self._endpoint)
        # Webull returns newest→oldest; bars_from_payload sorts oldest→newest.
        return bars_from_payload(payload, symbol=symbol, timespan=timespan)

    def get_snapshots(
        self,
        symbols: Sequence[str],
        *,
        category: str = "US_STOCK",
    ) -> list[QuoteSnapshot]:
        symbol_list = [s.upper() for s in symbols]
        if not symbol_list:
            return []
        # Batch only works with one category; split ETFs vs stocks.
        from trading_system.data.bars import resolve_equity_category

        by_cat: dict[str, list[str]] = {}
        for sym in symbol_list:
            cat = resolve_equity_category(sym, category)
            by_cat.setdefault(cat, []).append(sym)

        out: list[QuoteSnapshot] = []
        seen: set[str] = set()
        for cat, group in by_cat.items():
            rows = self._snapshots_once(group, category=cat)
            if not rows and cat == "US_ETF":
                rows = self._snapshots_once(group, category="US_STOCK")
            elif not rows and cat == "US_STOCK":
                rows = self._snapshots_once(group, category="US_ETF")
            for snap in rows:
                if snap.symbol and snap.symbol not in seen:
                    seen.add(snap.symbol)
                    out.append(snap)
        # Preserve caller order.
        order = {s: i for i, s in enumerate(symbol_list)}
        out.sort(key=lambda s: order.get(s.symbol, 999))
        return out

    def _snapshots_once(self, symbols: list[str], *, category: str) -> list[QuoteSnapshot]:
        res = self._data.market_data.get_snapshot(symbols, category)
        payload = require_ok(res, "get_snapshot", endpoint=self._endpoint)
        return _snapshots_from_payload(payload)

    def get_option_snapshots(
        self,
        option_symbols: Sequence[str],
        *,
        category: str = "US_OPTION",
    ) -> list[QuoteSnapshot]:
        symbols = [s.upper() for s in option_symbols]
        if not symbols:
            return []
        out: list[QuoteSnapshot] = []
        # Official option snapshot limit: 20 symbols per request.
        for i in range(0, len(symbols), 20):
            chunk = symbols[i : i + 20]
            res = self._data.option_market_data.get_option_snapshot(chunk, category)
            payload = require_ok(res, "get_option_snapshot", endpoint=self._endpoint)
            out.extend(_snapshots_from_payload(payload))
        return out


def _snapshots_from_payload(payload: Any) -> list[QuoteSnapshot]:
    from trading_system.webull_support import as_record_list

    rows = payload if isinstance(payload, list) else as_record_list(payload, ("data", "snapshots", "result"))
    out: list[QuoteSnapshot] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        sym = str(row.get("symbol") or row.get("ticker") or "").upper()
        last = to_float(
            row.get("price")
            or row.get("last")
            or row.get("close")
            or row.get("tradePrice")
        )
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
    valid = {"S5", "S15", "M1", "M5", "M15", "M30", "M60", "M120", "M240", "D", "W", "M", "Y"}
    if mapped not in valid:
        raise ValueError(f"Unsupported timespan={timespan!r}; expected one of {sorted(valid)}")
    return mapped
