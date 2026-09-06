"""Commission + slippage for synthetic long-premium fills."""

from __future__ import annotations

from trading_system.backtest.types import CostModel


def round_trip_costs(debit_usd: float, exit_mark_usd: float, costs: CostModel) -> float:
    """Entry pay-up + exit haircut + two commissions. Never negative costs."""
    entry_slip = max(0.0, debit_usd * costs.slippage_pct)
    exit_slip = max(0.0, exit_mark_usd * costs.slippage_pct)
    commissions = 2.0 * max(0.0, costs.commission_per_contract)
    return round(entry_slip + exit_slip + commissions, 6)
