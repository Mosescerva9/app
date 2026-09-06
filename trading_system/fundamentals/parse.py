"""Parse official Webull forecast-EPS, indicators, and statement payloads.

Field names from official docs (snake_case) plus Java/Python camelCase aliases.
Do not invent values when a key is missing.
"""

from __future__ import annotations

from typing import Any

from trading_system.events.parse import first_value
from trading_system.fundamentals.types import (
    BALANCE_FIELD_KEYS,
    CASHFLOW_FIELD_KEYS,
    INCOME_FIELD_KEYS,
    OFFICIAL_INDICATOR_KEYS,
    EpsRow,
    IndicatorPoint,
    IndustryComparison,
    IndustryPeer,
    StatementPeriod,
)
from trading_system.models import to_float
from trading_system.webull_support import as_record_list


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _period_meta(row: dict[str, Any]) -> tuple[int | None, int | None, str | None, str | None, str | None]:
    fy = _int_or_none(first_value(row, "fiscal_year", "fiscalYear"))
    fp = _int_or_none(first_value(row, "fiscal_period", "fiscalPeriod"))
    end = first_value(row, "end_date", "endDate")
    pub = first_value(row, "publish_date", "publishDate")
    cur = first_value(row, "currency")
    return fy, fp, str(end) if end is not None else None, str(pub) if pub is not None else None, (
        str(cur) if cur is not None else None
    )


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


def _latest_indicator_item(items: Any) -> dict[str, Any] | None:
    rows = items if isinstance(items, list) else []
    typed = [r for r in rows if isinstance(r, dict)]
    return typed[-1] if typed else None


def parse_indicators(payload: Any) -> tuple[dict[str, float | None], list[IndicatorPoint]]:
    """Official FinancialValuesVo: {currency, values: {roa: [{fiscal_year, fiscal_period, value}]}}."""
    body = payload
    if isinstance(payload, dict):
        nested = payload.get("values") or payload.get("Values") or payload.get("data")
        if isinstance(nested, dict) and any(
            k.lower() in {x.lower() for x in OFFICIAL_INDICATOR_KEYS} or isinstance(v, list)
            for k, v in nested.items()
        ):
            body = {"values": nested} if "values" not in payload and "Values" not in payload else payload
    values = {}
    if isinstance(body, dict):
        values = body.get("values") or body.get("Values") or {}
    if not isinstance(values, dict):
        return {}, []
    latest: dict[str, float | None] = {}
    points: list[IndicatorPoint] = []
    official_lower = {k.lower(): k for k in OFFICIAL_INDICATOR_KEYS}
    for raw_name, items in values.items():
        canon = official_lower.get(str(raw_name).lower())
        if canon is None:
            continue
        last = _latest_indicator_item(items)
        if last is None:
            continue
        val = to_float(first_value(last, "value", "Value"))
        latest[canon] = val
        points.append(
            IndicatorPoint(
                name=canon,
                fiscal_year=_int_or_none(first_value(last, "fiscal_year", "fiscalYear")),
                fiscal_period=_int_or_none(first_value(last, "fiscal_period", "fiscalPeriod")),
                value=val,
            )
        )
    return latest, points


def _extract_fields(row: dict[str, Any], keys: tuple[str, ...]) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    camel = {k: "".join(p.title() if i else p for i, p in enumerate(k.split("_"))) for k in keys}
    # fiscalYear-style: total_revenue -> totalRevenue
    camel = {}
    for key in keys:
        parts = key.split("_")
        camel[key] = parts[0] + "".join(p.title() for p in parts[1:])
    for key in keys:
        raw = first_value(row, key, camel[key])
        parsed = to_float(raw)
        if parsed is not None:
            out[key] = parsed
    return out


