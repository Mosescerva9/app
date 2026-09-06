"""Fundamentals provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from trading_system.fundamentals.types import FundamentalsSnapshot


class FundamentalsProvider(ABC):
    name: str

    @abstractmethod
    def get_fundamentals(
        self,
        symbol: str,
        *,
        as_of: datetime | None = None,
    ) -> FundamentalsSnapshot:
        raise NotImplementedError
