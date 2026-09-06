"""Backtest report schema. Research-only — never a GO or order ticket."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from trading_system.research_lock import research_lock_fields


@dataclass(frozen=True)
class CostModel:
    """Round-trip costs applied to synthetic long-premium fills."""

    commission_per_contract: float = 0.65
    slippage_pct: float = 0.02  # fraction of debit/mark, each side

    def to_dict(self) -> dict[str, Any]:
        return {
            "commission_per_contract": self.commission_per_contract,
            "slippage_pct": self.slippage_pct,
        }


@dataclass(frozen=True)
class PremiumSpec:
    """Transparent synthetic long-premium proxy (not a live option quote)."""

    otm_pct: float = 0.02
    min_debit_usd: float = 20.0
    max_debit_usd: float = 150.0
    hold_bars: int = 15
    stop_pct: float = 0.04
    target_pct: float = 0.08

    def to_dict(self) -> dict[str, Any]:
        return {
            "otm_pct": self.otm_pct,
            "min_debit_usd": self.min_debit_usd,
            "max_debit_usd": self.max_debit_usd,
            "hold_bars": self.hold_bars,
            "stop_pct": self.stop_pct,
            "target_pct": self.target_pct,
            "note": (
                "Synthetic long call/put: OTM strike + decaying extrinsic. "
                "Not a historical option chain. Max loss ≈ debit + costs."
            ),
        }


@dataclass(frozen=True)
class BacktestTrade:
    symbol: str
    side: str  # LONG -> long_call | SHORT -> long_put
    strategy: str
    signal_index: int
    entry_index: int
    exit_index: int
    signal_time: datetime
    entry_time: datetime
    exit_time: datetime
    signal_close: float
    entry_underlying: float
    exit_underlying: float
    strike: float
    debit_usd: float
    exit_mark_usd: float
    gross_pnl_usd: float
    costs_usd: float
    net_pnl_usd: float
    exit_reason: str
    split: str  # in_sample | oos | walk_forward
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "strategy": self.strategy,
            "signal_index": self.signal_index,
            "entry_index": self.entry_index,
            "exit_index": self.exit_index,
            "signal_time": self.signal_time.isoformat(),
            "entry_time": self.entry_time.isoformat(),
            "exit_time": self.exit_time.isoformat(),
            "signal_close": round(self.signal_close, 4),
            "entry_underlying": round(self.entry_underlying, 4),
            "exit_underlying": round(self.exit_underlying, 4),
            "strike": round(self.strike, 4),
            "debit_usd": round(self.debit_usd, 2),
            "exit_mark_usd": round(self.exit_mark_usd, 2),
            "gross_pnl_usd": round(self.gross_pnl_usd, 2),
            "costs_usd": round(self.costs_usd, 2),
            "net_pnl_usd": round(self.net_pnl_usd, 2),
            "exit_reason": self.exit_reason,
            "split": self.split,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class SplitMetrics:
    label: str
    n_trades: int
    wins: int
    losses: int
    win_rate: float | None
    gross_pnl_usd: float
    costs_usd: float
    net_pnl_usd: float
    avg_net_usd: float | None
    max_drawdown_usd: float
    profit_factor: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "n_trades": self.n_trades,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": None if self.win_rate is None else round(self.win_rate, 4),
            "gross_pnl_usd": round(self.gross_pnl_usd, 2),
            "costs_usd": round(self.costs_usd, 2),
            "net_pnl_usd": round(self.net_pnl_usd, 2),
            "avg_net_usd": None if self.avg_net_usd is None else round(self.avg_net_usd, 2),
            "max_drawdown_usd": round(self.max_drawdown_usd, 2),
            "profit_factor": None if self.profit_factor is None else round(self.profit_factor, 3),
        }


@dataclass(frozen=True)
class BacktestReport:
    symbol: str
    setup: str
    bar_count: int
    lookback: int
    split_mode: str
    cost_model: CostModel
    premium: PremiumSpec
    trades: tuple[BacktestTrade, ...]
    metrics: dict[str, SplitMetrics] = field(default_factory=dict)
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "symbol": self.symbol,
            "setup": self.setup,
            "bar_count": self.bar_count,
            "lookback": self.lookback,
            "split_mode": self.split_mode,
            "cost_model": self.cost_model.to_dict(),
            "premium": self.premium.to_dict(),
            "trade_count": len(self.trades),
            "trades": [t.to_dict() for t in self.trades],
            "metrics": {k: v.to_dict() for k, v in self.metrics.items()},
            "notes": list(self.notes),
            "phase": "architecture_7_backtester",
            "go_signal": False,
        }
        payload.update(research_lock_fields(command="backtest"))
        return payload
