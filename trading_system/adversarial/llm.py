"""Optional LLM critique hook. CI uses the null implementation — no network."""

from __future__ import annotations

from trading_system.adversarial.base import AdversarialCritic, CritiqueContext
from trading_system.adversarial.types import AdversarialCritique


class NullLLMCritic(AdversarialCritic):
    """Default overlay: do not call a model. Keeps pytest deterministic."""

    name = "llm_null"

    def critique(self, context: CritiqueContext) -> AdversarialCritique | None:
        return None


class CallableLLMCritic(AdversarialCritic):
    """Hook for a later operator-supplied callable. Not invoked unless injected."""

    name = "llm_callable"

    def __init__(self, fn) -> None:
        self._fn = fn

    def critique(self, context: CritiqueContext) -> AdversarialCritique | None:
        return self._fn(context)
