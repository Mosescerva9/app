"""Deterministic mock market data for offline research and tests."""

from __future__ import annotations

from datetime import timedelta
from typing import Sequence

from trading_system.data.base import MarketDataProvider
from trading_system.models import Bar, QuoteSnapshot, utc_now


class MockMarketDataProvider(MarketDataProvider):
    name = "mock"

    def __init__(self, seed_price: float = 100.0) -> None:
        self.seed_price = seed_price

    def get_history_bars(
        self,
        symbol: str,
        *,
        timespan: str = "D",
        count: int = 60,
        category: str = "US_STOCK",
    ) -> list[Bar]:
        now = utc_now()
        bars: list[Bar] = []
        price = self.seed_price
        for i in range(count, 0, -1):
            # Mild deterministic drift so tests are stable.
            open_px = price
            close_px = price * (1.0 + ((hash((symbol, i)) % 7) - 3) / 1000.0)
            high_px = max(open_px, close_px) * 1.005
            low_px = min(open_px, close_px) * 0.995
            bars.append(
                Bar(
                    symbol=symbol.upper(),
                    timestamp=now - timedelta(days=i if timespan.upper() == "D" else 0,
                                              minutes=i if timespan.upper() != "D" else 0),
                    open=round(open_px, 4),
                    high=round(high_px, 4),
                    low=round(low_px, 4),
                    close=round(close_px, 4),
                    volume=1_000_000 + i * 1000,
                    timespan=timespan.upper(),
                )
            )
            price = close_px
        return bars

    def get_snapshots(
        self,
        symbols: Sequence[str],
        *,
        category: str = "US_STOCK",
    ) -> list[QuoteSnapshot]:
        out: list[QuoteSnapshot] = []
        for symbol in symbols:
            last = self.seed_price * (1.0 + (hash(symbol.upper()) % 50) / 1000.0)
            out.append(
                QuoteSnapshot(
                    symbol=symbol.upper(),
                    last=round(last, 4),
                    open=round(last * 0.99, 4),
                    high=round(last * 1.01, 4),
                    low=round(last * 0.98, 4),
                    prev_close=round(last * 0.995, 4),
                    volume=2_500_000.0,
                    change=round(last * 0.005, 4),
                    change_ratio=0.005,
                    bid=round(last - 0.01, 4),
                    ask=round(last + 0.01, 4),
                    raw={"provider": "mock", "category": category},
                )
            )
        return out

    def get_option_snapshots(
        self,
        option_symbols: Sequence[str],
        *,
        category: str = "US_OPTION",
    ) -> list[QuoteSnapshot]:
        out: list[QuoteSnapshot] = []
        for symbol in option_symbols:
            mid = 2.5
            out.append(
                QuoteSnapshot(
                    symbol=symbol.upper(),
                    last=mid,
                    open=mid,
                    high=mid * 1.1,
                    low=mid * 0.9,
                    prev_close=mid,
                    volume=1500.0,
                    change=0.0,
                    change_ratio=0.0,
                    bid=2.4,
                    ask=2.6,
                    raw={"provider": "mock", "category": category, "oi": 5000},
                )
            )
        return out
