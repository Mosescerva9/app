"""Thin paper-journal rows. Phase 9 is a stub — not a broker paper loop."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class JournalEntry:
    recorded_at: datetime
    symbol: str
    strategy: str
    side: str
    source: str  # backtest | manual | stub
    net_pnl_usd: float | None
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "recorded_at": self.recorded_at.isoformat(),
            "symbol": self.symbol,
            "strategy": self.strategy,
            "side": self.side,
            "source": self.source,
            "net_pnl_usd": self.net_pnl_usd,
            "notes": list(self.notes),
        }
