"""Phase 2 scaffold tests — mock providers only (no live Webull calls)."""

from __future__ import annotations

import pytest

from trading_system.broker.mock import MockBrokerReadClient
from trading_system.config import Settings
from trading_system.data.mock import MockMarketDataProvider
from trading_system.modes import LIVE_EXECUTION_UNLOCKED, PHASE, TradingMode, assert_mode_allowed
from trading_system.risk import load_risk_limits
from trading_system.services.runtime import ResearchRuntime


def _settings(**overrides) -> Settings:
    base = dict(
        mode=TradingMode.RESEARCH,
        market_data_provider="mock",
        broker_provider="mock",
        webull_app_key="",
        webull_app_secret="",
        webull_region="us",
        webull_api_endpoint="api.sandbox.webull.com",
        webull_account_id="",
        account_equity_usd=1000.0,
        max_risk_per_trade_pct=0.04,
        max_simultaneous_positions=2,
        max_daily_loss_pct=0.05,
        max_weekly_loss_pct=0.10,
        emergency_stop=False,
        log_level="INFO",
    )
    base.update(overrides)
    return Settings(**base)


def test_mock_bars_and_snapshots():
    md = MockMarketDataProvider()
    bars = md.get_history_bars("AAPL", timespan="D", count=10)
    assert len(bars) == 10
    assert bars[0].symbol == "AAPL"
    assert bars[-1].close > 0
    snaps = md.get_snapshots(["AAPL", "SPY"])
    assert {s.symbol for s in snaps} == {"AAPL", "SPY"}
    opts = md.get_option_snapshots(["AAPL260619C00200000"])
    assert opts[0].bid is not None and opts[0].ask is not None


def test_mock_broker_reads_and_blocks_orders():
    broker = MockBrokerReadClient(equity=1000)
    accounts = broker.list_accounts()
    assert accounts[0]["account_id"] == "MOCK-001"
    bal = broker.get_balance("MOCK-001")
    assert bal.total_equity == 1000
    assert broker.get_positions("MOCK-001") == []
    assert broker.get_open_orders("MOCK-001") == []
    with pytest.raises(RuntimeError, match="Phase 2|disabled|locked|disabled in Phase"):
        broker.place_order(symbol="AAPL")


def test_risk_limits_math_and_stop():
    settings = _settings()
    risk = load_risk_limits(settings)
    assert risk.max_risk_per_trade_usd == 40.0
    assert risk.max_daily_loss_usd == 50.0
    assert risk.max_weekly_loss_usd == 100.0
    risk.assert_can_trade()

    stopped = load_risk_limits(_settings(emergency_stop=True))
    with pytest.raises(RuntimeError, match="EMERGENCY_STOP"):
        stopped.assert_can_trade()


def test_live_mode_locked():
    assert LIVE_EXECUTION_UNLOCKED is False
    with pytest.raises(RuntimeError, match="locked"):
        assert_mode_allowed(TradingMode.LIVE_APPROVAL)


def test_runtime_status_and_fetch():
    settings = _settings()
    runtime = ResearchRuntime(
        settings=settings,
        market_data=MockMarketDataProvider(),
        broker=MockBrokerReadClient(equity=1000),
        risk=load_risk_limits(settings),
    )
    status = runtime.status()
    assert status["phase"] == PHASE == 3
    assert status["mode"] == "RESEARCH"
    assert status["live_execution_unlocked"] is False
    assert status["risk"]["max_risk_per_trade_usd"] == 40.0
    bars = runtime.fetch_bars("MSFT", count=5)
    assert len(bars) == 5
    snaps = runtime.fetch_snapshots(["QQQ"])
    assert snaps[0]["symbol"] == "QQQ"
    acct = runtime.account_overview()
    assert acct["balance"]["total_equity"] == 1000
