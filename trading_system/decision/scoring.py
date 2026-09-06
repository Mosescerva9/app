"""Decision Package overall score — architecture weights, missing dims excluded."""

from __future__ import annotations

# From docs/ARCHITECTURE_AUDIT.md scoring table (Phase 8 research blend).
DECISION_WEIGHTS: dict[str, float] = {
    "regime_fit": 0.18,
    "liquidity": 0.15,
    "risk_reward": 0.15,
    "options_quality": 0.12,
    "momentum": 0.10,
    "technical": 0.08,
    "catalyst": 0.08,
    "crowding": 0.07,
    "fundamental": 0.07,
}


def blend_decision_overall(
    *,
    technical: float | None,
    momentum: float | None,
    liquidity: float | None,
    regime_fit: float | None,
    risk_reward: float | None,
    crowding_risk: float | None,
    options_quality: float | None,
    catalyst: float | None,
    fundamental: float | None,
) -> tuple[float, dict[str, float]]:
    values: dict[str, float] = {}
    if regime_fit is not None:
        values["regime_fit"] = regime_fit
    if liquidity is not None:
        values["liquidity"] = liquidity
    if risk_reward is not None:
        values["risk_reward"] = risk_reward
    if options_quality is not None:
        values["options_quality"] = options_quality
    if momentum is not None:
        values["momentum"] = momentum
    if technical is not None:
        values["technical"] = technical
    if catalyst is not None:
        values["catalyst"] = catalyst
    if crowding_risk is not None:
        values["crowding"] = max(0.0, 100.0 - crowding_risk)
    if fundamental is not None:
        values["fundamental"] = fundamental
    active = {k: DECISION_WEIGHTS[k] for k in values if k in DECISION_WEIGHTS}
    total = sum(active.values()) or 1.0
    weights = {k: w / total for k, w in active.items()}
    overall = sum(values[k] * weights[k] for k in weights)
    return round(overall, 2), {k: round(v, 4) for k, v in weights.items()}
