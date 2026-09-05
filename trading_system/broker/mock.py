"""Mock broker for offline RESEARCH mode."""

from __future__ import annotations

from trading_system.broker.base import BrokerReadClient
from trading_system.models import AccountBalance, OpenOrder, Position


class MockBrokerReadClient(BrokerReadClient):
    name = "mock"

    def __init__(self, equity: float = 1000.0, account_id: str = "MOCK-001") -> None:
        self._equity = equity
        self._account_id = account_id
        self._positions: list[Position] = []
        self._orders: list[OpenOrder] = []

    def list_accounts(self) -> list[dict]:
        return [{"account_id": self._account_id, "account_type": "CASH", "provider": "mock"}]

    def get_balance(self, account_id: str) -> AccountBalance:
        return AccountBalance(
            account_id=account_id or self._account_id,
            total_equity=self._equity,
            cash=self._equity,
            buying_power=self._equity,
            raw={"provider": "mock"},
        )

    def get_positions(self, account_id: str) -> list[Position]:
        return list(self._positions)

    def get_open_orders(self, account_id: str) -> list[OpenOrder]:
        return list(self._orders)