def parse_statement_periods(payload: Any, *, kind: str, field_keys: tuple[str, ...]) -> list[StatementPeriod]:
    rows = as_record_list(payload, ("data", "result", "items", "list", "statements"))
    if not rows and isinstance(payload, dict) and first_value(payload, "fiscal_year", "fiscalYear") is not None:
        rows = [payload]
    out: list[StatementPeriod] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        fy, fp, end, pub, cur = _period_meta(row)
        fields = _extract_fields(row, field_keys)
        if fy is None and fp is None and not fields:
            continue
        out.append(
            StatementPeriod(
                kind=kind,
                fiscal_year=fy,
                fiscal_period=fp,
                end_date=end,
                publish_date=pub,
                currency=cur,
                fields=fields,
            )
        )
    return out


def parse_income_periods(payload: Any) -> list[StatementPeriod]:
    return parse_statement_periods(payload, kind="income", field_keys=INCOME_FIELD_KEYS)


def parse_cashflow_periods(payload: Any) -> list[StatementPeriod]:
    return parse_statement_periods(payload, kind="cashflow", field_keys=CASHFLOW_FIELD_KEYS)


def parse_balance_periods(payload: Any) -> list[StatementPeriod]:
    return parse_statement_periods(payload, kind="balance", field_keys=BALANCE_FIELD_KEYS)


def parse_industry_comparison(payload: Any, *, symbol: str) -> IndustryComparison:
    body = payload
    if isinstance(payload, dict):
        for nest in ("data", "result"):
            inner = payload.get(nest)
            if isinstance(inner, dict) and (
                "industry_name" in inner
                or "industryName" in inner
                or "data" in inner
            ):
                body = inner
                break
    if not isinstance(body, dict):
        return IndustryComparison(available=False, notes=("Industry comparison payload was not an object.",))
    name = str(first_value(body, "industry_name", "industryName") or "")
    metric = str(first_value(body, "type", "metric", "sort_by", "sortBy") or "")
    fy = _int_or_none(first_value(body, "fiscal_year", "fiscalYear"))
    fp = _int_or_none(first_value(body, "fiscal_period", "fiscalPeriod"))
    raw_peers = body.get("data") or body.get("items") or body.get("list") or []
    if not isinstance(raw_peers, list):
        raw_peers = []
    peers: list[IndustryPeer] = []
    self_rank = None
    self_value = None
    key = symbol.upper()
    for row in raw_peers:
        if not isinstance(row, dict):
            continue
        sym = str(first_value(row, "symbol", "ticker") or "").upper()
        peer = IndustryPeer(
            symbol=sym,
            name=str(first_value(row, "name", "securityName") or ""),
            rank=_int_or_none(first_value(row, "rank")),
            value=to_float(first_value(row, "value")),
        )
        peers.append(peer)
        if sym == key:
            self_rank = peer.rank
            self_value = peer.value
    if not peers and not name:
        return IndustryComparison(available=False, notes=("Official industry comparison returned no peers.",))
    return IndustryComparison(
        available=True,
        industry_name=name,
        metric=metric,
        fiscal_year=fy,
        fiscal_period=fp,
        peers=tuple(peers),
        self_rank=self_rank,
        self_value=self_value,
        notes=(
            "Source: DataClient.fundamentals.get_industry_comparison "
            "(GET /openapi/fundamentals/stock/industry-comparison).",
        ),
    )


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


def blend_fundamental_score(
    *,
    eps_score: float | None,
    indicators: dict[str, float | None],
    income: StatementPeriod | None,
) -> float | None:
    """Heuristic on official numbers only. Missing keys are skipped, never filled."""
    base = eps_score
    if base is None and not indicators and income is None:
        return None
    score = 50.0 if base is None else base
    roe = indicators.get("roe")
    if roe is not None:
        if roe > 0.15:
            score += 8
        elif roe > 0:
            score += 5
        elif roe < 0:
            score -= 8
    margin = indicators.get("net_margin")
    if margin is not None:
        if margin > 0:
            score += 5
        else:
            score -= 8
    debt = indicators.get("debt_to_assets")
    if debt is not None and debt > 0.7:
        score -= 8
    if income is not None:
        ni = income.fields.get("net_income")
        if ni is not None and ni < 0:
            score -= 6
        rev = income.fields.get("total_revenue") or income.fields.get("revenue")
        if rev is not None and rev > 0 and ni is not None and ni > 0:
            score += 3
    return max(0.0, min(100.0, score))
