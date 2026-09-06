"""Build a daily/weekly text report for Grok oversight (no UI, no broker GO)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from trading_system.research_lock import (
    RESEARCH_COMPLETE,
    is_paper_research_candidate,
    paper_research_candidate_flags,
)
from trading_system.report.types import ResearchReport

PHASE10_COMPLETE = True
PHASE10_NOTE = (
    "Phase 10 is a minimal daily/weekly text report for Grok oversight. "
    "It aggregates status, regime, decide stand_aside/candidate flags, "
    "the paper journal snapshot, and a backtest summary pointer. "
    "No dashboard UI. Sandbox/live execution adapters are not required. "
    "Never places a broker order."
)

_LOCK_LINES = (
    "RESEARCH_COMPLETE is a research-desk flag only.",
    "Sandbox execution adapter: deferred (not required for RESEARCH_COMPLETE).",
    "LIVE_EXECUTION_UNLOCKED: false — never auto-place broker orders.",
    "go_signal (broker GO): false.",
    "Prefer stand_aside when Decision Packages are incomplete.",
)


def _aware(now: datetime | None) -> datetime:
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        return stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def _safe(label: str, fn: Callable[[], Any]) -> Any:
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "section": label}


def _symbols(packages: list[dict[str, Any]], *, recommendation: str) -> list[str]:
    out: list[str] = []
    for pkg in packages:
        if pkg.get("recommendation") == recommendation:
            symbol = str(pkg.get("symbol") or "").upper()
            if symbol and symbol not in out:
                out.append(symbol)
    return out


def _csv(values: list[str]) -> str:
    return ", ".join(values) if values else "(none)"


def _excerpt_status(status: dict[str, Any]) -> dict[str, Any]:
    risk = status.get("risk") if isinstance(status.get("risk"), dict) else {}
    paper = status.get("paper_account") if isinstance(status.get("paper_account"), dict) else {}
    return {
        "phase": status.get("phase"),
        "mode": status.get("mode"),
        "emergency_stop": status.get("emergency_stop"),
        "market_data_provider": status.get("market_data_provider"),
        "broker_provider": status.get("broker_provider"),
        "catalyst_provider": status.get("catalyst_provider"),
        "fundamentals_provider": status.get("fundamentals_provider"),
        "paper_journal": status.get("paper_journal"),
        "phase9_complete": status.get("phase9_complete"),
        "phase10_complete": status.get("phase10_complete"),
        "backtester": status.get("backtester"),
        "webull_configured": status.get("webull_configured"),
        "risk": {
            "account_equity_usd": risk.get("account_equity_usd"),
            "max_risk_per_trade_usd": risk.get("max_risk_per_trade_usd"),
            "max_simultaneous_positions": risk.get("max_simultaneous_positions"),
        },
        "paper_cash_usd": paper.get("cash_usd"),
        "error": status.get("error"),
    }


def _excerpt_regime(regime: dict[str, Any]) -> dict[str, Any]:
    return {
        "benchmark": regime.get("benchmark"),
        "regime": regime.get("regime"),
        "confidence": regime.get("confidence"),
        "strategies_favored": regime.get("strategies_favored"),
        "error": regime.get("error"),
    }


def decide_flags_from_packages(packages: list[dict[str, Any]]) -> dict[str, Any]:
    incomplete = [str(p.get("symbol") or "").upper() for p in packages if p.get("incomplete_research")]
    incomplete = [s for s in incomplete if s]
    paper_candidates = [
        str(p.get("symbol") or "").upper()
        for p in packages
        if is_paper_research_candidate(p)
    ]
    paper_candidates = [s for s in paper_candidates if s]
    paper = paper_research_candidate_flags(packages)
    return {
        "package_count": len(packages),
        "incomplete_research_count": sum(1 for p in packages if p.get("incomplete_research")),
        "incomplete_research": incomplete,
        "stand_aside": _symbols(packages, recommendation="stand_aside"),
        "watch": _symbols(packages, recommendation="watch"),
        "reject": _symbols(packages, recommendation="reject"),
        "candidates_paper_research": paper_candidates,
        "prefer_stand_aside": bool(incomplete) or not paper_candidates,
        "trade_recommendation": paper,
        "go_signals_allowed": paper,
        "go_signal": False,
        "broker_go_allowed": False,
    }


def _journal_snapshot(journal: dict[str, Any], *, weekly: bool, now: datetime) -> dict[str, Any]:
    account = journal.get("account") if isinstance(journal.get("account"), dict) else {}
    entries = [e for e in (journal.get("entries") or []) if isinstance(e, dict)]
    fills = [f for f in (journal.get("fills") or []) if isinstance(f, dict)]
    positions = [p for p in (journal.get("positions") or []) if isinstance(p, dict)]
    cutoff = now - timedelta(days=7) if weekly else None

    def _after(raw: str | None) -> bool:
        if cutoff is None or not raw:
            return True
        try:
            stamp = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            return True
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return stamp >= cutoff

    recent_entries = [e for e in entries if _after(e.get("recorded_at"))]
    recent_fills = [f for f in fills if _after(f.get("filled_at"))]
    return {
        "ledger": journal.get("ledger"),
        "phase9_complete": journal.get("phase9_complete"),
        "account": {
            "cash_usd": account.get("cash_usd"),
            "equity_usd": account.get("equity_usd"),
            "realized_pnl_usd": account.get("realized_pnl_usd"),
            "unrealized_pnl_usd": account.get("unrealized_pnl_usd"),
            "daily_pnl_usd": account.get("daily_pnl_usd"),
            "weekly_pnl_usd": account.get("weekly_pnl_usd"),
            "open_position_count": account.get("open_position_count"),
            "closed_position_count": account.get("closed_position_count"),
        },
        "open_symbols": [
            str(p.get("symbol") or "").upper()
            for p in positions
            if p.get("status") == "open" and p.get("symbol")
        ],
        "entry_count": len(entries),
        "recent_entry_count": len(recent_entries),
        "recent_fill_count": len(recent_fills),
        "recent_notes": [
            str(e.get("notes") or e.get("symbol") or "")
            for e in recent_entries
            if e.get("source") == "paper_note"
        ][:8],
        "error": journal.get("error"),
    }


def _backtest_pointer(journal: dict[str, Any], *, weekly: bool, now: datetime) -> dict[str, Any]:
    stored = journal.get("last_backtest")
    if isinstance(stored, dict) and stored.get("symbol"):
        pointer = dict(stored)
        pointer.setdefault("available", True)
        pointer.setdefault(
            "cli",
            f"python -m trading_system backtest {stored.get('symbol')} "
            f"--split {stored.get('split_mode') or 'oos'}",
        )
        pointer.setdefault("note", "synthetic long-premium; not historical OPRA")
        return pointer

    entries = [e for e in (journal.get("entries") or []) if isinstance(e, dict)]
    rows = [e for e in entries if e.get("source") == "backtest"]
    if weekly:
        cutoff = now - timedelta(days=7)

        def _recent(raw: str | None) -> bool:
            if not raw:
                return False
            try:
                stamp = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            except ValueError:
                return False
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            return stamp >= cutoff

        rows = [e for e in rows if _recent(e.get("recorded_at"))]
    if not rows:
        return {
            "available": False,
            "cli": "python -m trading_system backtest SPY --split oos",
            "note": (
                "No backtest annotations in the paper journal. "
                "Phase 7 is a synthetic long-premium mark (not historical OPRA)."
            ),
        }
    pnl = 0.0
    symbols: list[str] = []
    for row in rows:
        symbol = str(row.get("symbol") or "").upper()
        if symbol and symbol not in symbols:
            symbols.append(symbol)
        value = row.get("net_pnl_usd")
        if isinstance(value, (int, float)):
            pnl += float(value)
    return {
        "available": True,
        "symbols": symbols,
        "annotation_count": len(rows),
        "net_pnl_usd": round(pnl, 2),
        "cli": "python -m trading_system backtest SPY --split oos",
        "note": "Derived from journal backtest annotations; synthetic mark, not historical OPRA.",
    }


def _format_kv(title: str, rows: list[tuple[str, Any]]) -> list[str]:
    lines = [title, "-" * len(title)]
    for key, value in rows:
        if isinstance(value, list):
            rendered = _csv([str(v) for v in value])
        elif isinstance(value, bool):
            rendered = "true" if value else "false"
        elif value is None:
            rendered = "n/a"
        else:
            rendered = str(value)
        lines.append(f"{key}: {rendered}")
    lines.append("")
    return lines


def render_text(
    *,
    as_of: datetime,
    period: str,
    status: dict[str, Any],
    regime: dict[str, Any],
    flags: dict[str, Any],
    journal_snapshot: dict[str, Any],
    backtest_pointer: dict[str, Any],
    notes: tuple[str, ...],
) -> str:
    heading = f"TRADING SYSTEM — {period.upper()} RESEARCH REPORT"
    account = journal_snapshot.get("account") if isinstance(journal_snapshot.get("account"), dict) else {}
    lines = [
        "=" * 72,
        heading,
        "=" * 72,
        f"as_of: {as_of.astimezone(timezone.utc).isoformat()}",
        f"research_complete: {'true' if RESEARCH_COMPLETE else 'false'}",
        "live_execution_unlocked: false",
        "broker_go_allowed: false",
        "go_signal: false",
        f"prefer_stand_aside: {'true' if flags.get('prefer_stand_aside') else 'false'}",
        "",
    ]
    lines += _format_kv(
        "STATUS",
        [
            ("phase", status.get("phase")),
            ("mode", status.get("mode")),
            ("emergency_stop", status.get("emergency_stop")),
            ("market_data_provider", status.get("market_data_provider")),
            ("catalyst_provider", status.get("catalyst_provider")),
            ("fundamentals_provider", status.get("fundamentals_provider")),
            ("paper_journal", status.get("paper_journal")),
            ("phase9_complete", status.get("phase9_complete")),
            ("phase10_complete", status.get("phase10_complete")),
            ("backtester", status.get("backtester")),
            ("webull_configured", status.get("webull_configured")),
        ],
    )
    lines += _format_kv(
        "REGIME",
        [
            ("benchmark", regime.get("benchmark")),
            ("regime", regime.get("regime")),
            ("confidence", regime.get("confidence")),
            ("strategies_favored", regime.get("strategies_favored")),
            ("error", regime.get("error")),
        ],
    )
    lines += _format_kv(
        "DECIDE (paper/research only — never a broker GO)",
        [
            ("package_count", flags.get("package_count")),
            ("incomplete_research_count", flags.get("incomplete_research_count")),
            ("incomplete_research", flags.get("incomplete_research")),
            ("stand_aside", flags.get("stand_aside")),
            ("watch", flags.get("watch")),
            ("reject", flags.get("reject")),
            ("candidates_paper_research", flags.get("candidates_paper_research")),
            ("trade_recommendation", flags.get("trade_recommendation")),
            ("go_signals_allowed", flags.get("go_signals_allowed")),
            ("go_signal", False),
            ("prefer_stand_aside", flags.get("prefer_stand_aside")),
        ],
    )
    lines += _format_kv(
        "PAPER JOURNAL",
        [
            ("ledger", journal_snapshot.get("ledger")),
            ("cash_usd", account.get("cash_usd")),
            ("equity_usd", account.get("equity_usd")),
            ("realized_pnl_usd", account.get("realized_pnl_usd")),
            ("unrealized_pnl_usd", account.get("unrealized_pnl_usd")),
            ("daily_pnl_usd", account.get("daily_pnl_usd")),
            ("weekly_pnl_usd", account.get("weekly_pnl_usd")),
            ("open_position_count", account.get("open_position_count")),
            ("open_symbols", journal_snapshot.get("open_symbols")),
            ("entry_count", journal_snapshot.get("entry_count")),
            ("recent_entry_count", journal_snapshot.get("recent_entry_count")),
            ("recent_fill_count", journal_snapshot.get("recent_fill_count")),
        ],
    )
    lines += _format_kv(
        "BACKTEST POINTER",
        [
            ("available", backtest_pointer.get("available")),
            ("symbol", backtest_pointer.get("symbol")),
            ("symbols", backtest_pointer.get("symbols")),
            ("setup", backtest_pointer.get("setup")),
            ("split_mode", backtest_pointer.get("split_mode")),
            ("trade_count", backtest_pointer.get("trade_count") or backtest_pointer.get("annotation_count")),
            ("net_pnl_usd", backtest_pointer.get("net_pnl_usd")),
            ("cli", backtest_pointer.get("cli")),
            ("note", backtest_pointer.get("note")),
        ],
    )
    lines += ["LOCK", "----"]
    lines.extend(f"- {line}" for line in _LOCK_LINES)
    if notes:
        lines.append("")
        lines.append("NOTES")
        lines.append("-----")
        lines.extend(f"- {note}" for note in notes)
    lines.append("=" * 72)
    return "\n".join(lines) + "\n"


class ResearchReportBuilder:
    """Assemble the Phase 10 text report from existing research surfaces."""

    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime

    def build(
        self,
        *,
        weekly: bool = False,
        benchmark: str = "SPY",
        lookback: int = 90,
        min_equity_score: float = 55.0,
        min_option_score: float = 55.0,
        max_results: int = 10,
        symbols: list[str] | None = None,
        now: datetime | None = None,
    ) -> ResearchReport:
        as_of = _aware(now)
        period = "weekly" if weekly else "daily"
        notes = [
            PHASE10_NOTE,
            "Prefer stand_aside when packages are incomplete.",
            "trade_recommendation / go_signals_allowed apply to paper/research candidates only.",
        ]
        if weekly:
            notes.append("Weekly window: journal P&L, fills, notes, and backtest annotations over 7 days.")

        raw_status = _safe("status", self.runtime.status)
        raw_regime = _safe(
            "regime",
            lambda: self.runtime.market_regime(benchmark=benchmark, lookback=lookback),
        )
        raw_decide = _safe(
            "decide",
            lambda: self.runtime.decide(
                benchmark=benchmark,
                lookback=lookback,
                min_equity_score=min_equity_score,
                min_option_score=min_option_score,
                max_results=max_results,
                symbols=symbols,
            ),
        )
        raw_journal = _safe("journal", self.runtime.journal)

        if isinstance(raw_status, dict) and raw_status.get("error"):
            notes.append(f"status error: {raw_status['error']}")
        if isinstance(raw_regime, dict) and raw_regime.get("error"):
            notes.append(f"regime error: {raw_regime['error']}")
        if isinstance(raw_decide, dict) and raw_decide.get("error"):
            notes.append(f"decide error: {raw_decide['error']}")
        if isinstance(raw_journal, dict) and raw_journal.get("error"):
            notes.append(f"journal error: {raw_journal['error']}")

        packages = []
        if isinstance(raw_decide, dict):
            packages = [p for p in (raw_decide.get("packages") or []) if isinstance(p, dict)]
        flags = decide_flags_from_packages(packages)
        status = _excerpt_status(raw_status if isinstance(raw_status, dict) else {"error": "status unavailable"})
        regime = _excerpt_regime(raw_regime if isinstance(raw_regime, dict) else {"error": "regime unavailable"})
        journal_snapshot = _journal_snapshot(
            raw_journal if isinstance(raw_journal, dict) else {"error": "journal unavailable"},
            weekly=weekly,
            now=as_of,
        )
        backtest_pointer = _backtest_pointer(
            raw_journal if isinstance(raw_journal, dict) else {},
            weekly=weekly,
            now=as_of,
        )
        text = render_text(
            as_of=as_of,
            period=period,
            status=status,
            regime=regime,
            flags=flags,
            journal_snapshot=journal_snapshot,
            backtest_pointer=backtest_pointer,
            notes=tuple(notes),
        )
        return ResearchReport(
            as_of=as_of,
            period=period,
            text=text,
            status=status,
            regime=regime,
            decide_flags=flags,
            journal_snapshot=journal_snapshot,
            backtest_pointer=backtest_pointer,
            packages=tuple(packages),
            notes=tuple(notes),
        )
