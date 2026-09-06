"""Phase 9 paper ledger: simulated long-premium fills, never broker orders."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from trading_system.backtest.types import BacktestReport
from trading_system.decision.types import DecisionPackage
from trading_system.journal.types import (
    JournalEntry,
    PaperAccountSnapshot,
    PaperActionResult,
    PaperFill,
    PaperPosition,
)
from trading_system.research_lock import research_lock_fields
from trading_system.risk.limits import RiskLimits

PHASE9_COMPLETE = True
PHASE9_NOTE = (
    "Phase 9 paper journal is a real RESEARCH practice loop: simulated long-premium "
    "positions, fills, P&L, and $1,500 / $150 risk caps. Commands are paper-only and "
    "never place broker orders. RESEARCH_COMPLETE is a research-desk flag; "
    "LIVE_EXECUTION_UNLOCKED stays false and no broker GO is emitted."
)

DEFAULT_LEDGER_PATH = Path("data/paper_journal.json")
LEDGER_SCHEMA = "paper_ledger_v1"
LONG_PREMIUM = frozenset({"long_call", "long_put"})
OPENABLE_RECOMMENDATIONS = frozenset({"candidate"})


def default_paper_risk() -> RiskLimits:
    return RiskLimits(
        account_equity_usd=1500.0,
        max_risk_per_trade_pct=0.10,
        max_simultaneous_positions=2,
        max_daily_loss_pct=0.05,
        max_weekly_loss_pct=0.10,
        emergency_stop=False,
    )


def _parse_ts(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))


def _aware(now: datetime | None) -> datetime:
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        return stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def _monday(day) -> datetime:
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    return start - timedelta(days=start.weekday())


class PaperLedger:
    """File-backed simulated account. Never calls a broker."""

    name = "paper_ledger"

    def __init__(
        self,
        path: Path | None = DEFAULT_LEDGER_PATH,
        *,
        risk: RiskLimits | None = None,
        starting_cash_usd: float | None = None,
    ) -> None:
        self.path = path
        self.risk = risk or default_paper_risk()
        self.starting_cash_usd = float(
            starting_cash_usd if starting_cash_usd is not None else self.risk.account_equity_usd
        )
        self._cash_usd = float(self.starting_cash_usd)
        self._positions: list[PaperPosition] = []
        self._fills: list[PaperFill] = []
        self._entries: list[JournalEntry] = []
        self._position_seq = 0
        self._fill_seq = 0
        self._last_backtest: dict[str, Any] | None = None
        self._load()

    def _load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(raw, dict):
            return
        start = raw.get("starting_cash_usd")
        if isinstance(start, (int, float)):
            self.starting_cash_usd = float(start)
        cash = raw.get("cash_usd")
        if isinstance(cash, (int, float)):
            self._cash_usd = max(0.0, float(cash))
        else:
            self._cash_usd = self.starting_cash_usd
        self._position_seq = int(raw.get("position_seq") or 0)
        self._fill_seq = int(raw.get("fill_seq") or 0)
        self._positions = [
            self._position_from_dict(row) for row in raw.get("positions") or [] if isinstance(row, dict)
        ]
        self._positions = [p for p in self._positions if p is not None]
        self._fills = [
            self._fill_from_dict(row) for row in raw.get("fills") or [] if isinstance(row, dict)
        ]
        self._fills = [f for f in self._fills if f is not None]
        self._entries = []
        for row in raw.get("entries") or []:
            if not isinstance(row, dict):
                continue
            try:
                self._entries.append(
                    JournalEntry(
                        recorded_at=_parse_ts(str(row.get("recorded_at"))),
                        symbol=str(row.get("symbol") or ""),
                        strategy=str(row.get("strategy") or ""),
                        side=str(row.get("side") or ""),
                        source=str(row.get("source") or "paper_note"),
                        net_pnl_usd=row.get("net_pnl_usd"),
                        notes=tuple(row.get("notes") or ()),
                        position_id=str(row.get("position_id") or ""),
                        fill_id=str(row.get("fill_id") or ""),
                    )
                )
            except (TypeError, ValueError):
                continue
        stored = raw.get("last_backtest")
        if isinstance(stored, dict) and stored.get("symbol"):
            self._last_backtest = dict(stored)
        self._assert_cash_invariant()

    def _position_from_dict(self, row: dict[str, Any]) -> PaperPosition | None:
        try:
            return PaperPosition(
                position_id=str(row.get("position_id") or ""),
                opened_at=_parse_ts(row.get("opened_at")),
                closed_at=_parse_ts(row["closed_at"]) if row.get("closed_at") else None,
                symbol=str(row.get("symbol") or ""),
                option_symbol=str(row.get("option_symbol") or ""),
                strategy=str(row.get("strategy") or ""),
                quantity=int(row.get("quantity") or 1),
                entry_premium_usd=float(row.get("entry_premium_usd") or 0.0),
                exit_premium_usd=(
                    None
                    if row.get("exit_premium_usd") is None
                    else float(row.get("exit_premium_usd"))
                ),
                mark_usd=float(row.get("mark_usd") or row.get("entry_premium_usd") or 0.0),
                realized_pnl_usd=(
                    None
                    if row.get("realized_pnl_usd") is None
                    else float(row.get("realized_pnl_usd"))
                ),
                status=str(row.get("status") or "open"),
                package_recommendation=str(row.get("package_recommendation") or ""),
                notes=tuple(row.get("notes") or ()),
            )
        except (TypeError, ValueError):
            return None

    def _fill_from_dict(self, row: dict[str, Any]) -> PaperFill | None:
        try:
            return PaperFill(
                fill_id=str(row.get("fill_id") or ""),
                position_id=str(row.get("position_id") or ""),
                filled_at=_parse_ts(row.get("filled_at")),
                symbol=str(row.get("symbol") or ""),
                option_symbol=str(row.get("option_symbol") or ""),
                strategy=str(row.get("strategy") or ""),
                side=str(row.get("side") or ""),
                quantity=int(row.get("quantity") or 1),
                premium_usd=float(row.get("premium_usd") or 0.0),
                cash_delta_usd=float(row.get("cash_delta_usd") or 0.0),
                source=str(row.get("source") or "paper"),
                notes=tuple(row.get("notes") or ()),
            )
        except (TypeError, ValueError):
            return None

    def _persist(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._state_dict(), indent=2))

    def _state_dict(self) -> dict[str, Any]:
        snap = self.account_snapshot()
        return {
            "schema": LEDGER_SCHEMA,
            "phase9_complete": PHASE9_COMPLETE,
            "starting_cash_usd": round(self.starting_cash_usd, 2),
            "cash_usd": round(self._cash_usd, 2),
            "position_seq": self._position_seq,
            "fill_seq": self._fill_seq,
            "account": snap.to_dict(),
            "positions": [p.to_dict() for p in self._positions],
            "fills": [f.to_dict() for f in self._fills],
            "entries": [e.to_dict() for e in self._entries],
            "last_backtest": None if self._last_backtest is None else dict(self._last_backtest),
        }

    def _assert_cash_invariant(self) -> None:
        if self._cash_usd < -1e-9:
            raise RuntimeError(f"paper ledger cash invariant violated: cash={self._cash_usd}")
        self._cash_usd = max(0.0, round(self._cash_usd, 2))

    def _apply_cash_delta(self, delta: float) -> None:
        next_cash = round(self._cash_usd + delta, 2)
        if next_cash < -1e-9:
            raise RuntimeError(
                f"paper ledger refused cash move that would go negative "
                f"({self._cash_usd} + {delta})"
            )
        self._cash_usd = max(0.0, next_cash)

    def _next_position_id(self) -> str:
        self._position_seq += 1
        return f"PAPER-{self._position_seq:04d}"

    def _next_fill_id(self) -> str:
        self._fill_seq += 1
        return f"FILL-{self._fill_seq:04d}"

    def open_positions(self) -> tuple[PaperPosition, ...]:
        return tuple(p for p in self._positions if p.status == "open")

    def fills(self) -> tuple[PaperFill, ...]:
        return tuple(self._fills)

    def entries(self) -> tuple[JournalEntry, ...]:
        return tuple(self._entries)

    def account_snapshot(self, *, now: datetime | None = None) -> PaperAccountSnapshot:
        stamp = _aware(now)
        opens = self.open_positions()
        closed = [p for p in self._positions if p.status == "closed"]
        market_value = sum(p.market_value_usd for p in opens)
        unrealized = sum(p.unrealized_pnl_usd for p in opens)
        realized = sum(p.realized_pnl_usd or 0.0 for p in closed)
        equity = round(self._cash_usd + market_value, 2)
        return PaperAccountSnapshot(
            starting_cash_usd=self.starting_cash_usd,
            cash_usd=self._cash_usd,
            market_value_usd=round(market_value, 2),
            equity_usd=equity,
            realized_pnl_usd=round(realized, 2),
            unrealized_pnl_usd=round(unrealized, 2),
            daily_pnl_usd=self.period_pnl(stamp, days=1),
            weekly_pnl_usd=self.period_pnl(stamp, days=7),
            open_position_count=len(opens),
            closed_position_count=len(closed),
            fill_count=len(self._fills),
            notes=(
                "Simulated paper account. Not a Webull balance.",
                "Equity = cash + open long-premium marks.",
            ),
        )

    def period_pnl(self, now: datetime, *, days: int) -> float:
        """Realized closes in the window plus current unrealized (halt input)."""
        stamp = _aware(now)
        if days >= 7:
            start = _monday(stamp.date())
        else:
            start = datetime(stamp.year, stamp.month, stamp.day, tzinfo=timezone.utc)
        realized = 0.0
        for pos in self._positions:
            if pos.status != "closed" or pos.closed_at is None or pos.realized_pnl_usd is None:
                continue
            closed_at = pos.closed_at if pos.closed_at.tzinfo else pos.closed_at.replace(
                tzinfo=timezone.utc
            )
            if closed_at >= start:
                realized += pos.realized_pnl_usd
        unrealized = sum(p.unrealized_pnl_usd for p in self.open_positions())
        return round(realized + unrealized, 2)

    def record(self, entry: JournalEntry) -> None:
        self._entries.append(entry)
        self._persist()

    def add_note(
        self,
        text: str,
        *,
        symbol: str = "",
        now: datetime | None = None,
    ) -> PaperActionResult:
        stamp = _aware(now)
        note = text.strip()
        if not note:
            return PaperActionResult(
                accepted=False,
                action="paper_note",
                reason="empty_note",
                recommendation="stand_aside",
                cash_usd=self._cash_usd,
                notes=("Journal note was empty.",),
            )
        self.record(
            JournalEntry(
                recorded_at=stamp,
                symbol=symbol.upper(),
                strategy="",
                side="",
                source="paper_note",
                net_pnl_usd=None,
                notes=(note,),
            )
        )
        return PaperActionResult(
            accepted=True,
            action="paper_note",
            reason="recorded",
            recommendation="stand_aside",
            cash_usd=self._cash_usd,
            notes=("Paper note recorded. No broker order.", note),
        )

    def record_backtest(self, report: BacktestReport) -> int:
        now = datetime.now(timezone.utc)
        all_metrics = report.metrics.get("all")
        self._last_backtest = {
            "available": True,
            "recorded_at": now.isoformat(),
            "symbol": report.symbol,
            "setup": report.setup,
            "split_mode": report.split_mode,
            "trade_count": len(report.trades),
            "net_pnl_usd": None if all_metrics is None else round(all_metrics.net_pnl_usd, 2),
            "win_rate": None if all_metrics is None else all_metrics.win_rate,
            "cli": f"python -m trading_system backtest {report.symbol} --split {report.split_mode}",
            "note": "synthetic long-premium; not historical OPRA",
        }
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
                        "backtest annotation only — not a paper fill and not a broker order",
                    ),
                )
            )
        if not report.trades:
            self._persist()
        return len(report.trades)

    def open_from_package(
        self,
        package: DecisionPackage | None,
        *,
        quantity: int = 1,
        now: datetime | None = None,
    ) -> PaperActionResult:
        stamp = _aware(now)
        qty = int(quantity)
        blockers = self._open_blockers(package, quantity=qty, now=stamp)
        if blockers:
            reason, notes = blockers
            return PaperActionResult(
                accepted=False,
                action="paper_open",
                reason=reason,
                recommendation="stand_aside",
                cash_usd=self._cash_usd,
                notes=notes,
            )
        assert package is not None and package.option_candidate is not None
        option = package.option_candidate
        debit = round(float(option.max_loss_usd) * qty, 2)
        position_id = self._next_position_id()
        fill_id = self._next_fill_id()
        fill = PaperFill(
            fill_id=fill_id,
            position_id=position_id,
            filled_at=stamp,
            symbol=package.symbol.upper(),
            option_symbol=option.contract.symbol,
            strategy=option.strategy,
            side="buy_to_open",
            quantity=qty,
            premium_usd=round(float(option.max_loss_usd), 2),
            cash_delta_usd=round(-debit, 2),
            source="paper_open",
            notes=(
                "PAPER-ONLY simulated buy-to-open. No Webull order.",
                f"debit={debit:.2f} recommendation={package.recommendation}",
            ),
        )
        position = PaperPosition(
            position_id=position_id,
            opened_at=stamp,
            symbol=package.symbol.upper(),
            option_symbol=option.contract.symbol,
            strategy=option.strategy,
            quantity=qty,
            entry_premium_usd=round(float(option.max_loss_usd), 2),
            mark_usd=round(float(option.max_loss_usd), 2),
            package_recommendation=package.recommendation,
            notes=(
                "Long-premium paper position. Max loss = debit paid.",
                f"package_as_of={package.as_of.isoformat()}",
            ),
        )
        self._apply_cash_delta(-debit)
        self._positions.append(position)
        self._fills.append(fill)
        self.record(
            JournalEntry(
                recorded_at=stamp,
                symbol=position.symbol,
                strategy=position.strategy,
                side="buy_to_open",
                source="paper_open",
                net_pnl_usd=None,
                notes=fill.notes,
                position_id=position_id,
                fill_id=fill_id,
            )
        )
        return PaperActionResult(
            accepted=True,
            action="paper_open",
            reason="paper_fill_simulated",
            recommendation=package.recommendation,
            position_id=position_id,
            fill_id=fill_id,
            cash_usd=self._cash_usd,
            notes=fill.notes,
            extra={"account": self.account_snapshot(now=stamp).to_dict()},
        )

    def close_position(
        self,
        position_id: str,
        *,
        exit_mark_usd: float,
        now: datetime | None = None,
        reason: str = "manual_paper_close",
    ) -> PaperActionResult:
        stamp = _aware(now)
        if exit_mark_usd < 0:
            return PaperActionResult(
                accepted=False,
                action="paper_close",
                reason="negative_exit_mark",
                recommendation="stand_aside",
                cash_usd=self._cash_usd,
                notes=("Exit mark cannot be negative.",),
            )
        position = next((p for p in self._positions if p.position_id == position_id), None)
        if position is None:
            return PaperActionResult(
                accepted=False,
                action="paper_close",
                reason="unknown_position",
                recommendation="stand_aside",
                cash_usd=self._cash_usd,
                notes=(f"No paper position {position_id!r}.",),
            )
        if position.status != "open":
            return PaperActionResult(
                accepted=False,
                action="paper_close",
                reason="already_closed",
                recommendation="stand_aside",
                cash_usd=self._cash_usd,
                position_id=position.position_id,
                notes=(f"{position_id} is already closed.",),
            )
        proceeds = round(float(exit_mark_usd) * position.quantity, 2)
        realized = round(proceeds - position.entry_premium_usd * position.quantity, 2)
        fill_id = self._next_fill_id()
        fill = PaperFill(
            fill_id=fill_id,
            position_id=position.position_id,
            filled_at=stamp,
            symbol=position.symbol,
            option_symbol=position.option_symbol,
            strategy=position.strategy,
            side="sell_to_close",
            quantity=position.quantity,
            premium_usd=round(float(exit_mark_usd), 2),
            cash_delta_usd=proceeds,
            source="paper_close",
            notes=(
                "PAPER-ONLY simulated sell-to-close. No Webull order.",
                f"exit_reason={reason}",
                f"realized_pnl_usd={realized:.2f}",
            ),
        )
        self._apply_cash_delta(proceeds)
        position.closed_at = stamp
        position.exit_premium_usd = round(float(exit_mark_usd), 2)
        position.mark_usd = round(float(exit_mark_usd), 2)
        position.realized_pnl_usd = realized
        position.status = "closed"
        position.notes = position.notes + (f"closed:{reason}",)
        self._fills.append(fill)
        self.record(
            JournalEntry(
                recorded_at=stamp,
                symbol=position.symbol,
                strategy=position.strategy,
                side="sell_to_close",
                source="paper_close",
                net_pnl_usd=realized,
                notes=fill.notes,
                position_id=position.position_id,
                fill_id=fill_id,
            )
        )
        return PaperActionResult(
            accepted=True,
            action="paper_close",
            reason="paper_fill_simulated",
            recommendation="stand_aside",
            position_id=position.position_id,
            fill_id=fill_id,
            cash_usd=self._cash_usd,
            notes=fill.notes,
            extra={
                "realized_pnl_usd": realized,
                "account": self.account_snapshot(now=stamp).to_dict(),
            },
        )

    def _open_blockers(
        self,
        package: DecisionPackage | None,
        *,
        quantity: int,
        now: datetime,
    ) -> tuple[str, tuple[str, ...]] | None:
        if quantity < 1:
            return "invalid_quantity", ("Quantity must be >= 1.",)
        if self.risk.emergency_stop:
            return "emergency_stop", ("EMERGENCY_STOP is enabled — paper opens refused.",)
        if package is None:
            return "no_decision_package", ("No Decision Package to journal. Stand aside.",)
        if package.incomplete_research or package.missing_required:
            missing = ", ".join(package.missing_required) or "required dimensions"
            return (
                "incomplete_research",
                (
                    f"incomplete_research=true ({missing}). Stand aside — no paper open.",
                    "Prefer stand aside until catalyst, fundamentals, and a long-premium option exist.",
                ),
            )
        if package.recommendation not in OPENABLE_RECOMMENDATIONS:
            return (
                "not_a_candidate",
                (
                    f"recommendation={package.recommendation} is not paper-openable. Stand aside.",
                    "Only complete candidate Decision Packages may be simulated.",
                ),
            )
        option = package.option_candidate
        if option is None:
            return "missing_option", ("No long-premium contract on the package. Stand aside.",)
        if option.strategy not in LONG_PREMIUM:
            return (
                "not_long_premium",
                (f"strategy={option.strategy} is forbidden on the paper ledger.",),
            )
        debit = round(float(option.max_loss_usd) * quantity, 2)
        if debit <= 0:
            return "invalid_debit", ("Debit must be positive for a long-premium paper fill.",)
        if debit - self.risk.max_risk_per_trade_usd > 1e-9:
            return (
                "risk_per_trade_cap",
                (
                    f"Debit ${debit:.2f} exceeds max risk/trade "
                    f"${self.risk.max_risk_per_trade_usd:.2f}.",
                ),
            )
        if debit - self._cash_usd > 1e-9:
            return (
                "insufficient_cash",
                (
                    f"Debit ${debit:.2f} exceeds paper cash ${self._cash_usd:.2f}. "
                    "Cash cannot go negative.",
                ),
            )
        if len(self.open_positions()) >= self.risk.max_simultaneous_positions:
            return (
                "max_positions",
                (
                    f"Already {len(self.open_positions())} open paper positions "
                    f"(cap {self.risk.max_simultaneous_positions}).",
                ),
            )
        daily = self.period_pnl(now, days=1)
        if daily <= -self.risk.max_daily_loss_usd + 1e-9:
            return (
                "daily_loss_cap",
                (
                    f"Daily P&L ${daily:.2f} has hit the "
                    f"${self.risk.max_daily_loss_usd:.2f} daily loss cap.",
                ),
            )
        weekly = self.period_pnl(now, days=7)
        if weekly <= -self.risk.max_weekly_loss_usd + 1e-9:
            return (
                "weekly_loss_cap",
                (
                    f"Weekly P&L ${weekly:.2f} has hit the "
                    f"${self.risk.max_weekly_loss_usd:.2f} weekly loss cap.",
                ),
            )
        return None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "phase": "architecture_9_paper_journal",
            "phase9_complete": PHASE9_COMPLETE,
            "ledger": self.name,
            "path": str(self.path) if self.path is not None else None,
            "schema": LEDGER_SCHEMA,
            "entry_count": len(self._entries),
            "entries": [e.to_dict() for e in self._entries],
            "positions": [p.to_dict() for p in self._positions],
            "fills": [f.to_dict() for f in self._fills],
            "account": self.account_snapshot().to_dict(),
            "risk": {
                "account_equity_usd": self.risk.account_equity_usd,
                "max_risk_per_trade_usd": self.risk.max_risk_per_trade_usd,
                "max_simultaneous_positions": self.risk.max_simultaneous_positions,
                "max_daily_loss_usd": self.risk.max_daily_loss_usd,
                "max_weekly_loss_usd": self.risk.max_weekly_loss_usd,
                "emergency_stop": self.risk.emergency_stop,
            },
            "notes": [PHASE9_NOTE],
            "last_backtest": None if self._last_backtest is None else dict(self._last_backtest),
            "broker_order_placed": False,
            "paper_only": True,
        }
        payload.update(research_lock_fields(command="journal"))
        return payload
