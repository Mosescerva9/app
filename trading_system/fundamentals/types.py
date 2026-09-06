"""Minimal fundamentals snapshot. Official EPS rows only — no invented metrics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EpsRow:
    fiscal_year: int | None
    fiscal_period: int | None
    actual: float | None
    estimate: float | None
    reported: bool | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "fiscal_year": self.fiscal_year,
            "fiscal_period": self.fiscal_period,
            "actual": self.actual,
            "estimate": self.estimate,
            "reported": self.reported,
        }


@dataclass(frozen=True)
class FundamentalsSnapshot:
    symbol: str
    available: bool
    source: str
    score: float | None = None
    latest_actual_eps: float | None = None
    latest_estimate_eps: float | None = None
    beat_miss: str = "unavailable"  # beat | miss | inline | unknown | unavailable | not_applicable
    rows: tuple[EpsRow, ...] = ()
    notes: tuple[str, ...] = ()
    raw_error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "available": self.available,
            "source": self.source,
            "score": None if self.score is None else round(self.score, 2),
            "latest_actual_eps": self.latest_actual_eps,
            "latest_estimate_eps": self.latest_estimate_eps,
            "beat_miss": self.beat_miss,
            "rows": [r.to_dict() for r in self.rows],
            "notes": list(self.notes),
            "raw_error": self.raw_error,
        }


@dataclass(frozen=True)
class FundamentalsFixture:
    latest_actual_eps: float | None = None
    latest_estimate_eps: float | None = None
    beat_miss: str = "unknown"
    notes: tuple[str, ...] = ()
