"""Fundamentals snapshot. Official EPS + statements/ratios only — no invented metrics."""

from __future__ import annotations

from dataclasses import dataclass, field
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
class IndicatorPoint:
    name: str
    fiscal_year: int | None
    fiscal_period: int | None
    value: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "fiscal_year": self.fiscal_year,
            "fiscal_period": self.fiscal_period,
            "value": self.value,
        }


@dataclass(frozen=True)
class StatementPeriod:
    kind: str  # income | cashflow | balance
    fiscal_year: int | None
    fiscal_period: int | None
    end_date: str | None
    publish_date: str | None
    currency: str | None
    fields: dict[str, float | None] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "fiscal_year": self.fiscal_year,
            "fiscal_period": self.fiscal_period,
            "end_date": self.end_date,
            "publish_date": self.publish_date,
            "currency": self.currency,
            "fields": dict(self.fields),
        }


@dataclass(frozen=True)
class IndustryPeer:
    symbol: str
    name: str
    rank: int | None
    value: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "rank": self.rank,
            "value": self.value,
        }


@dataclass(frozen=True)
class IndustryComparison:
    available: bool
    industry_name: str = ""
    metric: str = ""
    fiscal_year: int | None = None
    fiscal_period: int | None = None
    peers: tuple[IndustryPeer, ...] = ()
    self_rank: int | None = None
    self_value: float | None = None
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "industry_name": self.industry_name,
            "metric": self.metric,
            "fiscal_year": self.fiscal_year,
            "fiscal_period": self.fiscal_period,
            "self_rank": self.self_rank,
            "self_value": self.self_value,
            "peers": [p.to_dict() for p in self.peers],
            "notes": list(self.notes),
        }


# Official indicator keys from GET /openapi/fundamentals/financial/indicators
OFFICIAL_INDICATOR_KEYS: tuple[str, ...] = (
    "roa",
    "roe",
    "diluted_eps_incl_extra",
    "net_margin",
    "debt_to_assets",
    "naps",
    "ocf_ps",
    "cap_surplus_ps",
)

# Official income fields we surface (GET /openapi/fundamentals/financial/income)
INCOME_FIELD_KEYS: tuple[str, ...] = (
    "total_revenue",
    "revenue",
    "gross_profit",
    "op_income",
    "net_income",
    "diluted_eps_incl_extra",
)

# Official cash-flow fields we surface (GET /openapi/fundamentals/financial/cash-flow)
CASHFLOW_FIELD_KEYS: tuple[str, ...] = (
    "cfo",
    "capex",
    "net_change_cash",
    "net_income",
)

# Official balance-sheet fields we surface (GET /openapi/fundamentals/financial/balance-sheet)
BALANCE_FIELD_KEYS: tuple[str, ...] = (
    "total_assets",
    "cash",
    "total_liab",
    "total_debt",
    "total_equity",
)


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
    # Richer official slices (empty when the SDK/API path is unavailable)
    statements_status: str = "unavailable"  # unavailable | partial | present | not_applicable
    latest_indicators: dict[str, float | None] = field(default_factory=dict)
    indicator_points: tuple[IndicatorPoint, ...] = ()
    income: StatementPeriod | None = None
    cashflow: StatementPeriod | None = None
    balance: StatementPeriod | None = None
    industry: IndustryComparison | None = None
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
            "statements_status": self.statements_status,
            "latest_indicators": dict(self.latest_indicators),
            "indicator_points": [p.to_dict() for p in self.indicator_points],
            "income": None if self.income is None else self.income.to_dict(),
            "cashflow": None if self.cashflow is None else self.cashflow.to_dict(),
            "balance": None if self.balance is None else self.balance.to_dict(),
            "industry": None if self.industry is None else self.industry.to_dict(),
            "notes": list(self.notes),
            "raw_error": self.raw_error,
        }


@dataclass(frozen=True)
class FundamentalsFixture:
    latest_actual_eps: float | None = None
    latest_estimate_eps: float | None = None
    beat_miss: str = "unknown"
    notes: tuple[str, ...] = ()
    latest_indicators: dict[str, float | None] | None = None
    income: StatementPeriod | None = None
    cashflow: StatementPeriod | None = None
    balance: StatementPeriod | None = None
    industry: IndustryComparison | None = None
    statements_status: str = "unavailable"
