"""Opportunity scanner types and weighted score schema."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SetupType(str, Enum):
    BREAKOUT_CONTINUATION = "breakout_continuation"
    PULLBACK_IN_TREND = "pullback_in_trend"
    MOMENTUM_CONTINUATION = "momentum_continuation"
    RELATIVE_STRENGTH = "relative_strength"
    MEAN_REVERSION = "mean_reversion"
    STAND_ASIDE = "stand_aside"


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NONE = "NONE"


BASE_WEIGHTS: dict[str, float] = {
    "regime_fit": 0.22,
    "liquidity": 0.18,
    "risk_reward": 0.18,
    "momentum": 0.14,
    "technical": 0.12,
    "crowding": 0.10,
}


@dataclass(frozen=True)
class ScoreBreakdown:
    technical: float | None
    momentum: float | None
    liquidity: float | None
    regime_fit: float | None
    risk_reward: float | None
    crowding_risk: float | None
    options_quality: float | None = None
    catalyst: float | None = None
    fundamental: float | None = None
    overall: float = 0.0
    weights_used: dict[str, float] = field(default_factory=dict)
    missing_dimensions: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "technical": _r(self.technical),
            "momentum": _r(self.momentum),
            "liquidity": _r(self.liquidity),
            "regime_fit": _r(self.regime_fit),
            "risk_reward": _r(self.risk_reward),
            "crowding_risk": _r(self.crowding_risk),
            "options_quality": _r(self.options_quality),
            "catalyst": _r(self.catalyst),
            "fundamental": _r(self.fundamental),
            "overall": round(self.overall, 2),
            "weights_used": {k: round(v, 4) for k, v in self.weights_used.items()},
            "missing_dimensions": list(self.missing_dimensions),
        }


@dataclass(frozen=True)
class Opportunity:
    symbol: str
    direction: Direction
    setup: SetupType
    scores: ScoreBreakdown
    entry: float | None
    stop: float | None
    target: float | None
    risk_reward: float | None
    regime: str
    regime_confidence: float
    why: list[str]
    do_not_trade_if: list[str]
    invalidation: list[str]
    decision: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "direction": self.direction.value,
            "setup": self.setup.value,
            "decision": self.decision,
            "scores": self.scores.to_dict(),
            "entry": self.entry,
            "stop": self.stop,
            "target": self.target,
            "risk_reward": round(self.risk_reward, 2) if self.risk_reward is not None else None,
            "regime": self.regime,
            "regime_confidence": round(self.regime_confidence, 3),
            "why": self.why,
            "do_not_trade_if": self.do_not_trade_if,
            "invalidation": self.invalidation,
        }


@dataclass(frozen=True)
class SymbolReject:
    """Why a universe symbol did not become a ranked opportunity."""

    symbol: str
    reason: str  # no_setup | regime_fit | score_floor | error
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"symbol": self.symbol, "reason": self.reason, "detail": self.detail}


@dataclass(frozen=True)
class ScanReport:
    benchmark: str
    regime: str
    regime_confidence: float
    universe_size: int
    opportunities: list[Opportunity]
    notes: list[str] = field(default_factory=list)
    rejects: list[SymbolReject] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        reject_counts: dict[str, int] = {}
        for row in self.rejects:
            reject_counts[row.reason] = reject_counts.get(row.reason, 0) + 1
        payload: dict[str, Any] = {
            "benchmark": self.benchmark,
            "regime": self.regime,
            "regime_confidence": round(self.regime_confidence, 3),
            "universe_size": self.universe_size,
            "opportunity_count": len(self.opportunities),
            "opportunities": [o.to_dict() for o in self.opportunities],
            "reject_count": len(self.rejects),
            "reject_counts": reject_counts,
            "rejects": [r.to_dict() for r in self.rejects],
            "notes": self.notes,
            "scoring_policy": {
                "method": "weighted_renormalized",
                "base_weights": BASE_WEIGHTS,
                "note": (
                    "Missing dimensions are excluded and remaining weights renormalize "
                    "to sum 1.0. Crowding contributes as (100 - crowding_risk)."
                ),
            },
        }
        if not self.opportunities:
            payload["empty_scan_diagnosis"] = _empty_scan_diagnosis(
                self.rejects, regime=self.regime
            )
        return payload


def _empty_scan_diagnosis(
    rejects: list[SymbolReject],
    *,
    regime: str,
) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for row in rejects:
        counts[row.reason] = counts.get(row.reason, 0) + 1
    top = [
        f"{r.symbol}: {r.reason} ({r.detail})"
        for r in rejects[:8]
    ]
    summary = (
        f"No opportunities passed filters under regime={regime}. "
        + (
            ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
            if counts
            else "universe produced no scored rows"
        )
        + "."
    )
    return {"summary": summary, "reject_counts": counts, "examples": top}


def _r(value: float | None) -> float | None:
    return None if value is None else round(value, 2)


DEFAULT_UNIVERSE: tuple[str, ...] = (
    "SPY",
    "QQQ",
    "IWM",
    "DIA",
    "XLK",
    "XLF",
    "XLE",
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "META",
    "GOOGL",
    "TSLA",
    "JPM",
)
