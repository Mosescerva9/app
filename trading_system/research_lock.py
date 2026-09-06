"""Product lock: partial TA/options is never a trade recommendation or GO."""

from __future__ import annotations

from typing import Any

from trading_system.modes import LIVE_EXECUTION_UNLOCKED

# System-level RESEARCH_COMPLETE stays false until backtester + paper journal
# exist. Package-level completeness (catalyst + fundamentals + option) only
# lifts incomplete_research on that row — it still does not authorize a GO.
RESEARCH_COMPLETE = False
GO_SIGNALS_ALLOWED = False

RESEARCH_LOCK_NOTE = (
    "Partial TA/options is not RESEARCH_COMPLETE and is not a trade recommendation. "
    "Required Decision Package dimensions: regime/equity scores, long-premium option, "
    "official catalyst (or ETF not_applicable), official fundamentals/forecast-EPS "
    "(or ETF not_applicable), adversarial critique. Missing/unavailable dimensions "
    "force stand_aside + incomplete_research. Live execution stays locked. "
    "Still deferred: full statements, backtester, paper journal, live exec."
)


def research_lock_fields(*, command: str = "") -> dict[str, Any]:
    payload: dict[str, Any] = {
        "research_complete": RESEARCH_COMPLETE,
        "go_signals_allowed": GO_SIGNALS_ALLOWED,
        "trade_recommendation": False,
        "live_execution_unlocked": LIVE_EXECUTION_UNLOCKED,
        "research_lock_note": RESEARCH_LOCK_NOTE,
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
