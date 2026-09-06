"""Application service wiring for research operations."""

from __future__ import annotations

from dataclasses import asdict

from trading_system.adversarial import (
    AdversarialCritic,
    CompositeAdversarialCritic,
    NullLLMCritic,
    RuleBasedAdversarialCritic,
)
from trading_system.broker import build_broker_client
from trading_system.broker.base import BrokerReadClient
from trading_system.config import Settings, get_settings
from trading_system.data import build_market_data_provider
from trading_system.data.base import MarketDataProvider
from trading_system.decision import DecisionPackageEngine
from trading_system.events import CatalystProvider, build_catalyst_provider
from trading_system.fundamentals import FundamentalsProvider, build_fundamentals_provider
from trading_system.modes import PHASE, assert_mode_allowed
from trading_system.research_lock import stamp_research_lock
from trading_system.options import OptionsAnalysisEngine, build_option_chain_provider
from trading_system.regime import MarketRegimeEngine
from trading_system.risk import RiskLimits, load_risk_limits
from trading_system.scanner import OpportunityScanner
from trading_system.webull_support import (
    WebullApiError,
    account_access_hint,
    collect_account_ids,
)


class ResearchRuntime:
    def __init__(
        self,
        settings: Settings | None = None,
        market_data: MarketDataProvider | None = None,
        broker: BrokerReadClient | None = None,
        risk: RiskLimits | None = None,
        regime_engine: MarketRegimeEngine | None = None,
        scanner: OpportunityScanner | None = None,
        options_engine: OptionsAnalysisEngine | None = None,
        catalyst_provider: CatalystProvider | None = None,
        fundamentals_provider: FundamentalsProvider | None = None,
        critic: AdversarialCritic | None = None,
        decision_engine: DecisionPackageEngine | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        assert_mode_allowed(self.settings.mode)
        self.market_data = market_data or build_market_data_provider(self.settings)
        self.broker = broker or build_broker_client(self.settings)
        self.risk = risk or load_risk_limits(self.settings)
        self.regime_engine = regime_engine or MarketRegimeEngine(self.market_data)
        self.scanner = scanner or OpportunityScanner(self.market_data)
        chain = build_option_chain_provider(self.settings, self.market_data)
        self.options_engine = options_engine or OptionsAnalysisEngine(
            self.market_data,
            chain_provider=chain,
            risk=self.risk,
        )
        self.catalyst_provider = catalyst_provider or build_catalyst_provider(
            self.settings, self.market_data
        )
        self.fundamentals_provider = fundamentals_provider or build_fundamentals_provider(
            self.settings, self.market_data
        )
        self.critic = critic or CompositeAdversarialCritic(
            RuleBasedAdversarialCritic(),
            NullLLMCritic(),
        )
        self.decision_engine = decision_engine or DecisionPackageEngine(
            options_engine=self.options_engine,
            catalyst_provider=self.catalyst_provider,
            fundamentals_provider=self.fundamentals_provider,
            critic=self.critic,
            risk=self.risk,
        )

    def status(self) -> dict:
        return stamp_research_lock({
            "phase": PHASE,
            "mode": self.settings.mode.value,
            "emergency_stop": self.risk.emergency_stop,
            "market_data_provider": self.market_data.name,
            "broker_provider": self.broker.name,
            "option_chain_provider": type(self.options_engine.chain_provider).__name__,
            "catalyst_provider": getattr(
                self.catalyst_provider, "name", type(self.catalyst_provider).__name__
            ),
            "fundamentals_provider": getattr(
                self.fundamentals_provider,
                "name",
                type(self.fundamentals_provider).__name__,
            ),
            "adversarial_critic": getattr(self.critic, "name", type(self.critic).__name__),
            "webull_configured": self.settings.webull_configured,
            "webull_api_endpoint": self.settings.webull_api_endpoint,
            "risk": {
                "account_equity_usd": self.risk.account_equity_usd,
                "max_risk_per_trade_usd": self.risk.max_risk_per_trade_usd,
                "max_simultaneous_positions": self.risk.max_simultaneous_positions,
                "max_daily_loss_usd": self.risk.max_daily_loss_usd,
                "max_weekly_loss_usd": self.risk.max_weekly_loss_usd,
            },
        }, command="status")

    def fetch_bars(self, symbol: str, timespan: str = "D", count: int = 30) -> dict:
        bars = self.market_data.get_history_bars(symbol, timespan=timespan, count=count)
        rows = [asdict(b) | {"timestamp": b.timestamp.isoformat()} for b in bars]
        payload: dict = {
            "symbol": symbol.upper(),
            "timespan": timespan,
            "count": len(rows),
            "bars": rows,
            "session_note": (
                "Daily bars are requested as symbol/category/timespan/count(int) only "
                "(production rejects string count and real_time_required/trading_sessions "
                "with HTTP 400 type mismatch). Official defaults already return the latest "
                "RTH daily bar. Series is sorted oldest→newest so last_close is the newest "
                "print. Snapshot last should agree in the same session; remaining lag is "
                "the in-progress bar vs last print or delayed-quote entitlement offset."
            ),
        }
        if rows:
            payload["last_close"] = rows[-1]["close"]
            payload["first_close"] = rows[0]["close"]
            payload["last_bar_time"] = rows[-1]["timestamp"]
            snap_last = self._snapshot_last(symbol)
            if snap_last is not None and rows[-1]["close"]:
                payload["snapshot_last"] = snap_last
                payload["last_close_vs_snapshot_pct"] = round(
                    (rows[-1]["close"] / snap_last - 1.0) * 100.0, 3
                )
        return payload

    def fetch_snapshots(self, symbols: list[str]) -> list[dict]:
        snaps = self.market_data.get_snapshots(symbols)
        return [asdict(s) for s in snaps]

    def account_overview(self, account_id: str | None = None) -> dict:
        endpoint = getattr(self.broker, "endpoint", self.settings.webull_api_endpoint)
        try:
            accounts = self.broker.list_accounts()
        except WebullApiError as exc:
            return {
                **exc.to_dict(),
                "hint": account_access_hint(endpoint=endpoint, account_id=account_id),
                "accounts": [],
                "balance": None,
                "positions": [],
                "open_orders": [],
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "error": str(exc),
                "endpoint": endpoint,
                "hint": account_access_hint(endpoint=endpoint, account_id=account_id),
                "accounts": [],
                "balance": None,
                "positions": [],
                "open_orders": [],
            }

        available = collect_account_ids(accounts)
        acct = account_id or self.settings.webull_account_id
        if not acct and available:
            acct = available[0]
        if not acct:
            return {
                "endpoint": endpoint,
                "accounts": accounts,
                "available_account_ids": available,
                "balance": None,
                "positions": [],
                "open_orders": [],
                "hint": account_access_hint(endpoint=endpoint),
            }
        if available and acct not in available:
            return {
                "error": (
                    f"WEBULL_ACCOUNT_ID={acct!r} is not in the OpenAPI account list "
                    f"for {endpoint}."
                ),
                "error_code": "ACCOUNT_ID_ENDPOINT_MISMATCH",
                "endpoint": endpoint,
                "requested_account_id": acct,
                "available_account_ids": available,
                "accounts": accounts,
                "balance": None,
                "positions": [],
                "open_orders": [],
                "hint": account_access_hint(endpoint=endpoint, account_id=acct),
            }
        try:
            balance = self.broker.get_balance(acct)
            positions = self.broker.get_positions(acct)
            orders = self.broker.get_open_orders(acct)
        except WebullApiError as exc:
            return {
                **exc.to_dict(),
                "requested_account_id": acct,
                "available_account_ids": available,
                "accounts": accounts,
                "hint": account_access_hint(endpoint=endpoint, account_id=acct),
                "balance": None,
                "positions": [],
                "open_orders": [],
            }
        return {
            "endpoint": endpoint,
            "account_id": acct,
            "available_account_ids": available,
            "accounts": accounts,
            "balance": asdict(balance),
            "positions": [asdict(p) for p in positions],
            "open_orders": [asdict(o) for o in orders],
        }

    def market_regime(self, benchmark: str = "SPY", lookback: int = 90) -> dict:
        engine = MarketRegimeEngine(
            self.market_data,
            benchmark=benchmark,
            lookback=lookback,
        )
        payload = engine.analyze().to_dict()
        snap_last = self._snapshot_last(benchmark)
        last_close = payload.get("features", {}).get("last_close")
        payload["session_context"] = {
            "bars_last_close": last_close,
            "snapshot_last": snap_last,
            "note": (
                "bars_last_close is the newest RTH daily close (sorted oldest→newest). "
                "It should roughly match snapshot_last in the same session. "
                "A large gap usually meant newest-first history was read as last_close, "
                "or an ETF was queried as the wrong category."
            ),
        }
        if snap_last and last_close:
            payload["session_context"]["last_close_vs_snapshot_pct"] = round(
                (float(last_close) / float(snap_last) - 1.0) * 100.0, 3
            )
        return stamp_research_lock(payload, command="regime")

    def scan_opportunities(
        self,
        *,
        benchmark: str = "SPY",
        lookback: int = 90,
        min_score: float = 55.0,
        max_results: int = 10,
        symbols: list[str] | None = None,
    ) -> dict:
        scanner = OpportunityScanner(
            self.market_data,
            universe=symbols,
            lookback=lookback,
            min_score=min_score,
            max_results=max_results,
            benchmark=benchmark,
        )
        return stamp_research_lock(scanner.scan().to_dict(), command="scan")

    def analyze_options(
        self,
        *,
        benchmark: str = "SPY",
        lookback: int = 90,
        min_equity_score: float = 55.0,
        min_option_score: float = 55.0,
        max_results: int = 10,
        symbols: list[str] | None = None,
    ) -> dict:
        chain = build_option_chain_provider(self.settings, self.market_data)
        engine = OptionsAnalysisEngine(
            self.market_data,
            chain_provider=chain,
            risk=self.risk,
            lookback=lookback,
            min_equity_score=min_equity_score,
            min_option_score=min_option_score,
            max_results=max_results,
            benchmark=benchmark,
            universe=symbols,
        )
        return stamp_research_lock(engine.analyze().to_dict(), command="options")

    def decide(
        self,
        *,
        benchmark: str = "SPY",
        lookback: int = 90,
        min_equity_score: float = 55.0,
        min_option_score: float = 55.0,
        max_results: int = 10,
        symbols: list[str] | None = None,
    ) -> dict:
        chain = build_option_chain_provider(self.settings, self.market_data)
        options_engine = OptionsAnalysisEngine(
            self.market_data,
            chain_provider=chain,
            risk=self.risk,
            lookback=lookback,
            min_equity_score=min_equity_score,
            min_option_score=min_option_score,
            max_results=max_results,
            benchmark=benchmark,
            universe=symbols,
        )
        engine = DecisionPackageEngine(
            options_engine=options_engine,
            catalyst_provider=self.catalyst_provider,
            fundamentals_provider=self.fundamentals_provider,
            critic=self.critic,
            risk=self.risk,
            max_packages=max_results,
        )
        return stamp_research_lock(engine.build().to_dict(), command="decide")

    def _snapshot_last(self, symbol: str) -> float | None:
        try:
            snaps = self.market_data.get_snapshots([symbol])
        except Exception:  # noqa: BLE001
            return None
        if not snaps or snaps[0].last is None:
            return None
        return float(snaps[0].last)
