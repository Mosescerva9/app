"""Adversarial critic interface + optional LLM hook (no live LLM in CI)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from trading_system.adversarial.types import AdversarialCritique
from trading_system.events.types import CatalystSnapshot
from trading_system.options.types import OptionCandidate
from trading_system.risk.limits import RiskLimits
from trading_system.scanner.types import Opportunity


@dataclass(frozen=True)
class CritiqueContext:
    opportunity: Opportunity
    option: OptionCandidate | None
    catalyst: CatalystSnapshot
    risk: RiskLimits
    extras: dict[str, Any] | None = None


class AdversarialCritic(ABC):
    """Return a structured critique, or None to defer to another critic."""

    name: str

    @abstractmethod
    def critique(self, context: CritiqueContext) -> AdversarialCritique | None:
        raise NotImplementedError


class CompositeAdversarialCritic(AdversarialCritic):
    """Rule-based first; optional LLM overlay merges extra reasons only."""

    name = "composite"

    def __init__(
        self,
        primary: AdversarialCritic,
        overlay: AdversarialCritic | None = None,
    ) -> None:
        self.primary = primary
        self.overlay = overlay

    def critique(self, context: CritiqueContext) -> AdversarialCritique:
        base = self.primary.critique(context)
        if base is None:
            raise RuntimeError("primary adversarial critic must return a critique")
        extra = self.overlay.critique(context) if self.overlay is not None else None
        if extra is None:
            return base
        why = tuple(dict.fromkeys([*base.why_trade_fails, *extra.why_trade_fails]))
        rejects = tuple(
            dict.fromkeys([*base.instant_reject_conditions, *extra.instant_reject_conditions])
        )
        penalty = min(80.0, max(base.confidence_penalty, extra.confidence_penalty))
        suggestion = extra.better_strike_dte_or_stand_aside or base.better_strike_dte_or_stand_aside
        return AdversarialCritique(
            why_trade_fails=why,
            instant_reject_conditions=rejects,
            better_strike_dte_or_stand_aside=suggestion,
            confidence_penalty=penalty,
            critic=f"{base.critic}+{extra.critic}",
            stand_aside=base.stand_aside or extra.stand_aside,
            reject=base.reject or extra.reject,
            notes=tuple(dict.fromkeys([*base.notes, *extra.notes])),
        )
