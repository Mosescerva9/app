"""Structured adversarial critique — Phase 8 Decision Package fields."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AdversarialCritique:
    why_trade_fails: tuple[str, ...]
    instant_reject_conditions: tuple[str, ...]
    better_strike_dte_or_stand_aside: str
    confidence_penalty: float
    critic: str = "rule_based"
    stand_aside: bool = False
    reject: bool = False
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "why_trade_fails": list(self.why_trade_fails),
            "instant_reject_conditions": list(self.instant_reject_conditions),
            "better_strike_dte_or_stand_aside": self.better_strike_dte_or_stand_aside,
            "confidence_penalty": round(self.confidence_penalty, 2),
            "critic": self.critic,
            "stand_aside": self.stand_aside,
            "reject": self.reject,
            "notes": list(self.notes),
        }
