"""Weighted scoring and setup selection."""

from __future__ import annotations

from trading_system.regime.types import MarketRegime
from trading_system.scanner.features import SymbolFeatures
from trading_system.scanner.types import BASE_WEIGHTS, Direction, ScoreBreakdown, SetupType


def score_liquidity(features: SymbolFeatures) -> float:
    score = 70.0
    if features.volume_z > 3.0:
        score -= 15
    elif features.volume_z > 1.5:
        score -= 5
    elif features.volume_z < -1.5:
        score -= 10
    if features.atr_pct > 0.05:
        score -= 20
    elif features.atr_pct > 0.03:
        score -= 10
    elif 0.008 <= features.atr_pct <= 0.025:
        score += 10
    return max(0.0, min(100.0, score))


def score_crowding_risk(features: SymbolFeatures) -> float:
    risk = 30.0
    if features.volume_z >= 2.5:
        risk += 25
    elif features.volume_z >= 1.5:
        risk += 12
    ext = (features.last / features.sma_20 - 1.0) if features.sma_20 else 0.0
    if ext > 0.08:
        risk += 25
    elif ext > 0.04:
        risk += 12
    if abs(features.ret_5d) > 0.08:
        risk += 15
    return max(0.0, min(100.0, risk))


def score_regime_fit(
    features: SymbolFeatures,
    regime: MarketRegime,
    *,
    direction: Direction,
) -> float:
    longish = direction is Direction.LONG
    shortish = direction is Direction.SHORT

    if regime in {MarketRegime.STRONG_BULL, MarketRegime.LOW_VOL_TREND, MarketRegime.WEAK_BULL}:
        if longish and features.above_sma_50:
            return 85.0 if regime is MarketRegime.STRONG_BULL else 72.0
        if shortish:
            return 25.0
        return 45.0

    if regime in {MarketRegime.STRONG_BEAR, MarketRegime.WEAK_BEAR}:
        if shortish and not features.above_sma_50:
            return 85.0 if regime is MarketRegime.STRONG_BEAR else 70.0
        if longish:
            return 25.0
        return 45.0

    if regime is MarketRegime.HIGH_VOL_TREND:
        aligned = (longish and features.above_sma_20) or (shortish and not features.above_sma_20)
        return 60.0 if aligned else 40.0

    if regime in {MarketRegime.MEAN_REVERTING, MarketRegime.CHOPPY}:
        if features.pullback_from_high_pct >= 0.04 or features.distance_from_20d_low_pct <= 0.03:
            return 70.0
        return 40.0

    if regime is MarketRegime.EVENT_DRIVEN:
        return 35.0

    return 40.0


def score_risk_reward(entry: float, stop: float, target: float) -> float:
    risk = abs(entry - stop)
    reward = abs(target - entry)
    if risk <= 1e-9:
        return 0.0
    rr = reward / risk
    if rr >= 3:
        return 95.0
    if rr >= 2:
        return 80.0
    if rr >= 1.5:
        return 68.0
    if rr >= 1.0:
        return 55.0
    if rr >= 0.75:
        return 40.0
    return 20.0


def choose_setup_and_levels(
    features: SymbolFeatures,
    regime: MarketRegime,
) -> tuple[SetupType, Direction, float, float, float]:
    entry = features.last
    atr = max(features.last * features.atr_pct, features.last * 0.005)

    bull_regime = regime in {
        MarketRegime.STRONG_BULL,
        MarketRegime.WEAK_BULL,
        MarketRegime.LOW_VOL_TREND,
        MarketRegime.HIGH_VOL_TREND,
    }
    bear_regime = regime in {MarketRegime.STRONG_BEAR, MarketRegime.WEAK_BEAR}

    if features.distance_from_20d_high_pct >= -0.01 and features.above_sma_20 and bull_regime:
        return (
            SetupType.BREAKOUT_CONTINUATION,
            Direction.LONG,
            entry,
            entry - 1.5 * atr,
            entry + 2.5 * atr,
        )

    if (
        features.above_sma_50
        and features.pullback_from_high_pct >= 0.02
        and abs(features.last / features.sma_20 - 1.0) <= 0.02
        and bull_regime
    ):
        return (
            SetupType.PULLBACK_IN_TREND,
            Direction.LONG,
            entry,
            min(features.sma_20, entry) - 1.2 * atr,
            entry + 2.2 * atr,
        )

    if features.momentum_score >= 65 and features.above_sma_20 and bull_regime:
        return (
            SetupType.MOMENTUM_CONTINUATION,
            Direction.LONG,
            entry,
            entry - 1.8 * atr,
            entry + 2.4 * atr,
        )

    if bear_regime and not features.above_sma_50 and features.ret_5d > 0.01:
        return (
            SetupType.MEAN_REVERSION,
            Direction.SHORT,
            entry,
            entry + 1.5 * atr,
            entry - 2.2 * atr,
        )

    if regime in {MarketRegime.MEAN_REVERTING, MarketRegime.CHOPPY}:
        if features.distance_from_20d_low_pct <= 0.02:
            return (
                SetupType.MEAN_REVERSION,
                Direction.LONG,
                entry,
                entry - 1.2 * atr,
                max(features.sma_20, entry + atr),
            )
        if features.pullback_from_high_pct >= 0.05:
            return (
                SetupType.MEAN_REVERSION,
                Direction.SHORT,
                entry,
                entry + 1.2 * atr,
                min(features.sma_20, entry - atr),
            )

    if features.above_sma_20 and features.above_sma_50 and features.ret_20d > 0:
        return (
            SetupType.RELATIVE_STRENGTH,
            Direction.LONG,
            entry,
            entry - 1.5 * atr,
            entry + 2.0 * atr,
        )

    return SetupType.STAND_ASIDE, Direction.NONE, entry, entry - atr, entry + atr


def combine_scores(
    *,
    technical: float | None,
    momentum: float | None,
    liquidity: float | None,
    regime_fit: float | None,
    risk_reward: float | None,
    crowding_risk: float | None,
    options_quality: float | None = None,
    catalyst: float | None = None,
    fundamental: float | None = None,
) -> ScoreBreakdown:
    values: dict[str, float] = {}
    if regime_fit is not None:
        values["regime_fit"] = regime_fit
    if liquidity is not None:
        values["liquidity"] = liquidity
    if risk_reward is not None:
        values["risk_reward"] = risk_reward
    if momentum is not None:
        values["momentum"] = momentum
    if technical is not None:
        values["technical"] = technical
    if crowding_risk is not None:
        values["crowding"] = max(0.0, 100.0 - crowding_risk)

    missing = tuple(
        name
        for name, val in {
            "options_quality": options_quality,
            "catalyst": catalyst,
            "fundamental": fundamental,
        }.items()
        if val is None
    )

    active = {k: BASE_WEIGHTS[k] for k in values if k in BASE_WEIGHTS}
    total_w = sum(active.values()) or 1.0
    weights_used = {k: w / total_w for k, w in active.items()}
    overall = sum(values[k] * weights_used[k] for k in weights_used)

    return ScoreBreakdown(
        technical=technical,
        momentum=momentum,
        liquidity=liquidity,
        regime_fit=regime_fit,
        risk_reward=risk_reward,
        crowding_risk=crowding_risk,
        options_quality=options_quality,
        catalyst=catalyst,
        fundamental=fundamental,
        overall=overall,
        weights_used=weights_used,
        missing_dimensions=missing,
    )
