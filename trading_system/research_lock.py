"""Product lock: partial TA/options is never a trade recommendation or GO."""

from __future__ import annotations

from typing import Any

from trading_system.modes import LIVE_EXECUTION_UNLOCKED

# System-level RESEARCH_COMPLETE stays false until the documented checklist
# is honestly met (paper journal exists; dashboard/Grok brief and historical
# OPRA still missing). Package-level completeness only lifts
# incomplete_research on that row — it still does not authorize a GO.
RESEARCH_COMPLETE = False
GO_SIGNALS_ALLOWED = False

RESEARCH_LOCK_NOTE = (
    "Partial TA/options is not RESEARCH_COMPLETE and is not a trade recommendation. "
    "Required Decision Package dimensions: regime/equity scores, long-premium option, "
    "official catalyst (or ETF not_applicable), official fundamentals "
    "(forecast-EPS and/or statements/indicators, or ETF not_applicable), "
    "adversarial critique. Missing/unavailable dimensions force stand_aside + "
    "incomplete_research. Live execution stays locked. "
    "Phase 7 backtester exists (synthetic long-premium, OOS/walk-forward; not historical OPRA). "
    "Phase 9 paper journal is a real simulated ledger (no broker orders). "
    "Dashboard/Grok brief is still deferred. RESEARCH_COMPLETE remains false."
)


def research_complete_checklist() -> dict[str, Any]:
    """Honest checklist snapshot. Does not flip RESEARCH_COMPLETE."""
    return {
        "regime_and_equity_scores": True,
        "long_premium_options_engine": True,
        "catalyst": True,
        "fundamentals": True,
        "adversarial_critique": True,
        "backtester_minimal_synthetic": True,
        "historical_opra_backtest": False,
        "paper_journal_loop": True,
        "dashboard_grok_brief": False,
        "sandbox_execution_adapter": False,
        "live_approval_unlock": False,
    }


def research_lock_fields(*, command: str = "") -> dict[str, Any]:
    payload: dict[str, Any] = {
        "research_complete": RESEARCH_COMPLETE,
        "go_signals_allowed": GO_SIGNALS_ALLOWED,
        "trade_recommendation": False,
        "live_execution_unlocked": LIVE_EXECUTION_UNLOCKED,
        "research_lock_note": RESEARCH_LOCK_NOTE,
        "research_complete_checklist": research_complete_checklist(),
    }
    if command:
        payload["research_command"] = command
    return payload


def stamp_research_lock(payload: dict[str, Any], *, command: str) -> dict[str, Any]:
    """Overlay lock fields on CLI JSON. Never upgrades a GO."""
    locked = research_lock_fields(command=command)
    out = dict(payload)
    out.update(locked)
    return out
