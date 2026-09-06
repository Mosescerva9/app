"""Hard filters for option contracts on a ~$1,500 account (~$150 risk/trade)."""

from __future__ import annotations

from dataclasses import dataclass, replace

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
    # When the per-trade book is this small — or mid-delta is empty because
    # every liquid name blows the premium cap — widen long-premium selection
    # so cheap OTM can surface instead of 0 candidates.
    small_book_risk_usd: float = 150.0
    relaxed_min_abs_delta: float = 0.08
    relaxed_max_abs_delta: float = 0.35
    relaxed_min_dte: int = 14
    auto_relax_when_budget_binds: bool = True
    prefer_feasible_over_empty: bool = True
    budget_feasible_min_score: float = 35.0


@dataclass(frozen=True)
class FilterResult:
    ok: bool
    reason: str = ""


def budget_binds_small_book(limits: RiskLimits, config: OptionFilterConfig) -> bool:
    return limits.max_risk_per_trade_usd <= config.small_book_risk_usd + 1e-9


def resolve_filter_config(
    limits: RiskLimits,
    config: OptionFilterConfig | None = None,
    *,
    relax: bool = False,
) -> OptionFilterConfig:
    """Return the filter window to apply for this book.

    Default mid-delta / 30–60 DTE stays in force on larger books. A ≤$150
    per-trade budget (or an explicit ``relax`` retry when that band is empty)
    lowers |delta| to 0.08–0.35 and allows DTE ≥14. Hard premium / right /
    liquidity caps are unchanged.
    """
    cfg = config or OptionFilterConfig()
    if not cfg.auto_relax_when_budget_binds:
        return cfg
    if not (relax or budget_binds_small_book(limits, cfg)):
        return cfg
    return replace(
        cfg,
        min_dte=min(cfg.min_dte, cfg.relaxed_min_dte),
        min_abs_delta=min(cfg.min_abs_delta, cfg.relaxed_min_abs_delta),
        max_abs_delta=cfg.relaxed_max_abs_delta,
    )


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
    cfg = resolve_filter_config(limits, config)
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
