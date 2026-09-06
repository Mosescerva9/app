"""Architecture Phase 8 — Decision Packages, catalyst, adversarial rules."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from trading_system.adversarial import (
    CompositeAdversarialCritic,
    CritiqueContext,
    NullLLMCritic,
    RuleBasedAdversarialCritic,
)
from trading_system.cli import main
from trading_system.data.mock import MockMarketDataProvider
from trading_system.decision import DecisionPackageEngine
from trading_system.decision.types import DecisionPackage
from trading_system.events import MockCatalystProvider
from trading_system.events.parse import parse_earnings_rows, parse_filing_rows
from trading_system.events.scoring import score_catalyst
from trading_system.events.types import CatalystFixture
from trading_system.events.webull import WebullCatalystProvider
from trading_system.modes import LIVE_EXECUTION_UNLOCKED, PHASE
from trading_system.options.scoring import score_contract
from trading_system.options.types import OptionCandidate, OptionContract, OptionsAnalysisReport, occ_symbol
from trading_system.risk.limits import RiskLimits
from trading_system.scanner.types import Direction, Opportunity, ScoreBreakdown, SetupType
from trading_system.services.runtime import ResearchRuntime
from trading_system.config import Settings
from trading_system.modes import TradingMode
from trading_system.broker.mock import MockBrokerReadClient
from trading_system.risk import load_risk_limits


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


def _opportunity(*, symbol: str = "AAPL", technical: float = 70.0, overall: float = 72.0) -> Opportunity:
    return Opportunity(
        symbol=symbol,
        direction=Direction.LONG,
        setup=SetupType.PULLBACK_IN_TREND,
        scores=_scores(technical=technical, overall=overall),
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


def _contract(*, dte: int = 45, delta: float = 0.32, mid: float = 1.20) -> OptionContract:
    expiration = (AS_OF + timedelta(days=dte)).date()
    return OptionContract(
        underlying="AAPL",
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
        delta=delta,
        gamma=0.01,
        theta=-0.02,
        vega=0.05,
        as_of=AS_OF,
        symbol=occ_symbol("AAPL", expiration, "CALL", 185.0),
    )


def _candidate(opp: Opportunity | None = None, contract: OptionContract | None = None) -> OptionCandidate:
    contract = contract or _contract()
    opp = opp or _opportunity()
    return OptionCandidate(
        contract=contract,
        scores=score_contract(contract, limits=_limits()),
        equity_opportunity=opp,
        strategy="long_call",
        max_loss_usd=contract.premium_per_contract_usd,
    )


def _report(*candidates: OptionCandidate) -> OptionsAnalysisReport:
    return OptionsAnalysisReport(
        as_of=AS_OF,
        equity_candidates_considered=len(candidates),
        contracts_evaluated=len(candidates),
        candidates=tuple(candidates),
        rejected_counts={},
        notes=("test",),
    )


def _engine(catalyst=None) -> DecisionPackageEngine:
    from trading_system.options.engine import OptionsAnalysisEngine

    md = MockMarketDataProvider()
    options = OptionsAnalysisEngine(md, risk=_limits(), universe=["AAPL"])
    return DecisionPackageEngine(
        options_engine=options,
        catalyst_provider=catalyst or MockCatalystProvider(),
        critic=CompositeAdversarialCritic(RuleBasedAdversarialCritic(), NullLLMCritic()),
        risk=_limits(),
        max_packages=5,
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


REQUIRED_PACKAGE_KEYS = {
    "as_of",
    "symbol",
    "recommendation",
    "decision",
    "scores",
    "equity_opportunity",
    "option_candidate",
    "catalyst",
    "adversarial",
    "risk",
    "notes",
    "live_execution_unlocked",
}

REQUIRED_ADVERSARIAL_KEYS = {
    "why_trade_fails",
    "instant_reject_conditions",
    "better_strike_dte_or_stand_aside",
    "confidence_penalty",
}

REQUIRED_CATALYST_KEYS = {
    "available",
    "source",
    "earnings_date",
    "days_to_earnings",
    "event_flags",
    "score",
    "notes",
}


def test_phase_is_eight_and_execution_locked():
    assert PHASE == 8
    assert LIVE_EXECUTION_UNLOCKED is False


def test_decision_package_shape_includes_catalyst_and_adversarial():
    engine = _engine()
    report = engine.build(options_report=_report(_candidate()), as_of=AS_OF)
    assert report.packages
    payload = report.to_dict()
    assert payload["live_execution_unlocked"] is False
    assert payload["package_count"] == 1
    pkg = payload["packages"][0]
    assert REQUIRED_PACKAGE_KEYS <= set(pkg)
    assert REQUIRED_ADVERSARIAL_KEYS <= set(pkg["adversarial"])
    assert REQUIRED_CATALYST_KEYS <= set(pkg["catalyst"])
    scores = pkg["scores"]
    for key in (
        "technical",
        "regime_fit",
        "options_quality",
        "catalyst",
        "confidence",
        "overall",
    ):
        assert key in scores
    assert pkg["risk"]["long_premium_only"] is True
    assert pkg["risk"]["max_risk_per_trade_usd"] == 150.0
    assert pkg["live_execution_unlocked"] is False


def test_unavailable_catalyst_does_not_crash_and_lowers_confidence():
    engine = _engine(MockCatalystProvider())
    report = engine.build(options_report=_report(_candidate()), as_of=AS_OF)
    pkg = report.packages[0]
    assert pkg.catalyst.available is False
    assert pkg.catalyst.earnings_status == "unavailable"
    assert pkg.catalyst.score is None
    assert "earnings_date_unknown" in pkg.catalyst.event_flags
    assert any("unavailable" in n.lower() or "invent" in n.lower() for n in pkg.catalyst.notes)
    assert pkg.scores.confidence < pkg.scores.overall
    assert pkg.adversarial.confidence_penalty >= 15.0
    assert not pkg.catalyst.earnings_events
    assert not hasattr(pkg.catalyst, "headlines")
    assert "headlines" not in pkg.catalyst.to_dict()


def test_unknown_catalyst_and_weak_technicals_stand_aside():
    opp = _opportunity(technical=40.0, overall=48.0)
    engine = _engine(MockCatalystProvider())
    report = engine.build(options_report=_report(_candidate(opp)), as_of=AS_OF)
    pkg = report.packages[0]
    assert pkg.recommendation == "stand_aside"
    assert pkg.adversarial.stand_aside is True
    assert pkg.adversarial.reject is False
    assert any("catalyst unknown" in w.lower() for w in pkg.adversarial.why_trade_fails)
    assert "stand aside" in pkg.adversarial.better_strike_dte_or_stand_aside.lower()


def test_earnings_within_two_days_instant_reject():
    earn = AS_OF.date() + timedelta(days=2)
    catalyst = MockCatalystProvider(
        {"AAPL": CatalystFixture(earnings_date=earn, earnings_status="upcoming")}
    )
    engine = _engine(catalyst)
    report = engine.build(options_report=_report(_candidate()), as_of=AS_OF)
    pkg = report.packages[0]
    assert pkg.catalyst.available is True
    assert pkg.catalyst.days_to_earnings == 2
    assert "earnings_within_2d" in pkg.catalyst.event_flags
    assert pkg.recommendation == "reject"
    assert pkg.adversarial.reject is True
    assert "earnings_within_2d" in pkg.adversarial.instant_reject_conditions
    assert any("IV crush" in w or "iv crush" in w.lower() for w in pkg.adversarial.why_trade_fails)


def test_earnings_within_seven_days_stand_aside_not_crash():
    earn = AS_OF.date() + timedelta(days=6)
    catalyst = MockCatalystProvider(
        {"AAPL": CatalystFixture(earnings_date=earn, earnings_status="upcoming")}
    )
    engine = _engine(catalyst)
    pkg = engine.build(options_report=_report(_candidate()), as_of=AS_OF).packages[0]
    assert pkg.recommendation == "stand_aside"
    assert "earnings_within_7d" in pkg.catalyst.event_flags
    assert pkg.adversarial.reject is False


def test_known_distant_earnings_can_remain_candidate():
    earn = AS_OF.date() + timedelta(days=30)
    catalyst = MockCatalystProvider(
        {"AAPL": CatalystFixture(earnings_date=earn, earnings_status="upcoming")}
    )
    engine = _engine(catalyst)
    pkg = engine.build(options_report=_report(_candidate()), as_of=AS_OF).packages[0]
    assert pkg.catalyst.score is not None and pkg.catalyst.score >= 70
    assert pkg.recommendation in {"candidate", "watch"}
    assert pkg.adversarial.reject is False


def test_rule_critic_emergency_stop_reject():
    risk = RiskLimits(
        account_equity_usd=1500.0,
        max_risk_per_trade_pct=0.10,
        max_simultaneous_positions=2,
        max_daily_loss_pct=0.05,
        max_weekly_loss_pct=0.10,
        emergency_stop=True,
    )
    cat = MockCatalystProvider().get_catalyst("AAPL", as_of=AS_OF)
    critique = RuleBasedAdversarialCritic().critique(
        CritiqueContext(
            opportunity=_opportunity(),
            option=_candidate(),
            catalyst=cat,
            risk=risk,
        )
    )
    assert critique.reject is True
    assert "emergency_stop" in critique.instant_reject_conditions


def test_null_llm_overlay_does_not_change_rules():
    cat = MockCatalystProvider().get_catalyst("AAPL", as_of=AS_OF)
    ctx = CritiqueContext(
        opportunity=_opportunity(),
        option=_candidate(),
        catalyst=cat,
        risk=_limits(),
    )
    rules = RuleBasedAdversarialCritic().critique(ctx)
    composite = CompositeAdversarialCritic(RuleBasedAdversarialCritic(), NullLLMCritic()).critique(ctx)
    assert composite.confidence_penalty == rules.confidence_penalty
    assert composite.instant_reject_conditions == rules.instant_reject_conditions
    assert NullLLMCritic().critique(ctx) is None


def test_parse_official_earnings_and_filings_fields():
    rows = parse_earnings_rows(
        [
            {
                "expectedPublishDate": "2026-09-20",
                "epsActual": None,
                "epsEst": "1.25",
                "fiscalYear": 2026,
                "fiscalPeriod": 3,
            },
            {
                "expected_publish_date": "2026-06-20",
                "eps_actual": 1.1,
                "eps_est": 1.0,
            },
        ]
    )
    assert rows[0].status == "upcoming"
    assert rows[0].expected_publish_date == date(2026, 9, 20)
    assert rows[0].eps_estimate == 1.25
    assert rows[1].status == "published"
    filings = parse_filing_rows(
        {
            "filings": [
                {
                    "title": "Form 8-K current report",
                    "url": "https://www.sec.gov/example",
                    "publishDate": "2026-09-01",
                }
            ]
        }
    )
    assert filings[0].form_hint in {"8-K", "8K"}
    assert filings[0].publish_date == date(2026, 9, 1)


def test_webull_provider_missing_fundamentals_is_unavailable():
    provider = WebullCatalystProvider(data_client=object(), api_endpoint="api.sandbox.webull.com")
    snap = provider.get_catalyst("NVDA", as_of=AS_OF)
    assert snap.available is False
    assert snap.earnings_status == "unavailable"
    assert "fundamentals" in snap.notes[0].lower() or "fundamentals" in (snap.raw_error + snap.notes[0]).lower()


class _FakeRes:
    def __init__(self, body, status=200):
        self.status_code = status
        self._body = body

    def json(self):
        return self._body


class _FakeFund:
    def get_earnings_calendar(self, symbol, category="US_STOCK"):
        return _FakeRes(
            [
                {
                    "expectedPublishDate": "2026-10-06",
                    "epsActual": None,
                    "epsEst": "0.90",
                }
            ]
        )

    def get_sec_filings(self, symbol, category="US_STOCK"):
        return _FakeRes({"filings": []})


def test_webull_provider_uses_official_calendar_payload():
    client = type("C", (), {"fundamentals": _FakeFund()})()
    provider = WebullCatalystProvider(data_client=client, api_endpoint="api.webull.com")
    snap = provider.get_catalyst("MSFT", as_of=AS_OF)
    assert snap.available is True
    assert snap.source == "webull"
    assert snap.earnings_date == date(2026, 10, 6)
    assert snap.days_to_earnings == 30
    assert snap.score is not None
    assert any("earnings-calendar" in n for n in snap.notes)


def test_catalyst_score_none_when_unavailable():
    assert score_catalyst(
        available=False,
        earnings_date=None,
        days_to_earnings=None,
        earnings_status="unavailable",
    ) is None
    assert score_catalyst(
        available=True,
        earnings_date=date(2026, 9, 8),
        days_to_earnings=2,
        earnings_status="upcoming",
    ) == 10.0


def test_runtime_decide_and_cli_emit_packages(capsys):
    settings = _settings()
    runtime = ResearchRuntime(
        settings=settings,
        market_data=MockMarketDataProvider(),
        broker=MockBrokerReadClient(equity=1500),
        risk=load_risk_limits(settings),
        catalyst_provider=MockCatalystProvider(),
    )
    status = runtime.status()
    assert status["phase"] == 8
    assert status["live_execution_unlocked"] is False
    assert status["catalyst_provider"] == "mock"
    payload = runtime.decide(symbols=["AAPL", "MSFT"], min_equity_score=40.0, min_option_score=40.0)
    assert "packages" in payload
    assert payload["live_execution_unlocked"] is False
    for pkg in payload["packages"]:
        assert REQUIRED_PACKAGE_KEYS <= set(pkg)
        assert REQUIRED_ADVERSARIAL_KEYS <= set(pkg["adversarial"])

    rc = main(["decide", "--symbols", "AAPL", "--min-equity-score", "40", "--min-option-score", "40"])
    assert rc == 0
    printed = capsys.readouterr().out
    assert "packages" in printed
    assert "adversarial" in printed
    assert "catalyst" in printed


def test_empty_options_report_still_emits_packages():
    engine = _engine()
    report = engine.build(options_report=_report(), as_of=AS_OF)
    assert report.packages
    pkg = report.packages[0].to_dict()
    assert REQUIRED_PACKAGE_KEYS <= set(pkg)
    assert REQUIRED_ADVERSARIAL_KEYS <= set(pkg["adversarial"])
    assert pkg["catalyst"]["available"] is False
    assert pkg["recommendation"] in {"stand_aside", "reject", "watch", "candidate"}


def test_decision_package_dataclass_roundtrip_keys():
    engine = _engine()
    pkg = engine.build(options_report=_report(_candidate()), as_of=AS_OF).packages[0]
    assert isinstance(pkg, DecisionPackage)
    dumped = pkg.to_dict()
    assert dumped["option_candidate"]["strategy"] == "long_call"
    assert dumped["catalyst"]["source"] == "mock"
