"""Deterministic synthetic daily bars for backtest tests (no live quotes)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from trading_system.models import Bar


def synthetic_trend_bars(
    *,
    symbol: str = "TEST",
    start: float = 100.0,
    n_up: int = 80,
    n_down: int = 40,
    up_ret: float = 0.006,
    down_ret: float = -0.007,
    as_of: datetime | None = None,
) -> list[Bar]:
    """Smooth grind higher, then lower — enough for SMA50 + a regime flip."""
    now = as_of or datetime(2026, 9, 6, tzinfo=timezone.utc)
    total = n_up + n_down
    price = start
    bars: list[Bar] = []
    for i in range(total):
        ret = up_ret if i < n_up else down_ret
        open_px = price
        close_px = price * (1.0 + ret)
        high = max(open_px, close_px) * 1.001
        low = min(open_px, close_px) * 0.999
        bars.append(
            Bar(
                symbol=symbol.upper(),
                timestamp=now - timedelta(days=total - i),
                open=round(open_px, 6),
                high=round(high, 6),
                low=round(low, 6),
                close=round(close_px, 6),
                volume=1_000_000.0 + i,
                timespan="D",
            )
        )
        price = close_px
    return bars


def synthetic_chop_bars(
    *,
    symbol: str = "CHOP",
    start: float = 100.0,
    count: int = 80,
    as_of: datetime | None = None,
) -> list[Bar]:
    """Mean-reverting range with wide wicks — stand-aside expected."""
    now = as_of or datetime(2026, 9, 6, tzinfo=timezone.utc)
    bars: list[Bar] = []
    for i in range(count):
        # Tight close path around the mean; wide high/low so choppiness is high.
        close_px = start * (1.0 + 0.002 * (1 if i % 2 == 0 else -1))
        open_px = start * (1.0 + 0.002 * (-1 if i % 2 == 0 else 1))
        bars.append(
            Bar(
                symbol=symbol.upper(),
                timestamp=now - timedelta(days=count - i),
                open=round(open_px, 6),
                high=round(start * 1.025, 6),
                low=round(start * 0.975, 6),
                close=round(close_px, 6),
                volume=800_000.0 + (i % 3) * 10_000,
                timespan="D",
            )
        )
    return bars
