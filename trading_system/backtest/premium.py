"""Synthetic long-premium mark. Not a historical option quote."""

from __future__ import annotations

from trading_system.backtest.types import PremiumSpec
from trading_system.risk.limits import RiskLimits


def clamp_debit(raw: float, spec: PremiumSpec, risk: RiskLimits | None = None) -> float:
    cap = spec.max_debit_usd
    if risk is not None:
        cap = min(cap, risk.max_risk_per_trade_usd)
    return max(spec.min_debit_usd, min(cap, raw))


def strike_for(entry: float, side: str, spec: PremiumSpec) -> float:
    if side == "LONG":
        return entry * (1.0 + spec.otm_pct)
    return entry * (1.0 - spec.otm_pct)


def initial_debit_usd(entry: float, spec: PremiumSpec, risk: RiskLimits | None = None) -> float:
    """OTM proxy: a fraction of the OTM distance × 100, clamped to the $150 book."""
    raw = entry * spec.otm_pct * 100.0 * 0.35
    return clamp_debit(raw, spec, risk)


def intrinsic_usd(underlying: float, strike: float, side: str) -> float:
    if side == "LONG":
        return max(0.0, underlying - strike) * 100.0
    return max(0.0, strike - underlying) * 100.0


def mark_usd(
    *,
    underlying: float,
    strike: float,
    side: str,
    debit_usd: float,
    bars_held: int,
    hold_bars: int,
) -> float:
    """Intrinsic + linearly decaying leftover extrinsic. Floor at 0."""
    intrinsic = intrinsic_usd(underlying, strike, side)
    entry_intrinsic = 0.0  # entries are constructed OTM
    extrinsic0 = max(0.0, debit_usd - entry_intrinsic)
    frac = 0.0 if hold_bars <= 0 else max(0.0, 1.0 - bars_held / hold_bars)
    return max(0.0, intrinsic + extrinsic0 * frac)
