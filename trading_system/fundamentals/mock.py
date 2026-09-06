"""Offline fundamentals provider. Does not invent financials."""

from __future__ import annotations

from datetime import datetime

from trading_system.fundamentals.base import FundamentalsProvider
from trading_system.fundamentals.parse import blend_fundamental_score
from trading_system.fundamentals.types import EpsRow, FundamentalsFixture, FundamentalsSnapshot


class MockFundamentalsProvider(FundamentalsProvider):
    name = "mock"

    def __init__(self, fixtures: dict[str, FundamentalsFixture] | None = None) -> None:
        self.fixtures = {k.upper(): v for k, v in (fixtures or {}).items()}

    def get_fundamentals(
        self,
        symbol: str,
        *,
        as_of: datetime | None = None,
    ) -> FundamentalsSnapshot:
        key = symbol.upper()
        fixture = self.fixtures.get(key)
        if fixture is None:
            return unavailable_fundamentals(
                key,
                source=self.name,
                note=(
                    "Fundamentals unavailable: mock provider does not invent EPS, "
                    "statements, ratios, or analyst numbers."
                ),
            )
        eps_score = (
            70.0
            if fixture.beat_miss == "beat"
            else 40.0
            if fixture.beat_miss == "miss"
            else 55.0
        )
        indicators = dict(fixture.latest_indicators or {})
        score = blend_fundamental_score(
            eps_score=eps_score,
            indicators=indicators,
            income=fixture.income,
        )
        rows = (
            EpsRow(
                fiscal_year=None,
                fiscal_period=None,
                actual=fixture.latest_actual_eps,
                estimate=fixture.latest_estimate_eps,
                reported=fixture.latest_actual_eps is not None,
            ),
        )
        notes = fixture.notes or ("Fixture-supplied fundamentals snapshot (not live).",)
        return FundamentalsSnapshot(
            symbol=key,
            available=True,
            source=self.name,
            score=score,
            latest_actual_eps=fixture.latest_actual_eps,
            latest_estimate_eps=fixture.latest_estimate_eps,
            beat_miss=fixture.beat_miss,
            rows=rows,
            statements_status=fixture.statements_status,
            latest_indicators=indicators,
            income=fixture.income,
            cashflow=fixture.cashflow,
            balance=fixture.balance,
            industry=fixture.industry,
            notes=notes,
        )


def unavailable_fundamentals(
    symbol: str,
    *,
    source: str,
    note: str,
    error: str = "",
    statements_status: str = "unavailable",
) -> FundamentalsSnapshot:
    return FundamentalsSnapshot(
        symbol=symbol.upper(),
        available=False,
        source=source,
        beat_miss="unavailable",
        statements_status=statements_status,
        notes=(note,),
        raw_error=error,
    )
