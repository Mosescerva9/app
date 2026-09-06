"""Catalyst provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from trading_system.events.types import CatalystSnapshot


class CatalystProvider(ABC):
    """Read-only event/catalyst source. Implementations must not invent news."""

    name: str

    @abstractmethod
    def get_catalyst(
        self,
        symbol: str,
        *,
        as_of: datetime | None = None,
    ) -> CatalystSnapshot:
        raise NotImplementedError
