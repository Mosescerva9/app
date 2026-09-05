"""Read-only broker interfaces. Order placement is intentionally absent in Phase 2."""

from __future__ import annotations

from abc import ABC, abstractmethod

from trading_system.models import AccountBalance, OpenOrder, Position


class BrokerReadClient(ABC):
    """Account/position/order reads only. No submit/cancel methods in Phase 2."""

    name: str

    @abstractmethod
    def list_accounts(self) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def get_balance(self, account_id: str) -> AccountBalance:
        raise NotImplementedError

    @abstractmethod
    def get_positions(self, account_id: str) -> list[Position]:
        raise NotImplementedError

    @abstractmethod
    def get_open_orders(self, account_id: str) -> list[OpenOrder]:
        raise NotImplementedError

    def place_order(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError(
            "Order placement is disabled in Phase 2. "
            "Execution unlocks only after paper trading validation and explicit approval."
        )
