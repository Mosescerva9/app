"""Deterministic scoring for filtered option contracts."""

from __future__ import annotations

from trading_system.options.types import OptionContract, OptionContractScores
from trading_system.risk.limits import RiskLimits

OPTION_SCORE_WEIGHTS: dict[str, float] = {
    "liquidity": 0.30,
    "delta_fit": 0.25,
    "iv_sanity": 0.15,
    "theta_drag": 0.15,
    "risk_fit": 0.15,
}


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def score_contract(
    contract: OptionContract,
    *,
    limits: RiskLimits,
    target_abs_delta: float = 0.35,
) -> OptionContractScores:
    reasons: list[str] = []

    # Liquidity: OI + tight spread
    oi_score = _clamp(contract.open_interest / 50.0)  # 5000 OI → 100
    spread_score = _clamp(100.0 * (1.0 - contract.spread_pct / 0.12))
    vol_score = _clamp(contract.volume / 20.0)
    liquidity = round(0.5 * oi_score + 0.35 * spread_score + 0.15 * vol_score, 2)
    if liquidity >= 70:
        reasons.append("liquid_contract")
    elif liquidity < 40:
        reasons.append("thin_liquidity")

    # Delta fit around target
    abs_delta = abs(contract.delta)
    delta_err = abs(abs_delta - target_abs_delta)
    delta_fit = round(_clamp(100.0 * (1.0 - delta_err / 0.20)), 2)
    if delta_err <= 0.05:
        reasons.append("delta_near_target")

    # IV sanity: prefer moderate IV (very high IV = expensive premium)
    iv = contract.implied_volatility
    if iv <= 0:
        iv_sanity = 20.0
        reasons.append("missing_iv")
    elif 0.15 <= iv <= 0.45:
        iv_sanity = 90.0
        reasons.append("moderate_iv")
    elif iv < 0.15:
        iv_sanity = 70.0
    elif iv <= 0.70:
        iv_sanity = 55.0
        reasons.append("elevated_iv")
    else:
        iv_sanity = 25.0
        reasons.append("very_high_iv")

    # Theta drag: less painful on longer DTE within window
    # Prefer mid-window DTE (~45) and not-too-expensive theta relative to premium
    dte_center = abs(contract.dte - 45) / 30.0
    dte_score = _clamp(100.0 * (1.0 - dte_center))
    theta_per_day = abs(contract.theta)
    premium = max(contract.mid, 0.01)
    theta_ratio = theta_per_day / (premium * 100.0)  # fraction of premium per day (rough)
    theta_ratio_score = _clamp(100.0 * (1.0 - theta_ratio / 0.05))
    theta_drag = round(0.6 * dte_score + 0.4 * theta_ratio_score, 2)
    if contract.dte >= 40:
        reasons.append("dte_in_sweet_spot")

    # Risk fit: how well premium sits inside the per-trade budget (~$150 on $1,500)
    max_risk = max(limits.max_risk_per_trade_usd, 1.0)
    premium_usd = contract.premium_per_contract_usd
    utilization = premium_usd / max_risk
    if 0.5 <= utilization <= 0.95:
        risk_fit = 95.0
        reasons.append("premium_fits_budget_well")
    elif utilization < 0.5:
        risk_fit = 70.0 + utilization * 40.0
    elif utilization <= 1.0:
        risk_fit = 80.0
    else:
        risk_fit = 10.0
        reasons.append("premium_over_budget")
    risk_fit = round(_clamp(risk_fit), 2)

    overall = round(
        OPTION_SCORE_WEIGHTS["liquidity"] * liquidity
        + OPTION_SCORE_WEIGHTS["delta_fit"] * delta_fit
        + OPTION_SCORE_WEIGHTS["iv_sanity"] * iv_sanity
        + OPTION_SCORE_WEIGHTS["theta_drag"] * theta_drag
        + OPTION_SCORE_WEIGHTS["risk_fit"] * risk_fit,
        2,
    )

    return OptionContractScores(
        liquidity=liquidity,
        delta_fit=delta_fit,
        iv_sanity=round(iv_sanity, 2),
        theta_drag=theta_drag,
        risk_fit=risk_fit,
        overall=overall,
        reasons=tuple(reasons),
    )
