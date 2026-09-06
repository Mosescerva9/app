"""Product lock: research-complete is not a live GO and never unlocks the broker."""

from __future__ import annotations

from typing import Any, Iterable

from trading_system.modes import LIVE_EXECUTION_UNLOCKED

# System-level RESEARCH_COMPLETE is true when the research-desk checklist
# (items 1–7 through paper journal, plus the Phase 10 text report CLI) is
# honestly present. Sandbox execution and LIVE unlock are post-research gates
# and are not required for this flag. Broker GO stays forbidden.
RESEARCH_COMPLETE = True
# Blanket broker GO remains off. Paper/research candidate flags are computed
# per decide/report payload when a complete candidate exists.
GO_SIGNALS_ALLOWED = False

RESEARCH_LOCK_NOTE = (
    "RESEARCH_COMPLETE is a research-desk flag, not a live unlock. "
    "Required Decision Package dimensions: regime/equity scores, long-premium option, "
    "official catalyst (or ETF not_applicable), official fundamentals "
    "(forecast-EPS and/or statements/indicators, or ETF not_applicable), "
    "adversarial critique. Missing/unavailable dimensions force stand_aside + "
    "incomplete_research. trade_recommendation / go_signals_allowed may be true "
    "only for paper/research candidates. go_signal (broker GO) stays false. "
    "LIVE_EXECUTION_UNLOCKED stays false. Sandbox/live adapters are deferred and "
    "are not required for RESEARCH_COMPLETE. Phase 7 backtester is a synthetic "
    "long-premium mark (not historical OPRA). Phase 9 paper journal is a simulated "
    "ledger (no broker orders). Phase 10 is a text daily/weekly report CLI."
)


def research_complete_checklist() -> dict[str, Any]:
    """Honest checklist snapshot. Sandbox/LIVE remain post-research."""
    return {
        "regime_and_equity_scores": True,
        "long_premium_options_engine": True,
        "catalyst": True,
        "fundamentals": True,
        "adversarial_critique": True,
        "backtester_minimal_synthetic": True,
        "historical_opra_backtest": False,
        "paper_journal_loop": True,
        "daily_weekly_text_report": True,
        "dashboard_ui": False,
        "sandbox_execution_adapter": False,
        "live_approval_unlock": False,
    }


def is_paper_research_candidate(package: Any) -> bool:
    """Complete candidate only — never a broker GO."""
    if package is None:
        return False
    if isinstance(package, dict):
        recommendation = package.get("recommendation")
        incomplete = bool(package.get("incomplete_research", True))
    else:
        recommendation = getattr(package, "recommendation", None)
        incomplete = bool(getattr(package, "incomplete_research", True))
    return recommendation == "candidate" and not incomplete


def paper_research_candidate_flags(packages: Iterable[Any] | None) -> bool:
    if not RESEARCH_COMPLETE:
        return False
    for package in packages or ():
        if is_paper_research_candidate(package):
            return True
    return False


def research_lock_fields(
    *,
    command: str = "",
    paper_research_candidates: bool = False,
) -> dict[str, Any]:
    paper = bool(RESEARCH_COMPLETE and paper_research_candidates)
    payload: dict[str, Any] = {
        "research_complete": RESEARCH_COMPLETE,
        "go_signals_allowed": paper,
        "trade_recommendation": paper,
        "live_execution_unlocked": LIVE_EXECUTION_UNLOCKED,
        "broker_go_allowed": False,
        "paper_research_only": True,
        "research_lock_note": RESEARCH_LOCK_NOTE,
        "research_complete_checklist": research_complete_checklist(),
    }
    if command:
        payload["research_command"] = command
    return payload


def stamp_research_lock(payload: dict[str, Any], *, command: str) -> dict[str, Any]:
    """Overlay lock fields on CLI JSON. Never upgrades a broker GO."""
    packages = payload.get("packages")
    if not packages:
        decide = payload.get("decide")
        if isinstance(decide, dict):
            packages = decide.get("packages")
    paper = paper_research_candidate_flags(packages if isinstance(packages, (list, tuple)) else None)
    locked = research_lock_fields(command=command, paper_research_candidates=paper)
    out = dict(payload)
    out.update(locked)
    out["go_signal"] = False
    return out
