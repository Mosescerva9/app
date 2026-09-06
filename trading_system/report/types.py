"""Phase 10 daily/weekly text report schema (no dashboard, no broker GO)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class ResearchReport:
    as_of: datetime
    period: str  # daily | weekly
    text: str
    status: dict[str, Any] = field(default_factory=dict)
    regime: dict[str, Any] = field(default_factory=dict)
    decide_flags: dict[str, Any] = field(default_factory=dict)
    journal_snapshot: dict[str, Any] = field(default_factory=dict)
    backtest_pointer: dict[str, Any] = field(default_factory=dict)
    packages: tuple[dict[str, Any], ...] = ()
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_of": self.as_of.astimezone(timezone.utc).isoformat(),
            "period": self.period,
            "text": self.text,
            "status": dict(self.status),
            "regime": dict(self.regime),
            "decide_flags": dict(self.decide_flags),
            "journal_snapshot": dict(self.journal_snapshot),
            "backtest_pointer": dict(self.backtest_pointer),
            "packages": [dict(p) for p in self.packages],
            "notes": list(self.notes),
            "phase": "architecture_10_research_report",
            "go_signal": False,
        }
