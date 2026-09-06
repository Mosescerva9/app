"""Defensive parsers for official Webull fundamentals payloads.

Field names come from the official Java SDK domain objects and the Python
SDK docstring (eps_actual distinguishes published vs upcoming):

- EarningsCalendar: expectedPublishDate, epsActual, epsEst, fiscalYear, fiscalPeriod
- SecFilingItem: title, url, publishDate
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any

from trading_system.events.types import EarningsEvent, FilingNote
from trading_system.models import ms_to_datetime, to_float
from trading_system.webull_support import as_record_list

_FORM_HINTS = ("8-K", "8K", "10-Q", "10Q", "10-K", "10K", "6-K", "6K", "S-1", "S1", "13F")


def first_value(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def parse_iso_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit() or (text.replace(".", "", 1).isdigit() and "." in text):
        try:
            return ms_to_datetime(value).date()
        except (TypeError, ValueError, OSError):
            return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(text[:10] if fmt != "%Y%m%d" else text[:8], fmt).date()
        except ValueError:
            continue
    return None


def form_hint_from_title(title: str) -> str:
    upper = (title or "").upper()
    for token in _FORM_HINTS:
        pattern = token.replace("-", r"[\s-]?")
        if re.search(rf"\b{pattern}\b", upper):
            return token.replace(" ", "")
    return ""


def parse_earnings_rows(payload: Any) -> list[EarningsEvent]:
    rows = as_record_list(payload, ("data", "result", "items", "list", "earnings", "calendar"))
    if not rows and isinstance(payload, dict):
        # Single-object envelope.
        if first_value(payload, "expected_publish_date", "expectedPublishDate") is not None:
            rows = [payload]
    out: list[EarningsEvent] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        publish = parse_iso_date(
            first_value(
                row,
                "expected_publish_date",
                "expectedPublishDate",
                "report_date",
                "reportDate",
                "date",
            )
        )
        eps_actual = to_float(first_value(row, "eps_actual", "epsActual", "eps"))
        eps_est = to_float(first_value(row, "eps_est", "epsEst", "eps_estimate", "epsEstimate"))
        fy = first_value(row, "fiscal_year", "fiscalYear")
        fp = first_value(row, "fiscal_period", "fiscalPeriod")
        try:
            fiscal_year = int(fy) if fy is not None else None
        except (TypeError, ValueError):
            fiscal_year = None
        try:
            fiscal_period = int(fp) if fp is not None else None
        except (TypeError, ValueError):
            fiscal_period = None
        # Official SDK: eps_actual present → published; absent → upcoming.
        if eps_actual is not None:
            status = "published"
        elif publish is not None:
            status = "upcoming"
        else:
            status = "unknown"
        out.append(
            EarningsEvent(
                expected_publish_date=publish,
                eps_actual=eps_actual,
                eps_estimate=eps_est,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                status=status,
            )
        )
    return out


def parse_filing_rows(payload: Any) -> list[FilingNote]:
    rows = as_record_list(payload, ("filings", "data", "result", "items", "list"))
    if isinstance(payload, dict) and isinstance(payload.get("filings"), dict):
        rows = as_record_list(payload["filings"], ("data", "result", "items", "list"))
    out: list[FilingNote] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = str(first_value(row, "title", "form", "formType", "form_type") or "").strip()
        url = str(first_value(row, "url", "link", "filingUrl") or "").strip()
        published = parse_iso_date(
            first_value(row, "publish_date", "publishDate", "filed_at", "filingDate", "date")
        )
        if not title and not published:
            continue
        out.append(
            FilingNote(
                title=title,
                publish_date=published,
                url=url,
                form_hint=form_hint_from_title(title),
            )
        )
    return out


def next_upcoming_earnings(
    events: list[EarningsEvent],
    *,
    as_of: date,
) -> EarningsEvent | None:
    upcoming = [
        e
        for e in events
        if e.status == "upcoming"
        and e.expected_publish_date is not None
        and e.expected_publish_date >= as_of
    ]
    upcoming.sort(key=lambda e: e.expected_publish_date or date.max)
    return upcoming[0] if upcoming else None


def days_between(start: date, end: date) -> int:
    return (end - start).days


def aware_utc(value: datetime | None) -> datetime:
    now = value or datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)
