"""Normalized catalyst / news-event types. No invented headlines."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True)
class FilingNote:
    """A documented SEC filing (title/url/date only — no generated news)."""

    title: str
    publish_date: date | None
    url: str = ""
    form_hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "publish_date": self.publish_date.isoformat() if self.publish_date else None,
            "url": self.url,
            "form_hint": self.form_hint,
        }


@dataclass(frozen=True)
class EarningsEvent:
    expected_publish_date: date | None
    eps_actual: float | None
    eps_estimate: float | None
    fiscal_year: int | None = None
    fiscal_period: int | None = None
    status: str = "unknown"  # upcoming | published | unknown

    def to_dict(self) -> dict[str, Any]:
        return {
            "expected_publish_date": (
                self.expected_publish_date.isoformat() if self.expected_publish_date else None
            ),
            "eps_actual": self.eps_actual,
            "eps_estimate": self.eps_estimate,
            "fiscal_year": self.fiscal_year,
            "fiscal_period": self.fiscal_period,
            "status": self.status,
        }


@dataclass(frozen=True)
class CatalystSnapshot:
    """Auditable catalyst view. Missing data is explicit, never fabricated."""

    symbol: str
    available: bool
    source: str
    earnings_date: date | None = None
    days_to_earnings: int | None = None
    earnings_status: str = "unavailable"  # upcoming | published | unknown | unavailable | not_applicable
    event_flags: tuple[str, ...] = ()
    earnings_events: tuple[EarningsEvent, ...] = ()
    filings: tuple[FilingNote, ...] = ()
    score: float | None = None
    notes: tuple[str, ...] = ()
    raw_error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "available": self.available,
            "source": self.source,
            "earnings_date": self.earnings_date.isoformat() if self.earnings_date else None,
            "days_to_earnings": self.days_to_earnings,
            "earnings_status": self.earnings_status,
            "event_flags": list(self.event_flags),
            "earnings_events": [e.to_dict() for e in self.earnings_events],
            "filings": [f.to_dict() for f in self.filings],
            "score": None if self.score is None else round(self.score, 2),
            "notes": list(self.notes),
            "raw_error": self.raw_error,
        }


@dataclass(frozen=True)
class CatalystFixture:
    """Test/operator injection of a known earnings date — never used as live news."""

    earnings_date: date | None = None
    earnings_status: str = "upcoming"
    filings: tuple[FilingNote, ...] = field(default_factory=tuple)
    notes: tuple[str, ...] = ()
