"""Deterministic catalyst score from documented event proximity only."""

from __future__ import annotations

from datetime import date

from trading_system.events.types import CatalystSnapshot, EarningsEvent, FilingNote


def score_catalyst(
    *,
    available: bool,
    earnings_date: date | None,
    days_to_earnings: int | None,
    earnings_status: str,
) -> float | None:
    """Return 0–100 or None when the catalyst calendar is unavailable.

    Long-premium RESEARCH prefers a known date that is not inside the
    binary-event / IV-crush window. Missing data is None, not a fake 50.
    """
    if not available or earnings_status == "unavailable":
        return None
    if earnings_status == "not_applicable":
        return 55.0
    if earnings_date is None or days_to_earnings is None:
        return 40.0 if earnings_status == "published" else None
    dte = days_to_earnings
    if dte < 0:
        return 50.0
    if dte <= 2:
        return 10.0
    if dte <= 7:
        return 25.0
    if dte <= 13:
        return 45.0
    if 14 <= dte <= 45:
        return 78.0
    if dte <= 90:
        return 62.0
    return 50.0


def event_flags(
    *,
    available: bool,
    earnings_status: str,
    days_to_earnings: int | None,
    filings: tuple[FilingNote, ...] | list[FilingNote],
    as_of: date,
) -> tuple[str, ...]:
    flags: list[str] = []
    if not available or earnings_status in {"unavailable", "unknown"}:
        flags.append("earnings_date_unknown")
    if earnings_status == "not_applicable":
        flags.append("etf_or_no_earnings_calendar")
    if days_to_earnings is not None:
        if 0 <= days_to_earnings <= 2:
            flags.append("earnings_within_2d")
        if 0 <= days_to_earnings <= 7:
            flags.append("earnings_within_7d")
        if 0 <= days_to_earnings <= 21:
            flags.append("earnings_within_21d")
        if days_to_earnings > 21:
            flags.append("earnings_outside_21d")
    for filing in filings:
        if filing.publish_date is None:
            continue
        age = (as_of - filing.publish_date).days
        if age < 0 or age > 7:
            continue
        hint = (filing.form_hint or "").upper().replace("-", "")
        if hint in {"8K"}:
            flags.append("recent_8k")
        elif hint in {"10Q"}:
            flags.append("recent_10q")
        elif hint in {"10K"}:
            flags.append("recent_10k")
    # Preserve order, unique.
    seen: set[str] = set()
    out: list[str] = []
    for flag in flags:
        if flag not in seen:
            seen.add(flag)
            out.append(flag)
    return tuple(out)


def snapshot_from_events(
    symbol: str,
    *,
    source: str,
    as_of: date,
    earnings: list[EarningsEvent],
    filings: list[FilingNote],
    notes: list[str],
    available: bool,
    earnings_status_override: str | None = None,
    raw_error: str = "",
) -> CatalystSnapshot:
    from trading_system.events.parse import next_upcoming_earnings

    nxt = next_upcoming_earnings(earnings, as_of=as_of)
    earnings_date = nxt.expected_publish_date if nxt else None
    days = (earnings_date - as_of).days if earnings_date else None
    if earnings_status_override:
        status = earnings_status_override
    elif nxt:
        status = "upcoming"
    elif earnings:
        status = "published"
    elif available:
        status = "unknown"
    else:
        status = "unavailable"
    flags = event_flags(
        available=available,
        earnings_status=status,
        days_to_earnings=days,
        filings=filings,
        as_of=as_of,
    )
    score = score_catalyst(
        available=available,
        earnings_date=earnings_date,
        days_to_earnings=days,
        earnings_status=status,
    )
    return CatalystSnapshot(
        symbol=symbol.upper(),
        available=available,
        source=source,
        earnings_date=earnings_date,
        days_to_earnings=days,
        earnings_status=status,
        event_flags=flags,
        earnings_events=tuple(earnings),
        filings=tuple(filings),
        score=score,
        notes=tuple(notes),
        raw_error=raw_error,
    )
