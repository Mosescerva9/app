"""Phase 3 market regime engine tests (synthetic bars; no live Webull)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from trading_system.models import Bar, utc_now
from trading_system.regime.classifier import classify_regime
from trading_system.regime.engine import MarketRegimeEngine
from trading_system.regime.features import compute_features
from trading_system.regime.types import MarketRegime
from trading_system.data.mock import MockMarketDataProvider
from trading_system.modes import PHASE


def _bars_from_closes(closes: list[float], symbol: str = "SPY") -> list[Bar]:
    now = utc_now()
    bars: list[Bar] = []
    for i, close in enumerate(closes):
        open_px = closes[i - 1] if i else close
        # Tight intraday range so ATR/choppiness does not drown directional signal.
        high = max(open_px, close) * 1.0015
        low = min(open_px, close) * 0.9985
        bars.append(
            Bar(
                symbol=symbol,
                timestamp=now - timedelta(days=len(closes) - i),
                open=open_px,
                high=high,
                low=low,
                close=close,
                volume=1_000_000 + (i % 5) * 50_000,
                timespan="D",
            )
        )
    return bars


def test_phase_is_three():
    assert PHASE == 5


def test_strong_bull_classification():
    # Smooth grind higher for 90 sessions.
    closes = [100 * (1.004 ** i) for i in range(90)]
    features = compute_features(_bars_from_closes(closes), symbol="SPY")
    report = classify_regime(features, benchmark="SPY")
    assert report.regime in {MarketRegime.STRONG_BULL, MarketRegime.WEAK_BULL, MarketRegime.LOW_VOL_TREND}
    assert report.confidence >= 0.45
    assert report.strategies_favored
    assert report.strategies_avoided


def test_strong_bear_classification():
    closes = [100 * (0.996 ** i) for i in range(90)]
    features = compute_features(_bars_from_closes(closes), symbol="SPY")
    report = classify_regime(features, benchmark="SPY")
    assert report.regime in {MarketRegime.STRONG_BEAR, MarketRegime.WEAK_BEAR, MarketRegime.HIGH_VOL_TREND}
    assert report.confidence >= 0.4


def test_choppy_classification():
    # Alternating up/down days around a flat mean.
    closes = []
    px = 100.0
    for i in range(90):
        px *= 1.012 if i % 2 == 0 else 0.988
        closes.append(px)
    features = compute_features(_bars_from_closes(closes), symbol="SPY")
    report = classify_regime(features, benchmark="SPY")
    assert report.regime in {
        MarketRegime.CHOPPY,
        MarketRegime.MEAN_REVERTING,
        MarketRegime.UNKNOWN,
        MarketRegime.WEAK_BULL,
        MarketRegime.WEAK_BEAR,
    }


def test_engine_with_mock_provider():
    engine = MarketRegimeEngine(MockMarketDataProvider(), benchmark="SPY", lookback=90)
    report = engine.analyze()
    assert isinstance(report.regime, MarketRegime)
    payload = report.to_dict()
    assert "regime" in payload
    assert "evidence" in payload
    assert "strategies_favored" in payload
    assert payload["confidence"] <= 0.95


def test_insufficient_bars_raises():
    with pytest.raises(ValueError):
        compute_features(_bars_from_closes([100.0, 101.0]), symbol="SPY")
