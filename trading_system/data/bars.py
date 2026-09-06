"""Normalize Webull (and similar) history-bar payloads into chronological Bar rows."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from trading_system.models import Bar, ms_to_datetime, to_float

_OHLC_HINTS = ("open", "close", "high", "low", "o", "c", "h", "l")
_NEST_KEYS = ("bars", "data", "result", "items", "list", "kline", "klines")


def resolve_equity_category(symbol: str, category: str | None = None) -> str:
    """Map liquid US ETFs to official US_ETF; leave explicit non-default categories alone."""
    requested = (category or "US_STOCK").strip().upper() or "US_STOCK"
    if requested not in {"US_STOCK", "US_ETF"}:
        return requested
    if symbol.upper() in US_ETF_SYMBOLS:
        return "US_ETF"
    return requested


def categories_to_try(symbol: str, category: str | None = None) -> tuple[str, ...]:
    """Primary category plus one fallback so ETF/stock mis-tags still resolve."""
    primary = resolve_equity_category(symbol, category)
    requested = (category or "US_STOCK").strip().upper() or "US_STOCK"
    tried = [primary]
    if primary == "US_ETF" and requested != "US_STOCK":
        tried.append("US_STOCK")
    elif primary == "US_ETF":
        tried.append("US_STOCK")
    elif primary == "US_STOCK":
        tried.append("US_ETF")
    # Deduplicate while preserving order.
    out: list[str] = []
    for item in tried:
        if item not in out:
            out.append(item)
    return tuple(out)


def extract_bar_rows(payload: Any) -> list[dict[str, Any]]:
    """Pull raw bar dicts out of official Webull envelopes (nested result, bars, CSV)."""
    rows: list[dict[str, Any]] = []
    _collect_bar_rows(payload, rows)
    return rows


def bars_from_payload(
    payload: Any,
    *,
    symbol: str,
    timespan: str,
) -> list[Bar]:
    bars = [
        _row_to_bar(row, symbol=symbol, timespan=timespan)
        for row in extract_bar_rows(payload)
    ]
    bars = [b for b in bars if b.close > 0 or b.open > 0]
    bars.sort(key=lambda b: b.timestamp)
    return bars


def _collect_bar_rows(payload: Any, out: list[dict[str, Any]]) -> None:
    if payload is None:
        return
    if isinstance(payload, str):
        parsed = _parse_bar_string(payload)
        if parsed:
            out.append(parsed)
        return
    if isinstance(payload, list):
        for item in payload:
            _collect_bar_rows(item, out)
        return
    if not isinstance(payload, dict):
        return
    if _looks_like_bar(payload):
        out.append(payload)
        return
    nested = False
    for key in _NEST_KEYS:
        value = payload.get(key)
        if isinstance(value, (list, dict, str)):
            _collect_bar_rows(value, out)
            nested = True
    if not nested and ("symbol" in payload or "ticker" in payload):
        # Envelope without a recognized nest key — keep walking values that are lists.
        for value in payload.values():
            if isinstance(value, list):
                _collect_bar_rows(value, out)


def _looks_like_bar(row: dict[str, Any]) -> bool:
    has_ohlc = any(k in row for k in _OHLC_HINTS)
    has_time = any(k in row for k in ("timestamp", "time", "startTime", "date", "t"))
    # Nested envelopes also have symbol+result; those are not bars.
    if "result" in row and isinstance(row.get("result"), list) and not has_ohlc:
        return False
    if "bars" in row and isinstance(row.get("bars"), list) and not has_ohlc:
        return False
    return has_ohlc or (has_time and ("volume" in row or "v" in row))


def _parse_bar_string(raw: str) -> dict[str, Any] | None:
    """Parse `time,open,high,low,close,volume` (and close-before-high variants)."""
    parts = [p.strip() for p in raw.replace("|", ",").split(",") if p.strip()]
    if len(parts) < 6:
        return None
    ts, a, b, c, d, vol = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5]
    fa, fb, fc, fd = to_float(a), to_float(b), to_float(c), to_float(d)
    if None in (fa, fb, fc, fd):
        return None
    # If the 3rd value is clearly a high ( >= both neighbors ) treat as O,H,L,C.
    if fb is not None and fc is not None and fa is not None and fd is not None:
        if fb >= max(fa, fc, fd) - 1e-9 and fc <= min(fa, fb, fd) + 1e-9:
            open_, high, low, close = fa, fb, fc, fd
        else:
            # Official older CSV: time,open,close,high,low,volume
            open_, close, high, low = fa, fb, fc, fd
    else:
        return None
    return {
        "time": ts,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": to_float(vol) or 0.0,
    }


def _row_to_bar(row: dict[str, Any], *, symbol: str, timespan: str) -> Bar:
    return Bar(
        symbol=symbol.upper(),
        timestamp=_bar_timestamp(row),
        open=float(to_float(row.get("open") if row.get("open") is not None else row.get("o")) or 0.0),
        high=float(to_float(row.get("high") if row.get("high") is not None else row.get("h")) or 0.0),
        low=float(to_float(row.get("low") if row.get("low") is not None else row.get("l")) or 0.0),
        close=float(to_float(row.get("close") if row.get("close") is not None else row.get("c")) or 0.0),
        volume=float(to_float(row.get("volume") if row.get("volume") is not None else row.get("v")) or 0.0),
        timespan=timespan,
    )


def _bar_timestamp(row: dict[str, Any]) -> datetime:
    return ms_to_datetime(
        row.get("timestamp")
        or row.get("time")
        or row.get("startTime")
        or row.get("date")
        or row.get("t")
    )


# Common US ETFs in the default scanner universe + liquid peers.
US_ETF_SYMBOLS: frozenset[str] = frozenset(
    {
        "SPY",
        "QQQ",
        "IWM",
        "DIA",
        "XLK",
        "XLF",
        "XLE",
        "XLV",
        "XLI",
        "XLY",
        "XLP",
        "XLU",
        "XLB",
        "XLRE",
        "XLC",
        "VOO",
        "VTI",
        "TQQQ",
        "SQQQ",
        "ARKK",
        "SMH",
        "SOXL",
        "SPXU",
        "UVXY",
        "VXX",
        "HYG",
        "TLT",
        "GLD",
        "SLV",
        "USO",
        "EEM",
        "EFA",
    }
)
