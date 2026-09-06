"""Hard filters for option contracts on a ~$1,500 account (~$150 risk/trade)."""

from __future__ import annotations

from dataclasses import dataclass

from trading_system.options.types import OptionContract
from trading_system.risk.limits import RiskLimits


@dataclass(frozen=True)
class OptionFilterConfig:
    min_dte: int = 30
    max_dte: int = 60
    min_abs_delta: float = 0.25
    max_abs_delta: float = 0.45
    min_open_interest: int = 200
    max_spread_pct: float = 0.12  # 12% of mid
    # Prefer contracts whose full premium fits inside the per-trade risk budget.
    require_premium_within_risk_budget: bool = True


@dataclass(frozen=True)
class FilterResult:
    ok: bool
    reason: str = ""


def filter_contract(
    contract: OptionContract,
    *,
    side_bias: str,
    limits: RiskLimits,
    config: OptionFilterConfig | None = None,
) -> FilterResult:
    """
    Return whether a contract is eligible for long-premium directional trades.

    side_bias: LONG → calls only; SHORT → puts only.
    """
    cfg = config or OptionFilterConfig()
    bias = side_bias.upper()

    if bias == "LONG" and contract.right != "CALL":
        return FilterResult(False, "right_mismatch_long_needs_call")
    if bias == "SHORT" and contract.right != "PUT":
        return FilterResult(False, "right_mismatch_short_needs_put")
    if bias not in {"LONG", "SHORT"}:
        return FilterResult(False, "unsupported_side_bias")

    if contract.dte < cfg.min_dte:
        return FilterResult(False, "dte_too_short")
    if contract.dte > cfg.max_dte:
        return FilterResult(False, "dte_too_long")

    abs_delta = abs(contract.delta)
    if abs_delta < cfg.min_abs_delta:
        return FilterResult(False, "delta_too_low")
    if abs_delta > cfg.max_abs_delta:
        return FilterResult(False, "delta_too_high")

    if contract.open_interest < cfg.min_open_interest:
        return FilterResult(False, "open_interest_too_low")

    if contract.mid <= 0:
        return FilterResult(False, "invalid_mid")
    if contract.spread_pct > cfg.max_spread_pct:
        return FilterResult(False, "spread_too_wide")

    premium = contract.premium_per_contract_usd
    if cfg.require_premium_within_risk_budget and premium > limits.max_risk_per_trade_usd:
        return FilterResult(False, "premium_exceeds_risk_budget")

    if premium <= 0:
        return FilterResult(False, "invalid_premium")

    return FilterResult(True, "passed")
