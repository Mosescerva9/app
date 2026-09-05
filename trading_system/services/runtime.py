"""Application service wiring for Phase 2 research operations."""

from __future__ import annotations

from dataclasses import asdict

from trading_system.broker import build_broker_client
from trading_system.broker.base import BrokerReadClient
from trading_system.config import Settings, get_settings
from trading_system.data import build_market_data_provider
from trading_system.data.base import MarketDataProvider
from trading_system.modes import PHASE, LIVE_EXECUTION_UNLOCKED, assert_mode_allowed
from trading_system.risk import RiskLimits, load_risk_limits


class ResearchRuntime:
    """Composable runtime used by CLI and future agent/orchestrator layers."""

    def __init__(
        self,
        settings: Settings | None = None,
        market_data: MarketDataProvider | None = None,
        broker: BrokerReadClient | None = None,
        risk: RiskLimits | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        assert_mode_allowed(self.settings.mode)
        self.market_data = market_data or build_market_data_provider(self.settings)
        self.broker = broker or build_broker_client(self.settings)
        self.risk = risk or load_risk_limits(self.settings)

    def status(self) -> dict:
        return {
            "phase": PHASE,
            "mode": self.settings.mode.value,
            "live_execution_unlocked": LIVE_EXECUTION_UNLOCKED,
            "emergency_stop": self.risk.emergency_stop,
            "market_data_provider": self.market_data.name,
            "broker_provider": self.broker.name,
            "webull_configured": self.settings.webull_configured,
            "risk": {
                "account_equity_usd": self.risk.account_equity_usd,
                "max_risk_per_trade_usd": self.risk.max_risk_per_trade_usd,
                "max_simultaneous_positions": self.risk.max_simultaneous_positions,
                "max_daily_loss_usd": self.risk.max_daily_loss_usd,
                "max_weekly_loss_usd": self.risk.max_weekly_loss_usd,
            },
        }

    def fetch_bars(self, symbol: str, timespan: str = "D", count: int = 30) -> list[dict]:
        bars = self.market_data.get_history_bars(symbol, timespan=timespan, count=count)
        return [asdict(b) | {"timestamp": b.timestamp.isoformat()} for b in bars]

    def fetch_snapshots(self, symbols: list[str]) -> list[dict]:
        snaps = self.market_data.get_snapshots(symbols)
        return [asdict(s) for s in snaps]

    def account_overview(self, account_id: str | None = None) -> dict:
        accounts = self.broker.list_accounts()
        acct = account_id or self.settings.webull_account_id
        if not acct and accounts:
            acct = str(accounts[0].get("account_id") or accounts[0].get("id") or "")
        if not acct:
            return {"accounts": accounts, "balance": None, "positions": [], "open_orders": []}
        balance = self.broker.get_balance(acct)
        positions = self.broker.get_positions(acct)
        orders = self.broker.get_open_orders(acct)
        return {
            "accounts": accounts,
            "balance": asdict(balance),
            "positions": [asdict(p) for p in positions],
            "open_orders": [asdict(o) for o in orders],
        }
