"""Shared domain models for market and account data."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class Bar:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    timespan: str


@dataclass(frozen=True)
class QuoteSnapshot:
    symbol: str
    last: float | None
    open: float | None
    high: float | None
    low: float | None
    prev_close: float | None
    volume: float | None
    change: float | None
    change_ratio: float | None
    bid: float | None = None
    ask: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AccountBalance:
    account_id: str
    total_equity: float | None
    cash: float | None
    buying_power: float | None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Position:
    symbol: str
    quantity: float
    market_value: float | None = None
    average_cost: float | None = None
    instrument_type: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OpenOrder:
    order_id: str
    client_order_id: str | None
    symbol: str
    side: str | None
    status: str | None
    quantity: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ms_to_datetime(value: Any) -> datetime:
    """Convert Webull millisecond timestamps (or ISO strings) to aware UTC datetime."""
    if value is None:
        return utc_now()
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        # Heuristic: ns vs ms vs s
        ts = float(value)
        if ts > 1e14:
            ts /= 1000.0
        if ts > 1e11:
            ts /= 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            return ms_to_datetime(int(text))
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return utc_now()
    return utc_now()


def to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
