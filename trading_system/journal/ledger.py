"""Thin paper ledger stub. Optional JSON file; not a broker paper loop."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from trading_system.backtest.types import BacktestReport
from trading_system.journal.types import JournalEntry
from trading_system.research_lock import research_lock_fields

PHASE9_COMPLETE = False
PHASE9_NOTE = (
    "Phase 9 paper journal is a thin research ledger stub. It does not simulate "
    "a broker paper account, fills, or day/week loss tracking. "
    "RESEARCH_COMPLETE stays false until a real paper loop exists."
)

DEFAULT_LEDGER_PATH = Path("data/paper_journal.json")


def _parse_ts(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


class PaperLedger:
    name = "stub"

    def __init__(self, path: Path | None = DEFAULT_LEDGER_PATH) -> None:
        self.path = path
        self._entries: list[JournalEntry] = []
        self._load()

    def _load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError):
            return
        rows = raw.get("entries") if isinstance(raw, dict) else raw
        if not isinstance(rows, list):
            return
        loaded: list[JournalEntry] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                loaded.append(
                    JournalEntry(
                        recorded_at=_parse_ts(str(row.get("recorded_at"))),
                        symbol=str(row.get("symbol") or ""),
                        strategy=str(row.get("strategy") or ""),
                        side=str(row.get("side") or ""),
                        source=str(row.get("source") or "stub"),
                        net_pnl_usd=row.get("net_pnl_usd"),
                        notes=tuple(row.get("notes") or ()),
                    )
                )
            except (TypeError, ValueError):
                continue
        self._entries = loaded

    def _persist(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "phase9_complete": PHASE9_COMPLETE,
            "entries": [e.to_dict() for e in self._entries],
        }
        self.path.write_text(json.dumps(payload, indent=2))

    def record(self, entry: JournalEntry) -> None:
        self._entries.append(entry)
        self._persist()

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
                    net_pnl_usd=round(trade.net_pnl_usd, 2),
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
            "path": str(self.path) if self.path is not None else None,
            "entry_count": len(self._entries),
            "entries": [e.to_dict() for e in self._entries],
            "notes": [PHASE9_NOTE],
        }
        payload.update(research_lock_fields(command="journal"))
        return payload
