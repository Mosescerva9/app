"""Rule-based market regime classifier.

Deterministic and auditable. LLM layers may explain this output later,
but must not override the classification without a measured rule change.
"""

from __future__ import annotations

from trading_system.regime.playbook import playbook_for
from trading_system.regime.types import MarketRegime, RegimeFeatures, RegimeReport


def classify_regime(features: RegimeFeatures, *, benchmark: str) -> RegimeReport:
    f = features
    evidence: list[str] = []
    notes: list[str] = []

    bullish = f.last_close > f.sma_slow and f.sma_fast > f.sma_slow and f.sma_fast_slope > 0
    bearish = f.last_close < f.sma_slow and f.sma_fast < f.sma_slow and f.sma_fast_slope < 0
    high_vol = f.realized_vol_20 >= 0.28 or (f.vix_level is not None and f.vix_level >= 25)
    low_vol = f.realized_vol_20 <= 0.14 and (f.vix_level is None or f.vix_level <= 16)

    # Directional trend can exist even if the choppiness proxy is noisy.
    directional = (
        f.momentum_persistence >= 0.58
        and abs(f.sma_fast_slope) >= 0.002
        and f.trend_strength >= 0.35
    )
    strong_directional = (
        directional
        and f.trend_strength >= 0.55
        and f.momentum_persistence >= 0.62
        and abs(f.sma_fast_slope) >= 0.004
    )
    choppy = f.choppiness >= 0.62 and not directional
    mean_rev = (
        not directional
        and f.choppiness >= 0.5
        and f.trend_strength < 0.4
        and abs(f.sma_fast_slope) < 0.01
        and f.momentum_persistence < 0.55
    )
    eventish = f.gap_frequency >= 0.25 or f.volume_z >= 2.5 or (
        f.vix_change_5d is not None and abs(f.vix_change_5d) >= 4.0
    )

    evidence.append(
        f"close={'above' if f.last_close > f.sma_slow else 'below'} SMA{f.raw.get('slow', 50)}"
    )
    evidence.append(f"SMA fast slope={f.sma_fast_slope:.4f}")
    evidence.append(f"trend_strength={f.trend_strength:.2f}")
    evidence.append(f"realized_vol_20={f.realized_vol_20:.2%}")
    evidence.append(f"choppiness={f.choppiness:.2f}")
    evidence.append(f"momentum_persistence={f.momentum_persistence:.2f}")
    evidence.append(f"atr_pct={f.atr_pct:.2%}")
    evidence.append(f"volume_z={f.volume_z:.2f}")
    evidence.append(f"gap_frequency={f.gap_frequency:.2f}")
    if f.vix_level is not None:
        evidence.append(f"vix_level={f.vix_level:.2f}")
    else:
        notes.append("VIX unavailable — vol regime inferred from realized volatility only")

    # Priority: event overlay → strong directional → vol-trend → weak directional → chop/mean-rev.
    if eventish and high_vol:
        regime = MarketRegime.EVENT_DRIVEN
        confidence = 0.55 + min(0.3, f.gap_frequency + max(0.0, f.volume_z) / 10.0)
    elif bullish and strong_directional:
        regime = MarketRegime.HIGH_VOL_TREND if high_vol else MarketRegime.STRONG_BULL
        if low_vol and not high_vol:
            regime = MarketRegime.LOW_VOL_TREND
        confidence = 0.65 + 0.25 * f.trend_strength
    elif bearish and strong_directional:
        regime = MarketRegime.HIGH_VOL_TREND if high_vol else MarketRegime.STRONG_BEAR
        confidence = 0.65 + 0.25 * f.trend_strength
    elif high_vol and directional:
        regime = MarketRegime.HIGH_VOL_TREND
        confidence = 0.6 + 0.2 * f.trend_strength
    elif bullish and directional:
        regime = MarketRegime.LOW_VOL_TREND if low_vol else MarketRegime.WEAK_BULL
        confidence = 0.55 + 0.2 * f.trend_strength
    elif bearish and directional:
        regime = MarketRegime.WEAK_BEAR
        confidence = 0.55 + 0.2 * f.trend_strength
    elif bullish:
        regime = MarketRegime.WEAK_BULL
        confidence = 0.45 + 0.15 * f.trend_strength
    elif bearish:
        regime = MarketRegime.WEAK_BEAR
        confidence = 0.45 + 0.15 * f.trend_strength
    elif choppy:
        regime = MarketRegime.CHOPPY
        confidence = 0.55 + 0.25 * f.choppiness
    elif mean_rev:
        regime = MarketRegime.MEAN_REVERTING
        confidence = 0.5 + 0.2 * (1.0 - f.trend_strength)
    elif low_vol and directional:
        regime = MarketRegime.LOW_VOL_TREND
        confidence = 0.55 + 0.2 * f.trend_strength
    else:
        regime = MarketRegime.UNKNOWN
        confidence = 0.35
        notes.append("Signals mixed — classifier abstained to UNKNOWN")

    confidence = float(max(0.0, min(0.95, confidence)))
    book = playbook_for(regime)

    risks = list(book["risks"])
    if high_vol:
        risks.append("elevated realized volatility — reduce size / prefer defined risk")
    if f.volume_z >= 2.0:
        risks.append("abnormal volume — crowding / event risk")

    return RegimeReport(
        regime=regime,
        confidence=confidence,
        benchmark=benchmark.upper(),
        features=features,
        evidence=evidence,
        strategies_favored=list(book["favored"]),
        strategies_avoided=list(book["avoided"]),
        risks=risks,
        notes=notes,
    )
