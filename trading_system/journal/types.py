"""Paper-journal rows for the Phase 9 RESEARCH practice loop (no broker orders)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


@dataclass(frozen=True)
class JournalEntry:
    recorded_at: datetime
    symbol: str
    strategy: str
    side: str
    source: str  # paper_open | paper_close | paper_note | backtest
    net_pnl_usd: float | None
    notes: tuple[str, ...] = ()
    position_id: str = ""
    fill_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "recorded_at": _iso(self.recorded_at),
            "symbol": self.symbol,
            "strategy": self.strategy,
            "side": self.side,
            "source": self.source,
            "net_pnl_usd": self.net_pnl_usd,
            "notes": list(self.notes),
            "position_id": self.position_id,
            "fill_id": self.fill_id,
        }


@dataclass(frozen=True)
class PaperFill:
    fill_id: str
    position_id: str
    filled_at: datetime
    symbol: str
    option_symbol: str
    strategy: str
    side: str  # buy_to_open | sell_to_close
    quantity: int
    premium_usd: float
    cash_delta_usd: float
    source: str
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "fill_id": self.fill_id,
            "position_id": self.position_id,
            "filled_at": _iso(self.filled_at),
            "symbol": self.symbol,
            "option_symbol": self.option_symbol,
            "strategy": self.strategy,
            "side": self.side,
            "quantity": self.quantity,
            "premium_usd": round(self.premium_usd, 2),
            "cash_delta_usd": round(self.cash_delta_usd, 2),
            "source": self.source,
            "notes": list(self.notes),
        }


@dataclass
class PaperPosition:
    position_id: str
    opened_at: datetime
    symbol: str
    option_symbol: str
    strategy: str
    quantity: int
    entry_premium_usd: float
    mark_usd: float
    package_recommendation: str
    closed_at: datetime | None = None
    exit_premium_usd: float | None = None
    realized_pnl_usd: float | None = None
    status: str = "open"
    notes: tuple[str, ...] = ()

    @property
    def unrealized_pnl_usd(self) -> float:
        if self.status != "open":
            return 0.0
        return round((self.mark_usd - self.entry_premium_usd) * self.quantity, 2)

    @property
    def market_value_usd(self) -> float:
        if self.status != "open":
            return 0.0
        return round(max(0.0, self.mark_usd) * self.quantity, 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "position_id": self.position_id,
            "opened_at": _iso(self.opened_at),
            "closed_at": None if self.closed_at is None else _iso(self.closed_at),
            "symbol": self.symbol,
            "option_symbol": self.option_symbol,
            "strategy": self.strategy,
            "quantity": self.quantity,
            "entry_premium_usd": round(self.entry_premium_usd, 2),
            "exit_premium_usd": (
                None if self.exit_premium_usd is None else round(self.exit_premium_usd, 2)
            ),
            "mark_usd": round(self.mark_usd, 2),
            "realized_pnl_usd": (
                None if self.realized_pnl_usd is None else round(self.realized_pnl_usd, 2)
            ),
            "unrealized_pnl_usd": self.unrealized_pnl_usd,
            "market_value_usd": self.market_value_usd,
            "status": self.status,
            "package_recommendation": self.package_recommendation,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class PaperAccountSnapshot:
    starting_cash_usd: float
    cash_usd: float
    market_value_usd: float
    equity_usd: float
    realized_pnl_usd: float
    unrealized_pnl_usd: float
    daily_pnl_usd: float
    weekly_pnl_usd: float
    open_position_count: int
    closed_position_count: int
    fill_count: int
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "starting_cash_usd": round(self.starting_cash_usd, 2),
            "cash_usd": round(self.cash_usd, 2),
            "market_value_usd": round(self.market_value_usd, 2),
            "equity_usd": round(self.equity_usd, 2),
            "realized_pnl_usd": round(self.realized_pnl_usd, 2),
            "unrealized_pnl_usd": round(self.unrealized_pnl_usd, 2),
            "daily_pnl_usd": round(self.daily_pnl_usd, 2),
            "weekly_pnl_usd": round(self.weekly_pnl_usd, 2),
            "open_position_count": self.open_position_count,
            "closed_position_count": self.closed_position_count,
            "fill_count": self.fill_count,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class PaperActionResult:
    accepted: bool
    action: str
    reason: str
    recommendation: str
    position_id: str = ""
    fill_id: str = ""
    cash_usd: float = 0.0
    notes: tuple[str, ...] = ()
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "accepted": self.accepted,
            "action": self.action,
            "reason": self.reason,
            "recommendation": self.recommendation,
            "position_id": self.position_id,
            "fill_id": self.fill_id,
            "cash_usd": round(self.cash_usd, 2),
            "notes": list(self.notes),
            "broker_order_placed": False,
            "paper_only": True,
        }
        payload.update(self.extra)
        return payload
