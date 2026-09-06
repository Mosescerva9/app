"""Offline catalyst provider. Does not invent news or earnings headlines."""

from __future__ import annotations

from datetime import datetime

from trading_system.events.base import CatalystProvider
from trading_system.events.parse import aware_utc
from trading_system.events.scoring import snapshot_from_events
from trading_system.events.types import CatalystFixture, CatalystSnapshot, EarningsEvent


class MockCatalystProvider(CatalystProvider):
    """Default RESEARCH/CI source: unavailable unless a fixture is injected.

    Fixtures are for tests and operator replay of a *known* date. They are
    not a news feed.
    """

    name = "mock"

    def __init__(
        self,
        fixtures: dict[str, CatalystFixture] | None = None,
    ) -> None:
        self.fixtures = {k.upper(): v for k, v in (fixtures or {}).items()}

    def get_catalyst(
        self,
        symbol: str,
        *,
        as_of: datetime | None = None,
    ) -> CatalystSnapshot:
        now = aware_utc(as_of)
        key = symbol.upper()
        fixture = self.fixtures.get(key)
        if fixture is None:
            return snapshot_from_events(
                key,
                source=self.name,
                as_of=now.date(),
                earnings=[],
                filings=[],
                notes=[
                    "Catalyst unavailable: mock provider does not invent news, "
                    "headlines, or earnings dates.",
                    "Inject a CatalystFixture in tests, or use MARKET_DATA_PROVIDER=webull "
                    "with DataClient.fundamentals.get_earnings_calendar.",
                ],
                available=False,
                earnings_status_override="unavailable",
            )
        earnings: list[EarningsEvent] = []
        if fixture.earnings_date is not None:
            earnings.append(
                EarningsEvent(
                    expected_publish_date=fixture.earnings_date,
                    eps_actual=None if fixture.earnings_status == "upcoming" else 0.0,
                    eps_estimate=None,
                    status=fixture.earnings_status,
                )
            )
        notes = list(fixture.notes) or [
            "Fixture-supplied earnings date (not live news).",
        ]
        return snapshot_from_events(
            key,
            source=self.name,
            as_of=now.date(),
            earnings=earnings,
            filings=list(fixture.filings),
            notes=notes,
            available=True,
            earnings_status_override=fixture.earnings_status if fixture.earnings_date else "unknown",
        )


def unavailable_snapshot(symbol: str, *, source: str, note: str, error: str = "") -> CatalystSnapshot:
    return CatalystSnapshot(
        symbol=symbol.upper(),
        available=False,
        source=source,
        earnings_status="unavailable",
        event_flags=("earnings_date_unknown",),
        notes=(note,),
        raw_error=error,
    )
