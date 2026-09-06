"""Parse official Webull forecast-EPS payloads.

Field names from official Java ``ForecastEps`` and Python
``DataClient.fundamentals.get_forecast_eps``:
fiscalYear, fiscalPeriod, actual, est, reported.
"""

from __future__ import annotations

from typing import Any

from trading_system.events.parse import first_value
from trading_system.fundamentals.types import EpsRow
from trading_system.models import to_float
from trading_system.webull_support import as_record_list


def parse_forecast_eps_rows(payload: Any) -> list[EpsRow]:
    rows = as_record_list(payload, ("data", "result", "items", "list", "forecast", "eps"))
    if not rows and isinstance(payload, dict):
        if first_value(payload, "actual", "est", "estimate") is not None:
            rows = [payload]
    out: list[EpsRow] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
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
        reported_raw = first_value(row, "reported")
        reported: bool | None
        if reported_raw is None:
            reported = None
        else:
            reported = str(reported_raw).strip().lower() in {"1", "true", "yes", "y"}
        out.append(
            EpsRow(
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                actual=to_float(first_value(row, "actual", "eps_actual", "epsActual")),
                estimate=to_float(first_value(row, "est", "estimate", "eps_est", "epsEst")),
                reported=reported,
            )
        )
    return out


def beat_miss_and_score(rows: list[EpsRow]) -> tuple[str, float | None, float | None, float | None]:
    """Return beat_miss, score, latest_actual, latest_estimate from official rows only."""
    if not rows:
        return "unavailable", None, None, None
    reported = [r for r in rows if r.actual is not None]
    latest = reported[-1] if reported else rows[-1]
    actual = latest.actual
    estimate = latest.estimate
    if actual is None and estimate is None:
        return "unknown", 45.0, None, None
    if actual is None:
        return "unknown", 50.0, None, estimate
    if estimate is None or estimate == 0:
        return "unknown", 52.0, actual, estimate
    delta = (actual - estimate) / abs(estimate)
    if delta >= 0.02:
        return "beat", 72.0, actual, estimate
    if delta <= -0.02:
        return "miss", 38.0, actual, estimate
    return "inline", 55.0, actual, estimate
