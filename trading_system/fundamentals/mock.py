"""Offline fundamentals provider. Does not invent financials."""

from __future__ import annotations

from datetime import datetime

from trading_system.fundamentals.base import FundamentalsProvider
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
                    "filings-backed metrics, or analyst numbers."
                ),
            )
        score = 70.0 if fixture.beat_miss == "beat" else 40.0 if fixture.beat_miss == "miss" else 55.0
        rows = (
            EpsRow(
                fiscal_year=None,
                fiscal_period=None,
                actual=fixture.latest_actual_eps,
                estimate=fixture.latest_estimate_eps,
                reported=fixture.latest_actual_eps is not None,
            ),
        )
        return FundamentalsSnapshot(
            symbol=key,
            available=True,
            source=self.name,
            score=score,
            latest_actual_eps=fixture.latest_actual_eps,
            latest_estimate_eps=fixture.latest_estimate_eps,
            beat_miss=fixture.beat_miss,
            rows=rows,
            notes=fixture.notes or ("Fixture-supplied EPS snapshot (not live fundamentals).",),
        )


def unavailable_fundamentals(
    symbol: str,
    *,
    source: str,
    note: str,
    error: str = "",
) -> FundamentalsSnapshot:
    return FundamentalsSnapshot(
        symbol=symbol.upper(),
        available=False,
        source=source,
        beat_miss="unavailable",
        notes=(note,),
        raw_error=error,
    )
