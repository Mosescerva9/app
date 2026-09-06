"""Regime-filtered equity signal. Uses only bars through the signal close."""

from __future__ import annotations

from statistics import mean

from trading_system.models import Bar
from trading_system.regime.classifier import classify_regime
from trading_system.regime.features import compute_features
from trading_system.regime.types import MarketRegime

BULLISH = {
    MarketRegime.STRONG_BULL,
    MarketRegime.WEAK_BULL,
    MarketRegime.LOW_VOL_TREND,
}
BEARISH = {MarketRegime.STRONG_BEAR, MarketRegime.WEAK_BEAR}
MIN_BARS = 50


def _sma(closes: list[float], window: int) -> float:
    if len(closes) < window:
        window = max(1, len(closes))
    return mean(closes[-window:])


def detect_signal(bars: list[Bar]) -> str | None:
    """Return LONG, SHORT, or None from bars ending at the latest close.

    No future bars may be passed. Callers must slice ``bars[:signal_index+1]``.
    """
    if len(bars) < MIN_BARS:
        return None
    try:
        features = compute_features(bars, symbol=bars[-1].symbol)
        report = classify_regime(features, benchmark=bars[-1].symbol)
    except ValueError:
        return None
    closes = [b.close for b in bars]
    sma20 = _sma(closes, 20)
    sma50 = _sma(closes, 50)
    last = closes[-1]
    regime = report.regime

    if regime in {MarketRegime.CHOPPY, MarketRegime.EVENT_DRIVEN, MarketRegime.UNKNOWN}:
        return None
    if regime in BULLISH and last > sma20 and sma20 > sma50:
        return "LONG"
    if regime in BEARISH and last < sma20 and sma20 < sma50:
        return "SHORT"
    if regime is MarketRegime.HIGH_VOL_TREND:
        if last > sma20:
            return "LONG"
        if last < sma20:
            return "SHORT"
    if regime is MarketRegime.MEAN_REVERTING:
        return None
    return None
