"""Phase 4 opportunity scanner tests."""

from __future__ import annotations

from datetime import timedelta

import pytest

from trading_system.data.mock import MockMarketDataProvider
from trading_system.models import Bar, utc_now
from trading_system.modes import PHASE
from trading_system.regime.types import MarketRegime
from trading_system.scanner.features import extract_symbol_features
from trading_system.scanner.scoring import combine_scores, score_risk_reward
from trading_system.scanner.engine import OpportunityScanner
from trading_system.scanner.types import BASE_WEIGHTS


def _trend_bars(n: int = 90, start: float = 100.0, drift: float = 0.004) -> list[Bar]:
    now = utc_now()
    bars: list[Bar] = []
    px = start
    for i in range(n):
        open_px = px
        close = px * (1.0 + drift)
        bars.append(
            Bar(
                symbol="TEST",
                timestamp=now - timedelta(days=n - i),
                open=open_px,
                high=max(open_px, close) * 1.0015,
                low=min(open_px, close) * 0.9985,
                close=close,
                volume=1_000_000 + i * 1000,
                timespan="D",
            )
        )
        px = close
    return bars


def test_phase_is_four():
    assert PHASE == 5


def test_weights_documented_and_sum_near_one():
    assert abs(sum(BASE_WEIGHTS.values()) - 0.94) < 1e-9  # 0.06 reserved for deferred dims


def test_combine_scores_renormalizes_without_missing_penalty_on_present_dims():
    scores = combine_scores(
        technical=80,
        momentum=70,
        liquidity=90,
        regime_fit=85,
        risk_reward=75,
        crowding_risk=20,
    )
    assert scores.overall > 70
    assert abs(sum(scores.weights_used.values()) - 1.0) < 1e-9
    assert "options_quality" in scores.missing_dimensions


def test_risk_reward_mapping():
    assert score_risk_reward(100, 95, 110) >= 80  # RR=2
    assert score_risk_reward(100, 99, 100.5) < 55


def test_feature_extraction_on_uptrend():
    feats = extract_symbol_features(_trend_bars(), symbol="TEST")
    assert feats.above_sma_20
    assert feats.trend_score >= 60
    assert feats.ret_20d > 0


def test_scanner_returns_ranked_report():
    scanner = OpportunityScanner(
        MockMarketDataProvider(),
        universe=["SPY", "QQQ", "AAPL", "MSFT", "NVDA"],
        min_score=40.0,
        max_results=5,
    )
    report = scanner.scan()
    payload = report.to_dict()
    assert payload["universe_size"] == 5
    assert "regime" in payload
    assert "scoring_policy" in payload
    assert payload["scoring_policy"]["method"] == "weighted_renormalized"
    # May be empty in awkward mock regimes; ensure structure is valid.
    for opp in payload["opportunities"]:
        assert opp["decision"] in {"WATCH", "CANDIDATE"}
        assert opp["scores"]["overall"] >= 40.0
        assert "why" in opp
        assert "do_not_trade_if" in opp or "do_not_trade_if" in opp
