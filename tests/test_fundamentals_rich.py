"""Richer official fundamentals: indicators, statements, industry. No invented numbers."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from trading_system.decision import DecisionPackageEngine
from trading_system.events import MockCatalystProvider
from trading_system.events.types import CatalystFixture
from trading_system.fundamentals import MockFundamentalsProvider
from trading_system.fundamentals.parse import (
    blend_fundamental_score,
    parse_balance_periods,
    parse_income_periods,
    parse_indicators,
    parse_industry_comparison,
)
from trading_system.fundamentals.types import (
    FundamentalsFixture,
    StatementPeriod,
)
from trading_system.fundamentals.webull import WebullFundamentalsProvider
from trading_system.options.engine import OptionsAnalysisEngine
from trading_system.options.scoring import score_contract
from trading_system.options.types import OptionCandidate, OptionContract, OptionsAnalysisReport, occ_symbol
from trading_system.risk.limits import RiskLimits
from trading_system.scanner.types import Direction, Opportunity, ScoreBreakdown, SetupType
from trading_system.data.mock import MockMarketDataProvider


AS_OF = datetime(2026, 9, 6, 15, 0, tzinfo=timezone.utc)


class _FakeRes:
    def __init__(self, body, status=200):
        self.status_code = status
        self._body = body

    def json(self):
        return self._body


class _RichFund:
    def get_forecast_eps(self, symbol, category="US_STOCK"):
        return _FakeRes(
            [
                {
                    "fiscalYear": 2026,
                    "fiscalPeriod": 2,
                    "actual": "1.10",
                    "est": "1.00",
                    "reported": True,
                }
            ]
        )

    def get_financials_indicators(self, symbol, category="US_STOCK", type=None, count=None):
        return _FakeRes(
            {
                "currency": "USD",
                "values": {
                    "roe": [{"fiscal_year": 2025, "fiscal_period": 4, "value": "0.21"}],
                    "net_margin": [{"fiscal_year": 2025, "fiscal_period": 4, "value": "0.18"}],
                    "debt_to_assets": [{"fiscal_year": 2025, "fiscal_period": 4, "value": "0.40"}],
                    "roa": [{"fiscal_year": 2025, "fiscal_period": 4, "value": "0.12"}],
                },
            }
        )

    def get_financials_income(self, symbol, category="US_STOCK", type=None, count=None):
        return _FakeRes(
            [
                {
                    "fiscal_year": 2025,
                    "fiscal_period": 4,
                    "end_date": "2025-09-27",
                    "currency": "USD",
                    "total_revenue": "416161000000",
                    "net_income": "112010000000",
                    "diluted_eps_incl_extra": "7.46",
                }
            ]
        )

    def get_financials_cashflow(self, symbol, category="US_STOCK", type=None, count=None):
        return _FakeRes(
            [{"fiscal_year": 2025, "fiscal_period": 4, "cfo": "14747000000", "capex": "-8527000000"}]
        )

    def get_financials_balance_sheet(self, symbol, category="US_STOCK", type=None, count=None):
        return _FakeRes(
            [
                {
                    "fiscal_year": 2025,
                    "fiscal_period": 4,
                    "total_assets": "379297000000",
                    "total_liab": "291107000000",
                    "total_equity": "88190000000",
                    "cash": "30826000000",
                }
            ]
        )

    def get_industry_comparison(self, symbol, category="US_STOCK", sort_by=None):
        return _FakeRes(
            {
                "fiscal_year": 2026,
                "fiscal_period": 1,
                "industry_name": "Phones & Handheld Devices",
                "type": "ROE",
                "data": [
                    {"symbol": "AAPL", "name": "Apple", "rank": 2, "value": "1.47"},
                    {"symbol": "PEER", "name": "Peer", "rank": 1, "value": "1.80"},
                ],
            }
        )


class _PartialFund:
    """EPS works; statements raise. Must degrade, not invent."""

    def get_forecast_eps(self, symbol, category="US_STOCK"):
        return _FakeRes(
            [{"fiscalYear": 2026, "fiscalPeriod": 1, "actual": "2.0", "est": "1.9", "reported": True}]
        )

    def get_financials_indicators(self, symbol, category="US_STOCK", type=None, count=None):
        raise RuntimeError("entitlement")

    def get_financials_income(self, symbol, category="US_STOCK", type=None, count=None):
        raise RuntimeError("entitlement")

    def get_financials_cashflow(self, symbol, category="US_STOCK", type=None, count=None):
        raise RuntimeError("entitlement")

    def get_financials_balance_sheet(self, symbol, category="US_STOCK", type=None, count=None):
        raise RuntimeError("entitlement")

    def get_industry_comparison(self, symbol, category="US_STOCK", sort_by=None):
        raise RuntimeError("entitlement")


def test_parse_official_indicator_and_statement_fields():
    latest, points = parse_indicators(
        {
            "currency": "USD",
            "values": {
                "roe": [{"fiscal_year": 2025, "fiscal_period": 4, "value": "0.2133"}],
                "invented_ratio": [{"fiscal_year": 2025, "value": "9.99"}],
            },
        }
    )
    assert latest["roe"] == 0.2133
    assert "invented_ratio" not in latest
    assert points[0].name == "roe"

    income = parse_income_periods(
        [
            {
                "fiscal_year": 2025,
                "fiscal_period": 0,
                "total_revenue": "416161000000",
                "net_income": "112010000000",
            }
        ]
    )
    assert income[0].fields["total_revenue"] == 416161000000.0
    assert "sga_exp" not in income[0].fields  # not in the surfaced official subset

    bal = parse_balance_periods(
        [{"fiscalYear": 2025, "fiscalPeriod": 4, "totalAssets": "100", "totalEquity": "40"}]
    )
    assert bal[0].fields["total_assets"] == 100.0
    assert bal[0].fields["total_equity"] == 40.0


def test_parse_industry_comparison_official_fields():
    snap = parse_industry_comparison(
        {
            "industry_name": "Phones & Handheld Devices",
            "type": "ROE",
            "fiscal_year": 2026,
            "data": [{"symbol": "AAPL", "name": "Apple", "rank": 2, "value": "1.47"}],
        },
        symbol="AAPL",
    )
    assert snap.available is True
    assert snap.self_rank == 2
    assert snap.industry_name == "Phones & Handheld Devices"


def test_webull_provider_uses_official_statement_payloads():
    client = type("C", (), {"fundamentals": _RichFund()})()
    provider = WebullFundamentalsProvider(data_client=client, api_endpoint="api.webull.com")
    snap = provider.get_fundamentals("AAPL")
    assert snap.available is True
    assert snap.source == "webull"
    assert snap.beat_miss == "beat"
    assert snap.statements_status == "present"
    assert snap.latest_indicators["roe"] == 0.21
    assert snap.income is not None
    assert snap.income.fields["total_revenue"] == 416161000000.0
    assert snap.cashflow is not None
    assert snap.balance is not None
    assert snap.industry is not None and snap.industry.self_rank == 2
    assert snap.score is not None and snap.score > 70
    blob = " ".join(snap.notes)
    assert "financial/indicators" in blob
    assert "financial/income" in blob


def test_webull_etf_skips_corporate_statements():
    client = type("C", (), {"fundamentals": _RichFund()})()
    provider = WebullFundamentalsProvider(data_client=client)
    snap = provider.get_fundamentals("SPY")
    assert snap.available is True
    assert snap.beat_miss == "not_applicable"
    assert snap.statements_status == "not_applicable"
    assert snap.income is None
    assert not snap.latest_indicators


def test_partial_failure_does_not_invent_statements():
    client = type("C", (), {"fundamentals": _PartialFund()})()
    provider = WebullFundamentalsProvider(data_client=client)
    snap = provider.get_fundamentals("MSFT")
    assert snap.available is True
    assert snap.beat_miss == "beat"
    assert snap.income is None
    assert snap.cashflow is None
    assert snap.balance is None
    assert snap.latest_indicators == {}
    assert snap.statements_status == "partial"
    assert any("not inventing" in n.lower() for n in snap.notes)


def test_missing_sdk_fundamentals_is_unavailable():
    provider = WebullFundamentalsProvider(data_client=object())
    snap = provider.get_fundamentals("NVDA")
    assert snap.available is False
    assert snap.beat_miss == "unavailable"
    assert snap.statements_status == "unavailable"


def test_blend_score_skips_missing_official_keys():
    assert blend_fundamental_score(eps_score=None, indicators={}, income=None) is None
    only_eps = blend_fundamental_score(eps_score=72.0, indicators={}, income=None)
    richer = blend_fundamental_score(
        eps_score=72.0,
        indicators={"roe": 0.21, "net_margin": 0.18, "debt_to_assets": 0.4},
        income=StatementPeriod(
            kind="income",
            fiscal_year=2025,
            fiscal_period=4,
            end_date=None,
            publish_date=None,
            currency="USD",
            fields={"total_revenue": 1.0, "net_income": 0.2},
        ),
    )
    assert only_eps == 72.0
    assert richer is not None and richer > only_eps


def test_statements_only_lifts_fundamentals_dimension():
    from trading_system.adversarial import CompositeAdversarialCritic, NullLLMCritic, RuleBasedAdversarialCritic

    def _limits() -> RiskLimits:
        return RiskLimits(
            account_equity_usd=1500.0,
            max_risk_per_trade_pct=0.10,
            max_simultaneous_positions=2,
            max_daily_loss_pct=0.05,
            max_weekly_loss_pct=0.10,
            emergency_stop=False,
        )

    def _opp() -> Opportunity:
        return Opportunity(
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
                overall=72.0,
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
    cand = OptionCandidate(
        contract=contract,
        scores=score_contract(contract, limits=_limits()),
        equity_opportunity=_opp(),
        strategy="long_call",
        max_loss_usd=120.0,
    )
    report = OptionsAnalysisReport(
        as_of=AS_OF,
        equity_candidates_considered=1,
        contracts_evaluated=1,
        candidates=(cand,),
        rejected_counts={},
        notes=("test",),
    )
    engine = DecisionPackageEngine(
        options_engine=OptionsAnalysisEngine(MockMarketDataProvider(), risk=_limits(), universe=["AAPL"]),
        catalyst_provider=MockCatalystProvider(
            {"AAPL": CatalystFixture(earnings_date=date(2026, 10, 6), earnings_status="upcoming")}
        ),
        fundamentals_provider=MockFundamentalsProvider(
            {
                "AAPL": FundamentalsFixture(
                    latest_actual_eps=None,
                    latest_estimate_eps=None,
                    beat_miss="unknown",
                    statements_status="present",
                    latest_indicators={"roe": 0.2, "net_margin": 0.1},
                    income=StatementPeriod(
                        kind="income",
                        fiscal_year=2025,
                        fiscal_period=4,
                        end_date="2025-09-27",
                        publish_date=None,
                        currency="USD",
                        fields={"total_revenue": 1.0, "net_income": 0.2},
                    ),
                    notes=("Fixture statements only.",),
                )
            }
        ),
        critic=CompositeAdversarialCritic(RuleBasedAdversarialCritic(), NullLLMCritic()),
        risk=_limits(),
    )
    pkg = engine.build(options_report=report, as_of=AS_OF).packages[0]
    assert pkg.incomplete_research is False
    assert "fundamentals" not in pkg.missing_required
    assert pkg.go_signal is False
    assert pkg.fundamentals.statements_status == "present"
