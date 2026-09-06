"""Architecture Phase 10 — daily/weekly text report (no broker GO)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from trading_system.adversarial import (
    CompositeAdversarialCritic,
    NullLLMCritic,
    RuleBasedAdversarialCritic,
)
from trading_system.backtest import LongPremiumBacktester, synthetic_trend_bars
from trading_system.broker.mock import MockBrokerReadClient
from trading_system.cli import main
from trading_system.config import Settings
from trading_system.data.mock import MockMarketDataProvider
from trading_system.decision import DecisionPackageEngine
from trading_system.events import MockCatalystProvider
from trading_system.events.types import CatalystFixture
from trading_system.fundamentals import MockFundamentalsProvider
from trading_system.fundamentals.types import FundamentalsFixture
from trading_system.journal import PaperLedger
from trading_system.modes import LIVE_EXECUTION_UNLOCKED, PHASE, TradingMode
from trading_system.options.engine import OptionsAnalysisEngine
from trading_system.options.scoring import score_contract
from trading_system.options.types import OptionCandidate, OptionContract, OptionsAnalysisReport, occ_symbol
from trading_system.report import PHASE10_COMPLETE, ResearchReportBuilder
from trading_system.research_lock import RESEARCH_COMPLETE, research_complete_checklist
from trading_system.risk import load_risk_limits
from trading_system.risk.limits import RiskLimits
from trading_system.scanner.types import Direction, Opportunity, ScoreBreakdown, SetupType
from trading_system.services.runtime import ResearchRuntime


AS_OF = datetime(2026, 9, 6, 15, 0, tzinfo=timezone.utc)


def _limits() -> RiskLimits:
    return RiskLimits(
        account_equity_usd=1500.0,
        max_risk_per_trade_pct=0.10,
        max_simultaneous_positions=2,
        max_daily_loss_pct=0.05,
        max_weekly_loss_pct=0.10,
        emergency_stop=False,
    )


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


class SpyBroker(MockBrokerReadClient):
    def __init__(self) -> None:
        super().__init__(equity=1500)
        self.place_order_calls = 0

    def place_order(self, *args, **kwargs):  # noqa: ANN002, ANN003
        self.place_order_calls += 1
        return super().place_order(*args, **kwargs)


def _runtime(*, ledger: PaperLedger | None = None, broker: SpyBroker | None = None) -> ResearchRuntime:
    settings = _settings()
    risk = load_risk_limits(settings)
    return ResearchRuntime(
        settings=settings,
        market_data=MockMarketDataProvider(),
        broker=broker or SpyBroker(),
        risk=risk,
        paper_ledger=ledger or PaperLedger(path=None, risk=risk),
    )


def test_phase10_research_complete_without_live_unlock():
    assert PHASE == 10
    assert PHASE10_COMPLETE is True
    assert RESEARCH_COMPLETE is True
    assert LIVE_EXECUTION_UNLOCKED is False
    checklist = research_complete_checklist()
    assert checklist["daily_weekly_text_report"] is True
    assert checklist["paper_journal_loop"] is True
    assert checklist["sandbox_execution_adapter"] is False
    assert checklist["live_approval_unlock"] is False
    assert checklist["dashboard_ui"] is False
    assert checklist["historical_opra_backtest"] is False


def test_report_text_aggregates_required_sections():
    runtime = _runtime()
    payload = runtime.research_report(symbols=["AAPL", "MSFT"], min_equity_score=40.0, min_option_score=40.0)
    text = payload["text"]
    assert payload["research_complete"] is True
    assert payload["phase10_complete"] is True
    assert payload["period"] == "daily"
    assert payload["live_execution_unlocked"] is False
    assert payload["broker_go_allowed"] is False
    assert payload["go_signal"] is False
    assert "DAILY RESEARCH REPORT" in text
    assert "STATUS" in text
    assert "REGIME" in text
    assert "DECIDE" in text
    assert "PAPER JOURNAL" in text
    assert "BACKTEST POINTER" in text
    assert "live_execution_unlocked: false" in text
    assert "go_signal: false" in text
    assert "stand_aside" in text
    assert payload["decide_flags"]["prefer_stand_aside"] is True
    assert payload["decide_flags"]["go_signal"] is False
    for pkg in payload["packages"]:
        if pkg["incomplete_research"]:
            assert pkg["recommendation"] != "candidate"
            assert pkg["go_signal"] is False


def test_weekly_report_uses_seven_day_window():
    runtime = _runtime()
    payload = runtime.research_report(weekly=True, symbols=["AAPL"])
    assert payload["period"] == "weekly"
    assert "WEEKLY RESEARCH REPORT" in payload["text"]
    assert any("7-day" in n or "Weekly" in n for n in payload["notes"])
    assert payload["journal_snapshot"]["account"]["weekly_pnl_usd"] is not None
    assert payload["live_execution_unlocked"] is False


def test_report_points_at_recorded_backtest():
    ledger = PaperLedger(path=None, risk=_limits())
    report = LongPremiumBacktester(lookback=60).run(synthetic_trend_bars(n_up=90, n_down=20))
    ledger.record_backtest(report)
    runtime = _runtime(ledger=ledger)
    payload = runtime.research_report(symbols=["AAPL"])
    pointer = payload["backtest_pointer"]
    assert pointer["available"] is True
    assert pointer["symbol"]
    assert "backtest" in pointer["cli"]
    assert "not historical OPRA" in pointer["note"]
    assert "BACKTEST POINTER" in payload["text"]


def test_incomplete_packages_do_not_raise_paper_go_flags():
    runtime = _runtime()
    payload = runtime.research_report(symbols=["AAPL"], min_equity_score=40.0, min_option_score=40.0)
    assert payload["trade_recommendation"] is False
    assert payload["go_signals_allowed"] is False
    assert payload["decide_flags"]["candidates_paper_research"] == []
    assert payload["decide_flags"]["incomplete_research_count"] >= 1


def test_complete_candidate_may_set_paper_flags_never_broker_go():
    options = OptionsAnalysisEngine(
        MockMarketDataProvider(),
        risk=_limits(),
        universe=["AAPL"],
    )
    engine = DecisionPackageEngine(
        options_engine=options,
        catalyst_provider=MockCatalystProvider(
            {
                "AAPL": CatalystFixture(
                    earnings_date=date(2026, 10, 6),
                    earnings_status="upcoming",
                )
            }
        ),
        fundamentals_provider=MockFundamentalsProvider(
            {
                "AAPL": FundamentalsFixture(
                    latest_actual_eps=1.2,
                    latest_estimate_eps=1.1,
                    beat_miss="beat",
                )
            }
        ),
        critic=CompositeAdversarialCritic(RuleBasedAdversarialCritic(), NullLLMCritic()),
        risk=_limits(),
    )
    expiration = (AS_OF + timedelta(days=45)).date()
    contract = OptionContract(
        underlying="AAPL",
        right="CALL",
        expiration=expiration,
        strike=185.0,
        bid=1.17,
        ask=1.23,
        last=1.20,
        mid=1.20,
        volume=800,
        open_interest=2500,
        implied_volatility=0.30,
        delta=0.32,
        gamma=0.01,
        theta=-0.02,
        vega=0.05,
        as_of=AS_OF,
        symbol=occ_symbol("AAPL", expiration, "CALL", 185.0),
    )
    opportunity = Opportunity(
        symbol="AAPL",
        direction=Direction.LONG,
        setup=SetupType.PULLBACK_IN_TREND,
        scores=ScoreBreakdown(
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
        ),
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
    candidate = OptionCandidate(
        contract=contract,
        scores=score_contract(contract, limits=_limits()),
        equity_opportunity=opportunity,
        strategy="long_call",
        max_loss_usd=contract.premium_per_contract_usd,
    )
    built = engine.build(
        options_report=OptionsAnalysisReport(
            as_of=AS_OF,
            equity_candidates_considered=1,
            contracts_evaluated=1,
            candidates=(candidate,),
            rejected_counts={},
            notes=("test",),
        ),
        as_of=AS_OF,
    )
    payload = built.to_dict()
    pkg = payload["packages"][0]
    assert pkg["go_signal"] is False
    assert payload["live_execution_unlocked"] is False
    assert payload["broker_go_allowed"] is False
    paper = pkg["recommendation"] == "candidate" and not pkg["incomplete_research"]
    assert payload["trade_recommendation"] is paper
    assert payload["go_signals_allowed"] is paper
    assert pkg["paper_research_candidate"] is paper


def test_cli_report_is_text_only_and_never_places_orders(capsys):
    broker = SpyBroker()
    runtime = _runtime(broker=broker)
    payload = runtime.research_report(symbols=["AAPL"])
    assert broker.place_order_calls == 0
    with pytest.raises(RuntimeError):
        broker.place_order(symbol="AAPL")
    assert broker.place_order_calls == 1

    rc = main(["report", "--symbols", "AAPL"])
    assert rc == 0
    printed = capsys.readouterr().out
    assert "RESEARCH REPORT" in printed
    assert "STATUS" in printed
    assert "DECIDE" in printed
    assert printed.strip().startswith("=")
    assert '"packages"' not in printed
    assert payload["research_command"] == "report"


def test_cli_weekly_flag(capsys):
    rc = main(["report", "--weekly", "--symbols", "AAPL"])
    assert rc == 0
    printed = capsys.readouterr().out
    assert "WEEKLY RESEARCH REPORT" in printed
    assert "live_execution_unlocked: false" in printed


def test_report_builder_survives_section_errors():
    class Broken:
        def status(self):
            raise RuntimeError("status down")

        def market_regime(self, **kwargs):
            raise RuntimeError("regime down")

        def decide(self, **kwargs):
            raise RuntimeError("decide down")

        def journal(self):
            raise RuntimeError("journal down")

    report = ResearchReportBuilder(Broken()).build(symbols=["AAPL"])
    assert "status error" in " ".join(report.notes)
    assert report.decide_flags["prefer_stand_aside"] is True
    assert report.decide_flags["go_signal"] is False
    assert "RESEARCH REPORT" in report.text
