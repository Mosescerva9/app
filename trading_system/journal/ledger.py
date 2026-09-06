"""In-memory paper ledger. Honest stub: not RESEARCH_COMPLETE."""

from __future__ import annotations

from datetime import datetime, timezone

from trading_system.backtest.types import BacktestReport
from trading_system.journal.types import JournalEntry
from trading_system.research_lock import research_lock_fields

PHASE9_COMPLETE = False
PHASE9_NOTE = (
    "Phase 9 paper journal is a thin research ledger stub. It does not simulate "
    "a broker paper account, fills, or day/week loss tracking. "
    "RESEARCH_COMPLETE stays false until a real paper loop exists."
)


class PaperLedger:
    name = "stub"

    def __init__(self) -> None:
        self._entries: list[JournalEntry] = []

    def record(self, entry: JournalEntry) -> None:
        self._entries.append(entry)

    def record_backtest(self, report: BacktestReport) -> int:
        now = datetime.now(timezone.utc)
        for trade in report.trades:
            self.record(
                JournalEntry(
                    recorded_at=now,
                    symbol=trade.symbol,
                    strategy=trade.strategy,
                    side=trade.side,
                    source="backtest",
                    net_pnl_usd=trade.net_pnl_usd,
                    notes=(
                        f"exit={trade.exit_reason}",
                        f"split={trade.split}",
                        "stub ledger — not a paper broker fill",
                    ),
                )
            )
        return len(report.trades)

    def entries(self) -> tuple[JournalEntry, ...]:
        return tuple(self._entries)

    def to_dict(self) -> dict:
        payload = {
            "phase": "architecture_9_paper_journal_stub",
            "phase9_complete": PHASE9_COMPLETE,
            "ledger": self.name,
            "entry_count": len(self._entries),
            "entries": [e.to_dict() for e in self._entries],
            "notes": [PHASE9_NOTE],
        }
        payload.update(research_lock_fields(command="journal"))
        return payload
