"""Market regime types and report schema."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MarketRegime(str, Enum):
    STRONG_BULL = "STRONG_BULL"
    WEAK_BULL = "WEAK_BULL"
    STRONG_BEAR = "STRONG_BEAR"
    WEAK_BEAR = "WEAK_BEAR"
    HIGH_VOL_TREND = "HIGH_VOL_TREND"
    LOW_VOL_TREND = "LOW_VOL_TREND"
    MEAN_REVERTING = "MEAN_REVERTING"
    CHOPPY = "CHOPPY"
    EVENT_DRIVEN = "EVENT_DRIVEN"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RegimeFeatures:
    symbol: str
    lookback: int
    last_close: float
    sma_fast: float
    sma_slow: float
    sma_fast_slope: float
    trend_strength: float  # 0-1
    atr_pct: float
    realized_vol_20: float
    volume_z: float
    choppiness: float  # higher = more choppy
    momentum_persistence: float  # share of days closing in trend direction
    gap_frequency: float
    vix_level: float | None = None
    vix_change_5d: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RegimeReport:
    regime: MarketRegime
    confidence: float  # 0-1
    benchmark: str
    features: RegimeFeatures
    evidence: list[str]
    strategies_favored: list[str]
    strategies_avoided: list[str]
    risks: list[str]
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "regime": self.regime.value,
            "confidence": round(self.confidence, 3),
            "benchmark": self.benchmark,
            "features": {
                "symbol": self.features.symbol,
                "lookback": self.features.lookback,
                "last_close": self.features.last_close,
                "sma_fast": round(self.features.sma_fast, 4),
                "sma_slow": round(self.features.sma_slow, 4),
                "sma_fast_slope": round(self.features.sma_fast_slope, 6),
                "trend_strength": round(self.features.trend_strength, 3),
                "atr_pct": round(self.features.atr_pct, 4),
                "realized_vol_20": round(self.features.realized_vol_20, 4),
                "volume_z": round(self.features.volume_z, 3),
                "choppiness": round(self.features.choppiness, 3),
                "momentum_persistence": round(self.features.momentum_persistence, 3),
                "gap_frequency": round(self.features.gap_frequency, 3),
                "vix_level": self.features.vix_level,
                "vix_change_5d": self.features.vix_change_5d,
            },
            "evidence": self.evidence,
            "strategies_favored": self.strategies_favored,
            "strategies_avoided": self.strategies_avoided,
            "risks": self.risks,
            "notes": self.notes,
        }
