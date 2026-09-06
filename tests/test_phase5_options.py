"""Phase 5 options analysis engine tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from trading_system.data.mock import MockMarketDataProvider
from trading_system.modes import PHASE, LIVE_EXECUTION_UNLOCKED
from trading_system.options.chain import MockOptionChainProvider, OptionChainProvider
from trading_system.options.engine import OptionsAnalysisEngine
from trading_system.options.filters import OptionFilterConfig, filter_contract
from trading_system.options.scoring import OPTION_SCORE_WEIGHTS, score_contract
from trading_system.options.types import OptionContract, occ_symbol
from trading_system.risk.limits import RiskLimits
from trading_system.scanner.types import (
    Direction,
    Opportunity,
    ScoreBreakdown,
    SetupType,
)


def _limits(equity: float = 1000.0, pct: float = 0.04) -> RiskLimits:
    return RiskLimits(
        account_equity_usd=equity,
        max_risk_per_trade_pct=pct,
        max_simultaneous_positions=2,
        max_daily_loss_pct=0.06,
        max_weekly_loss_pct=0.12,
        emergency_stop=False,
    )


def _research_book() -> RiskLimits:
    """Operator RESEARCH book: $1,500 equity / 10% → $150 per trade."""
    return _limits(equity=1500.0, pct=0.10)


def _large_book() -> RiskLimits:
    """Book large enough that the mid-delta window stays strict."""
    return _limits(equity=25_000.0, pct=0.02)  # $500


def _contract(
    *,
    right: str = "CALL",
    dte: int = 45,
    delta: float = 0.35,
    mid: float = 0.35,
    oi: int = 2000,
    spread_pct: float = 0.05,
    iv: float = 0.28,
    underlying: str = "TEST",
    strike: float = 100.0,
) -> OptionContract:
    as_of = datetime(2026, 9, 5, tzinfo=timezone.utc)
    expiration = (as_of + timedelta(days=dte)).date()
    half = mid * spread_pct / 2
    return OptionContract(
        underlying=underlying,
        right=right,
        expiration=expiration,
        strike=strike,
        bid=round(mid - half, 2),
        ask=round(mid + half, 2),
        last=mid,
        mid=mid,
        volume=500,
        open_interest=oi,
        implied_volatility=iv,
        delta=delta if right == "CALL" else -abs(delta),
        gamma=0.01,
        theta=-0.02,
        vega=0.05,
        as_of=as_of,
        symbol=occ_symbol(underlying, expiration, right, strike),
    )


class _StaticChain(OptionChainProvider):
    def __init__(self, contracts: list[OptionContract]) -> None:
        self._contracts = contracts

    def get_chain(self, underlying: str, **kwargs):
        return list(self._contracts)


def _long_opportunity(symbol: str = "NVDA", entry: float = 180.0) -> Opportunity:
    return Opportunity(
        symbol=symbol,
        direction=Direction.LONG,
        setup=SetupType.PULLBACK_IN_TREND,
        scores=ScoreBreakdown(
            technical=70,
            momentum=65,
            liquidity=80,
            regime_fit=75,
            risk_reward=70,
            crowding_risk=20,
            overall=72,
        ),
        entry=entry,
        stop=entry * 0.96,
        target=entry * 1.08,
        risk_reward=2.0,
        regime="weak_bull",
        regime_confidence=0.6,
        why=["test"],
        do_not_trade_if=[],
        invalidation=[],
        decision="CANDIDATE",
    )


def test_phase_is_five():
    assert PHASE == 10
    assert LIVE_EXECUTION_UNLOCKED is False


def test_option_score_weights_sum_to_one():
    assert abs(sum(OPTION_SCORE_WEIGHTS.values()) - 1.0) < 1e-9


def test_filter_rejects_wrong_right_and_over_budget():
    limits = _limits()
    call = _contract(right="CALL", mid=0.35)
    put = _contract(right="PUT", mid=0.35, delta=0.35)
    expensive = _contract(right="CALL", mid=1.50)  # $150 premium

    assert filter_contract(call, side_bias="LONG", limits=limits).ok
    assert not filter_contract(call, side_bias="SHORT", limits=limits).ok
    assert filter_contract(put, side_bias="SHORT", limits=limits).ok
    assert not filter_contract(expensive, side_bias="LONG", limits=limits).ok


def test_filter_enforces_dte_and_delta_window():
    # Larger books keep the original mid-delta / 30–60 DTE window.
    limits = _large_book()
    short_dte = _contract(dte=14)
    long_dte = _contract(dte=90)
    low_delta = _contract(delta=0.10)
    high_delta = _contract(delta=0.70)

    assert filter_contract(short_dte, side_bias="LONG", limits=limits).reason == "dte_too_short"
    assert filter_contract(long_dte, side_bias="LONG", limits=limits).reason == "dte_too_long"
    assert filter_contract(low_delta, side_bias="LONG", limits=limits).reason == "delta_too_low"
    assert filter_contract(high_delta, side_bias="LONG", limits=limits).reason == "delta_too_high"


def test_small_book_allows_low_delta_that_fits_budget():
    limits = _research_book()
    cheap_otm = _contract(delta=0.12, mid=0.90, dte=21)  # $90 debit
    too_cheap_delta = _contract(delta=0.04, mid=0.40, dte=21)
    mid_delta = _contract(delta=0.32, mid=1.20, dte=45)  # $120 debit
    expensive = _contract(delta=0.12, mid=2.50, dte=21)  # $250 > $150

    assert filter_contract(cheap_otm, side_bias="LONG", limits=limits).ok
    assert filter_contract(mid_delta, side_bias="LONG", limits=limits).ok
    assert filter_contract(too_cheap_delta, side_bias="LONG", limits=limits).reason == "delta_too_low"
    assert (
        filter_contract(expensive, side_bias="LONG", limits=limits).reason
        == "premium_exceeds_risk_budget"
    )
    # Explicit opt-out still enforces the mid-delta floor (DTE already in window).
    strict = OptionFilterConfig(auto_relax_when_budget_binds=False)
    cheap_otm_45 = _contract(delta=0.12, mid=0.90, dte=45)
    assert filter_contract(cheap_otm_45, side_bias="LONG", limits=limits, config=strict).reason == (
        "delta_too_low"
    )


def test_score_contract_prefers_liquid_mid_delta():
    limits = _limits()
    good = score_contract(_contract(delta=0.35, mid=0.32, oi=5000, spread_pct=0.03), limits=limits)
    thin = score_contract(_contract(delta=0.35, mid=0.32, oi=250, spread_pct=0.11), limits=limits)
    assert good.overall > thin.overall
    assert good.liquidity > thin.liquidity


def test_mock_chain_has_dte_and_rights():
    chain = MockOptionChainProvider().get_chain("AAPL", spot=100.0)
    assert len(chain) > 50
    dtes = {c.dte for c in chain}
    rights = {c.right for c in chain}
    assert 35 in dtes or 45 in dtes
    assert rights == {"CALL", "PUT"}
    # At least some mid-delta contracts should fit the $150 research budget
    affordable = [c for c in chain if c.premium_per_contract_usd <= 150 and 30 <= c.dte <= 60]
    assert len(affordable) > 0


def test_engine_returns_long_calls_for_long_bias():
    # Force a known equity opportunity so we don't depend on mock scanner luck.
    opp = Opportunity(
        symbol="AAPL",
        direction=Direction.LONG,
        setup=SetupType.PULLBACK_IN_TREND,
        scores=ScoreBreakdown(
            technical=70,
            momentum=65,
            liquidity=80,
            regime_fit=75,
            risk_reward=70,
            crowding_risk=20,
            overall=72,
        ),
        entry=100.0,
        stop=96.0,
        target=108.0,
        risk_reward=2.0,
        regime="weak_bull",
        regime_confidence=0.6,
        why=["test"],
        do_not_trade_if=[],
        invalidation=[],
        decision="CANDIDATE",
    )
    from trading_system.scanner.types import ScanReport

    scan = ScanReport(
        benchmark="SPY",
        regime="weak_bull",
        regime_confidence=0.6,
        universe_size=1,
        opportunities=[opp],
    )
    engine = OptionsAnalysisEngine(
        MockMarketDataProvider(),
        risk=_limits(),
        min_option_score=40.0,
        max_results=5,
    )
    report = engine.analyze(scan_report=scan)
    payload = report.to_dict()
    assert payload["equity_candidates_considered"] == 1
    assert payload["contracts_evaluated"] > 0
    assert LIVE_EXECUTION_UNLOCKED is False
    for cand in payload["candidates"]:
        assert cand["strategy"] == "long_call"
        assert cand["contract"]["right"] == "CALL"
        assert 14 <= cand["contract"]["dte"] <= 60
        assert cand["max_loss_usd"] <= _limits().max_risk_per_trade_usd
        assert cand["scores"]["overall"] >= 40.0


def test_engine_end_to_end_via_scanner():
    engine = OptionsAnalysisEngine(
        MockMarketDataProvider(),
        risk=_limits(),
        universe=["SPY", "QQQ", "AAPL", "MSFT"],
        min_equity_score=40.0,
        min_option_score=40.0,
        max_results=5,
    )
    report = engine.analyze()
    payload = report.to_dict()
    assert "candidates" in payload
    assert "rejected_counts" in payload
    assert "notes" in payload
    for cand in payload["candidates"]:
        assert cand["contract"]["right"] in {"CALL", "PUT"}
        assert cand["strategy"] in {"long_call", "long_put"}


def test_engine_low_delta_only_chain_yields_candidate():
    """When only |delta|~0.12 fits the $150 book, still return ≥1 long call."""
    from trading_system.scanner.types import ScanReport

    expensive_mid = _contract(
        underlying="NVDA",
        right="CALL",
        delta=0.35,
        mid=4.50,  # $450 — typical NVDA mid-delta
        dte=45,
        strike=180.0,
        oi=4000,
        spread_pct=0.04,
    )
    cheap_otm = _contract(
        underlying="NVDA",
        right="CALL",
        delta=0.12,
        mid=0.85,  # $85
        dte=21,
        strike=210.0,
        oi=2500,
        spread_pct=0.06,
    )
    # Wrong right must stay rejected even on the small book.
    cheap_put = _contract(
        underlying="NVDA",
        right="PUT",
        delta=0.12,
        mid=0.80,
        dte=21,
        strike=160.0,
        oi=2500,
        spread_pct=0.06,
    )
    scan = ScanReport(
        benchmark="SPY",
        regime="weak_bull",
        regime_confidence=0.6,
        universe_size=1,
        opportunities=[_long_opportunity("NVDA", entry=180.0)],
    )
    engine = OptionsAnalysisEngine(
        MockMarketDataProvider(),
        chain_provider=_StaticChain([expensive_mid, cheap_otm, cheap_put]),
        risk=_research_book(),
        min_option_score=55.0,
        max_results=5,
    )
    report = engine.analyze(scan_report=scan)
    assert LIVE_EXECUTION_UNLOCKED is False
    assert len(report.candidates) >= 1
    best = report.candidates[0]
    assert best.strategy == "long_call"
    assert best.contract.right == "CALL"
    assert best.contract.delta == 0.12
    assert best.max_loss_usd <= _research_book().max_risk_per_trade_usd
    assert best.max_loss_usd == cheap_otm.premium_per_contract_usd


def test_engine_prefers_mid_delta_when_it_fits_budget():
    """Mid-delta that fits $150 must outrank a cheaper deep-OTM contract."""
    from trading_system.scanner.types import ScanReport

    mid_delta = _contract(
        underlying="AAPL",
        right="CALL",
        delta=0.33,
        mid=1.20,  # $120
        dte=45,
        strike=100.0,
        oi=5000,
        spread_pct=0.03,
    )
    cheap_otm = _contract(
        underlying="AAPL",
        right="CALL",
        delta=0.10,
        mid=0.40,  # $40
        dte=21,
        strike=115.0,
        oi=2500,
        spread_pct=0.06,
    )
    scan = ScanReport(
        benchmark="SPY",
        regime="weak_bull",
        regime_confidence=0.6,
        universe_size=1,
        opportunities=[_long_opportunity("AAPL", entry=100.0)],
    )
    engine = OptionsAnalysisEngine(
        MockMarketDataProvider(),
        chain_provider=_StaticChain([cheap_otm, mid_delta]),
        risk=_research_book(),
        min_option_score=40.0,
        max_results=5,
        max_contracts_per_symbol=2,
    )
    report = engine.analyze(scan_report=scan)
    assert len(report.candidates) >= 1
    best = report.candidates[0]
    assert best.contract.delta == 0.33
    assert best.max_loss_usd <= 150.0
    deltas = [c.contract.delta for c in report.candidates]
    if len(deltas) > 1:
        assert deltas[0] > deltas[1]


def test_engine_relaxes_when_larger_book_mid_delta_still_blows_budget():
    """When budget binds even above $150, retry the low-delta band instead of 0."""
    from trading_system.scanner.types import ScanReport

    expensive_mid = _contract(
        underlying="TSLA",
        right="CALL",
        delta=0.38,
        mid=7.00,  # $700
        dte=45,
        strike=250.0,
        oi=4000,
        spread_pct=0.04,
    )
    cheap_otm = _contract(
        underlying="TSLA",
        right="CALL",
        delta=0.11,
        mid=0.95,
        dte=21,
        strike=300.0,
        oi=2200,
        spread_pct=0.05,
    )
    scan = ScanReport(
        benchmark="SPY",
        regime="weak_bull",
        regime_confidence=0.6,
        universe_size=1,
        opportunities=[_long_opportunity("TSLA", entry=250.0)],
    )
    engine = OptionsAnalysisEngine(
        MockMarketDataProvider(),
        chain_provider=_StaticChain([expensive_mid, cheap_otm]),
        risk=_large_book(),
        min_option_score=40.0,
        max_results=5,
    )
    report = engine.analyze(scan_report=scan)
    assert len(report.candidates) >= 1
    assert report.candidates[0].contract.delta == 0.11
    assert any("retrying |delta|" in n for n in report.notes)
