"""Auditable Decision Package schema (Architecture Phase 8)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from trading_system.adversarial.types import AdversarialCritique
from trading_system.events.types import CatalystSnapshot
from trading_system.fundamentals.types import FundamentalsSnapshot
from trading_system.options.types import OptionCandidate
from trading_system.research_lock import research_lock_fields
from trading_system.scanner.types import Opportunity


@dataclass(frozen=True)
class DecisionScores:
    technical: float | None
    momentum: float | None
    liquidity: float | None
    regime_fit: float | None
    risk_reward: float | None
    crowding_risk: float | None
    options_quality: float | None
    catalyst: float | None
    fundamental: float | None
    overall: float
    confidence: float
    missing_dimensions: tuple[str, ...] = ()
    weights_used: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        def _r(value: float | None) -> float | None:
            return None if value is None else round(value, 2)

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
            "confidence": round(self.confidence, 2),
            "missing_dimensions": list(self.missing_dimensions),
            "weights_used": {k: round(v, 4) for k, v in self.weights_used.items()},
        }


@dataclass(frozen=True)
class DecisionPackage:
    as_of: datetime
    symbol: str
    recommendation: str  # candidate | watch | stand_aside | reject
    decision: str
    scores: DecisionScores
    equity_opportunity: Opportunity
    option_candidate: OptionCandidate | None
    catalyst: CatalystSnapshot
    fundamentals: FundamentalsSnapshot
    adversarial: AdversarialCritique
    risk: dict[str, Any]
    incomplete_research: bool = True
    missing_required: tuple[str, ...] = ()
    go_signal: bool = False
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_of": self.as_of.astimezone(timezone.utc).isoformat(),
            "symbol": self.symbol,
            "recommendation": self.recommendation,
            "decision": self.decision,
            "incomplete_research": self.incomplete_research,
            "missing_required": list(self.missing_required),
            "go_signal": False,
            "scores": self.scores.to_dict(),
            "equity_opportunity": self.equity_opportunity.to_dict(),
            "option_candidate": (
                self.option_candidate.to_dict() if self.option_candidate is not None else None
            ),
            "catalyst": self.catalyst.to_dict(),
            "fundamentals": self.fundamentals.to_dict(),
            "adversarial": self.adversarial.to_dict(),
            "risk": dict(self.risk),
            "notes": list(self.notes),
            "live_execution_unlocked": False,
        }


@dataclass(frozen=True)
class DecisionReport:
    as_of: datetime
    packages: tuple[DecisionPackage, ...]
    options_summary: dict[str, Any] = field(default_factory=dict)
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "as_of": self.as_of.astimezone(timezone.utc).isoformat(),
            "package_count": len(self.packages),
            "packages": [p.to_dict() for p in self.packages],
            "options_summary": dict(self.options_summary),
            "notes": list(self.notes),
            "incomplete_research_count": sum(1 for p in self.packages if p.incomplete_research),
            "go_signal_count": 0,
            "phase": "architecture_8_decision_packages",
        }
        payload.update(research_lock_fields(command="decide"))
        return payload
