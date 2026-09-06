"""Architecture Phase 9 — paper ledger loop (no broker orders)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import pytest

from trading_system.adversarial import (
    CompositeAdversarialCritic,
    NullLLMCritic,
    RuleBasedAdversarialCritic,
)
from trading_system.broker.base import BrokerReadClient
from trading_system.broker.mock import MockBrokerReadClient
from trading_system.cli import main
from trading_system.config import Settings
from trading_system.data.mock import MockMarketDataProvider
from trading_system.decision import DecisionPackageEngine
from trading_system.events import MockCatalystProvider
from trading_system.events.types import CatalystFixture
from trading_system.fundamentals import MockFundamentalsProvider
from trading_system.fundamentals.types import FundamentalsFixture
from trading_system.journal import PHASE9_COMPLETE, PaperLedger
from trading_system.modes import LIVE_EXECUTION_UNLOCKED, PHASE, TradingMode
from trading_system.options.engine import OptionsAnalysisEngine
from trading_system.options.scoring import score_contract
from trading_system.options.types import OptionCandidate, OptionContract, OptionsAnalysisReport, occ_symbol
from trading_system.research_lock import RESEARCH_COMPLETE, research_complete_checklist
from trading_system.risk import load_risk_limits
from trading_system.risk.limits import RiskLimits
from trading_system.scanner.types import Direction, Opportunity, ScoreBreakdown, SetupType
from trading_system.services.runtime import ResearchRuntime


AS_OF = datetime(2026, 9, 6, 15, 0, tzinfo=timezone.utc)


def _limits(**overrides) -> RiskLimits:
    base = dict(
        account_equity_usd=1500.0,
        max_risk_per_trade_pct=0.10,
        max_simultaneous_positions=2,
        max_daily_loss_pct=0.05,
        max_weekly_loss_pct=0.10,
        emergency_stop=False,
    )
    base.update(overrides)
    return RiskLimits(**base)


def _settings() -> Settings:
    return Settings(
        mode=TradingMode.RESEARCH,
        market_data_provider="mock",
        broker_provider="mock",
        webull_app_key="",
        webull_app_secret="",
        webull_region="us",
        webull_api_endpoint="api.sandbox.webull.com",
        webull_account_id="",
        account_equity_usd=1500.0,
        max_risk_per_trade_pct=0.10,
        max_simultaneous_positions=2,
        max_daily_loss_pct=0.05,
        max_weekly_loss_pct=0.10,
        emergency_stop=False,
        log_level="INFO",
    )


def _scores(**overrides) -> ScoreBreakdown:
    base = dict(
        technical=70.0,
        momentum=65.0,
        liquidity=80.0,
        regime_fit=75.0,
        risk_reward=70.0,
        crowding_risk=20.0,
        options_quality=None,
        catalyst=None,
        fundamental=None,
        overall=72.0,
        weights_used={"regime_fit": 0.22},
        missing_dimensions=("options_quality", "catalyst", "fundamental"),
    )
    base.update(overrides)
    return ScoreBreakdown(**base)


def _opportunity(*, symbol: str = "AAPL") -> Opportunity:
    return Opportunity(
        symbol=symbol,
        direction=Direction.LONG,
        setup=SetupType.PULLBACK_IN_TREND,
        scores=_scores(),
        entry=180.0,
        stop=172.8,
        target=194.4,
        risk_reward=2.0,
        regime="weak_bull",
        regime_confidence=0.6,
        why=["test"],
        do_not_trade_if=[],
        invalidation=["close beyond stop"],
        decision="CANDIDATE",
    )


def _contract(*, symbol: str = "AAPL", mid: float = 1.20) -> OptionContract:
    expiration = (AS_OF + timedelta(days=45)).date()
    return OptionContract(
        underlying=symbol,
        right="CALL",
        expiration=expiration,
        strike=185.0,
        bid=mid - 0.03,
        ask=mid + 0.03,
        last=mid,
        mid=mid,
        volume=800,
        open_interest=2500,
        implied_volatility=0.30,
        delta=0.32,
        gamma=0.01,
        theta=-0.02,
        vega=0.05,
        as_of=AS_OF,
        symbol=occ_symbol(symbol, expiration, "CALL", 185.0),
    )


def _candidate(
    *,
    symbol: str = "AAPL",
    mid: float = 1.20,
) -> OptionCandidate:
    contract = _contract(symbol=symbol, mid=mid)
    return OptionCandidate(
        contract=contract,
        scores=score_contract(contract, limits=_limits()),
        equity_opportunity=_opportunity(symbol=symbol),
        strategy="long_call",
        max_loss_usd=contract.premium_per_contract_usd,
    )


def _engine() -> DecisionPackageEngine:
    options = OptionsAnalysisEngine(
        MockMarketDataProvider(),
        risk=_limits(),
        universe=["AAPL", "MSFT"],
    )
    return DecisionPackageEngine(
        options_engine=options,
        catalyst_provider=MockCatalystProvider(
            {
                "AAPL": CatalystFixture(
                    earnings_date=date(2026, 10, 6),
                    earnings_status="upcoming",
                ),
                "MSFT": CatalystFixture(
                    earnings_date=date(2026, 10, 8),
                    earnings_status="upcoming",
                ),
            }
        ),
        fundamentals_provider=MockFundamentalsProvider(
            {
                "AAPL": FundamentalsFixture(
                    latest_actual_eps=1.2,
                    latest_estimate_eps=1.1,
                    beat_miss="beat",
                ),
                "MSFT": FundamentalsFixture(
                    latest_actual_eps=2.2,
                    latest_estimate_eps=2.0,
                    beat_miss="beat",
                ),
            }
        ),
        critic=CompositeAdversarialCritic(RuleBasedAdversarialCritic(), NullLLMCritic()),
        risk=_limits(),
        max_packages=5,
    )


def _complete_package(*, symbol: str = "AAPL", mid: float = 1.20):
    report = _engine().build(
        options_report=OptionsAnalysisReport(
            as_of=AS_OF,
            equity_candidates_considered=1,
            contracts_evaluated=1,
            candidates=(_candidate(symbol=symbol, mid=mid),),
            rejected_counts={},
            notes=("test",),
        ),
        as_of=AS_OF,
    )
    return report.packages[0]


def _openable_package(*, symbol: str = "AAPL", mid: float = 1.20):
    pkg = _complete_package(symbol=symbol, mid=mid)
    assert pkg.incomplete_research is False
    return replace(pkg, recommendation="candidate", go_signal=False)


def _incomplete_package():
    options = OptionsAnalysisEngine(MockMarketDataProvider(), risk=_limits(), universe=["AAPL"])
    engine = DecisionPackageEngine(
        options_engine=options,
        catalyst_provider=MockCatalystProvider(),
        fundamentals_provider=MockFundamentalsProvider(),
        critic=CompositeAdversarialCritic(RuleBasedAdversarialCritic(), NullLLMCritic()),
        risk=_limits(),
    )
    report = engine.build(
        options_report=OptionsAnalysisReport(
            as_of=AS_OF,
            equity_candidates_considered=1,
            contracts_evaluated=1,
            candidates=(_candidate(),),
            rejected_counts={},
            notes=("test",),
        ),
        as_of=AS_OF,
    )
    return report.packages[0]


class SpyBroker(MockBrokerReadClient):
    def __init__(self) -> None:
        super().__init__(equity=1500)
        self.place_order_calls = 0

    def place_order(self, *args, **kwargs):  # noqa: ANN002, ANN003
        self.place_order_calls += 1
        return super().place_order(*args, **kwargs)


def test_phase9_complete_but_research_and_live_stay_locked():
    assert PHASE == 9
    assert PHASE9_COMPLETE is True
    assert RESEARCH_COMPLETE is False
    assert LIVE_EXECUTION_UNLOCKED is False
    checklist = research_complete_checklist()
    assert checklist["paper_journal_loop"] is True
    assert checklist["dashboard_grok_brief"] is False
    assert checklist["historical_opra_backtest"] is False
    assert checklist["live_approval_unlock"] is False


def test_open_complete_candidate_debits_cash_and_creates_position():
    ledger = PaperLedger(path=None, risk=_limits())
    pkg = _openable_package(mid=1.20)
    assert pkg.incomplete_research is False
    assert pkg.recommendation == "candidate"
    result = ledger.open_from_package(pkg)
    assert result.accepted is True
    assert result.broker_order_placed is False if hasattr(result, "broker_order_placed") else True
    assert result.to_dict()["broker_order_placed"] is False
    snap = ledger.account_snapshot()
    assert snap.cash_usd == 1380.0
    assert snap.market_value_usd == 120.0
    assert snap.equity_usd == 1500.0
    assert snap.open_position_count == 1
    assert snap.cash_usd >= 0
    assert ledger.open_positions()[0].strategy == "long_call"


def test_incomplete_package_stands_aside_and_does_not_move_cash():
    ledger = PaperLedger(path=None, risk=_limits())
    pkg = _incomplete_package()
    assert pkg.incomplete_research is True
    result = ledger.open_from_package(pkg)
    assert result.accepted is False
    assert result.recommendation == "stand_aside"
    assert result.reason == "incomplete_research"
    assert ledger.account_snapshot().cash_usd == 1500.0
    assert ledger.open_positions() == ()


def test_close_realizes_pnl_without_negative_cash():
    ledger = PaperLedger(path=None, risk=_limits())
    opened = ledger.open_from_package(_openable_package(mid=1.20))
    closed = ledger.close_position(opened.position_id, exit_mark_usd=0.0)
    assert closed.accepted is True
    snap = ledger.account_snapshot()
    assert snap.cash_usd == 1380.0
    assert snap.cash_usd >= 0
    assert snap.open_position_count == 0
    assert snap.realized_pnl_usd == -120.0
    assert snap.equity_usd == 1380.0


def test_close_winner_returns_premium_to_cash():
    ledger = PaperLedger(path=None, risk=_limits())
    opened = ledger.open_from_package(_openable_package(mid=1.00))
    closed = ledger.close_position(opened.position_id, exit_mark_usd=1.80)
    assert closed.accepted is True
    snap = ledger.account_snapshot()
    assert snap.cash_usd == 1580.0
    assert snap.realized_pnl_usd == 80.0
    assert snap.cash_usd >= 0


def test_risk_per_trade_cap_blocks_oversize_debit():
    ledger = PaperLedger(path=None, risk=_limits())
    result = ledger.open_from_package(_openable_package(mid=1.20), quantity=2)
    assert result.accepted is False
    assert result.reason == "risk_per_trade_cap"
    assert ledger.account_snapshot().cash_usd == 1500.0


def test_insufficient_cash_cannot_go_negative():
    ledger = PaperLedger(path=None, risk=_limits(), starting_cash_usd=80.0)
    result = ledger.open_from_package(_openable_package(mid=1.20))
    assert result.accepted is False
    assert result.reason == "insufficient_cash"
    assert ledger.account_snapshot().cash_usd == 80.0
    assert ledger.account_snapshot().cash_usd >= 0


def test_max_simultaneous_positions_cap():
    ledger = PaperLedger(path=None, risk=_limits())
    first = ledger.open_from_package(_openable_package(symbol="AAPL", mid=1.00))
    second = ledger.open_from_package(_openable_package(symbol="MSFT", mid=1.00))
    third = ledger.open_from_package(_openable_package(symbol="AAPL", mid=0.90))
    assert first.accepted and second.accepted
    assert third.accepted is False
    assert third.reason == "max_positions"
    assert ledger.account_snapshot().open_position_count == 2
    assert ledger.account_snapshot().cash_usd == 1300.0


def test_daily_loss_cap_blocks_new_opens():
    ledger = PaperLedger(path=None, risk=_limits())
    opened = ledger.open_from_package(_openable_package(mid=1.20))
    ledger.close_position(opened.position_id, exit_mark_usd=0.40)  # -80 vs $75 daily cap
    blocked = ledger.open_from_package(_openable_package(symbol="MSFT", mid=1.00))
    assert blocked.accepted is False
    assert blocked.reason == "daily_loss_cap"
    assert ledger.account_snapshot().cash_usd >= 0


def test_weekly_loss_cap_blocks_new_opens():
    risk = _limits(max_daily_loss_pct=0.20, max_weekly_loss_pct=0.05)  # weekly $75
    ledger = PaperLedger(path=None, risk=risk)
    opened = ledger.open_from_package(_openable_package(mid=1.20), now=AS_OF - timedelta(days=3))
    # Close earlier in the ISO week so the daily window is clean; weekly still includes it.
    earlier = AS_OF - timedelta(days=3)
    ledger.close_position(opened.position_id, exit_mark_usd=0.40, now=earlier)
    blocked = ledger.open_from_package(_openable_package(symbol="MSFT", mid=1.00), now=AS_OF)
    assert blocked.accepted is False
    assert blocked.reason == "weekly_loss_cap"


def test_emergency_stop_refuses_open():
    ledger = PaperLedger(path=None, risk=_limits(emergency_stop=True))
    result = ledger.open_from_package(_openable_package())
    assert result.accepted is False
    assert result.reason == "emergency_stop"


def test_file_roundtrip_preserves_open_position(tmp_path):
    path = tmp_path / "paper.json"
    ledger = PaperLedger(path=path, risk=_limits())
    opened = ledger.open_from_package(_openable_package(mid=1.10))
    assert opened.accepted is True
    reloaded = PaperLedger(path=path, risk=_limits())
    snap = reloaded.account_snapshot()
    assert snap.open_position_count == 1
    assert snap.cash_usd == 1390.0
    assert reloaded.open_positions()[0].position_id == opened.position_id


def test_runtime_status_wires_journal_and_keeps_locks():
    settings = _settings()
    runtime = ResearchRuntime(
        settings=settings,
        market_data=MockMarketDataProvider(),
        broker=SpyBroker(),
        risk=load_risk_limits(settings),
        paper_ledger=PaperLedger(path=None, risk=load_risk_limits(settings)),
    )
    status = runtime.status()
    assert status["phase"] == 9
    assert status["paper_journal"] == "paper_ledger"
    assert status["phase9_complete"] is True
    assert status["research_complete"] is False
    assert status["go_signals_allowed"] is False
    assert status["trade_recommendation"] is False
    assert status["live_execution_unlocked"] is False
    assert status["paper_account"]["cash_usd"] == 1500.0
    assert status["research_complete_checklist"]["paper_journal_loop"] is True
    assert status["research_complete_checklist"]["dashboard_grok_brief"] is False


def test_runtime_paper_open_stands_aside_when_mock_research_incomplete():
    settings = _settings()
    broker = SpyBroker()
    runtime = ResearchRuntime(
        settings=settings,
        market_data=MockMarketDataProvider(),
        broker=broker,
        risk=load_risk_limits(settings),
        paper_ledger=PaperLedger(path=None, risk=load_risk_limits(settings)),
    )
    payload = runtime.paper_open("AAPL")
    assert payload["accepted"] is False
    assert payload["recommendation"] == "stand_aside"
    assert payload["reason"] == "incomplete_research"
    assert payload["broker_order_placed"] is False
    assert payload["trade_recommendation"] is False
    assert payload["go_signals_allowed"] is False
    assert broker.place_order_calls == 0
    with pytest.raises(RuntimeError):
        broker.place_order(symbol="AAPL")
    assert broker.place_order_calls == 1


def test_cli_paper_commands_are_paper_only(capsys):
    rc = main(["paper-note", "reviewed AAPL — standing aside", "--symbol", "AAPL"])
    assert rc == 0
    printed = capsys.readouterr().out
    assert "paper_note" in printed
    assert "broker_order_placed" in printed
    assert "trade_recommendation" in printed

    rc = main(["paper-open", "AAPL"])
    assert rc == 0
    printed = capsys.readouterr().out
    assert "stand_aside" in printed
    assert "paper-open" in printed or "paper_open" in printed
    assert "research_complete" in printed


def test_cli_journal_shows_real_ledger(capsys):
    rc = main(["journal"])
    assert rc == 0
    printed = capsys.readouterr().out
    assert "architecture_9_paper_journal" in printed
    assert "phase9_complete" in printed
    assert "paper_ledger" in printed


def test_spy_broker_type_is_read_only():
    assert issubclass(SpyBroker, BrokerReadClient)
