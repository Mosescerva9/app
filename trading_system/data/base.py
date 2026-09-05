"""Provider-agnostic market data interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

from trading_system.models import Bar, QuoteSnapshot


class MarketDataProvider(ABC):
    """Read-only market data. Implementations must not place orders."""

    name: str

    @abstractmethod
    def get_history_bars(
        self,
        symbol: str,
        *,
        timespan: str = "D",
        count: int = 60,
        category: str = "US_STOCK",
    ) -> list[Bar]:
        raise NotImplementedError

    @abstractmethod
    def get_snapshots(
        self,
        symbols: Sequence[str],
        *,
        category: str = "US_STOCK",
    ) -> list[QuoteSnapshot]:
        raise NotImplementedError

    def get_option_snapshots(
        self,
        option_symbols: Sequence[str],
        *,
        category: str = "US_OPTION",
    ) -> list[QuoteSnapshot]:
        """Optional — providers without options data may leave unimplemented."""
        raise NotImplementedError(f"{self.name} does not implement option snapshots yet")

    def ping(self) -> dict:
        return {"provider": self.name, "ok": True}
