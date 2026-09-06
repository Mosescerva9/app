"""Webull OpenAPI option-chain adapter (read-only).

Uses official DataClient methods only:
- instrument.get_option_contracts  (GET /openapi/instrument/option/contracts)
- option_market_data.get_option_snapshot  (GET /market-data/options/snapshots/list)

Requires OpenAPI Advanced Quotes + OPRA options market data entitlement.
Never places orders.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Sequence

from trading_system.models import to_float
from trading_system.options.chain import OptionChainProvider
from trading_system.options.types import OptionContract, occ_symbol
from trading_system.webull_support import WebullApiError, as_record_list, require_ok

logger = logging.getLogger(__name__)

_SNAPSHOT_BATCH = 20  # official option snapshot max symbols per request
_CONTRACT_PAGE = 200
_MAX_PAGES = 8
_STRIKE_BAND = 0.15  # ±15% of spot keeps the chain actionable and under rate limits


class WebullOptionChainProvider(OptionChainProvider):
    name = "webull"

    def __init__(
        self,
        *,
        data_client: Any | None = None,
        app_key: str = "",
        app_secret: str = "",
        region: str = "us",
        api_endpoint: str = "api.sandbox.webull.com",
        min_dte: int = 30,
        max_dte: int = 60,
        strike_band: float = _STRIKE_BAND,
    ) -> None:
        if data_client is None:
            if not app_key or not app_secret:
                raise ValueError(
                    "WebullOptionChainProvider requires a DataClient or "
                    "WEBULL_APP_KEY / WEBULL_APP_SECRET"
                )
            from webull.core.client import ApiClient
            from webull.data.data_client import DataClient

            api_client = ApiClient(app_key, app_secret, region)
            api_client.add_endpoint(region, api_endpoint)
            data_client = DataClient(api_client)
        self._data = data_client
        self._endpoint = api_endpoint
        self.min_dte = min_dte
        self.max_dte = max_dte
        self.strike_band = strike_band

    def get_chain(
        self,
        underlying: str,
        *,
        as_of: datetime | None = None,
        spot: float | None = None,
    ) -> Sequence[OptionContract]:
        now = as_of or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        symbol = underlying.upper()
        start = (now.date() + timedelta(days=self.min_dte)).isoformat()
        end = (now.date() + timedelta(days=self.max_dte)).isoformat()

        lo = hi = None
        if spot and spot > 0:
            lo = round(spot * (1.0 - self.strike_band), 2)
            hi = round(spot * (1.0 + self.strike_band), 2)

        try:
            raw_contracts = self._list_contracts(
                symbol, start_date=start, end_date=end, strike_gte=lo, strike_lte=hi
            )
        except WebullApiError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise WebullApiError(
                f"Option contract listing failed for {symbol}: {exc}. "
                "Confirm OpenAPI Advanced Quotes / OPRA options entitlement.",
                action="get_option_contracts",
                endpoint=self._endpoint,
            ) from exc

        if not raw_contracts:
            # Retry without date bounds (SDK start_date is documented as "exact"
            # expiration; if that interpretation holds, the windowed query is empty).
            raw_contracts = self._list_contracts(
                symbol, start_date=None, end_date=None, strike_gte=lo, strike_lte=hi
            )

        specs = [c for c in (_normalize_contract_spec(r, symbol) for r in raw_contracts) if c]
        specs = [c for c in specs if self.min_dte <= _dte(c.expiration, now) <= self.max_dte]
        if not specs:
            logger.info("No listed option contracts in DTE window for %s", symbol)
            return []

        symbols = [c.symbol for c in specs]
        try:
            snaps = self._snapshot_map(symbols)
        except WebullApiError as exc:
            sample = ", ".join(symbols[:5])
            raise WebullApiError(
                f"Listed {len(specs)} OCC contracts for {symbol} via get_option_contracts "
                f"(e.g. {sample}) but quotes/greeks failed: {exc}",
                action="get_option_snapshot",
                status=exc.status,
                error_code=exc.error_code or "MARKET_DATA_NOT_SUBSCRIBED",
                endpoint=self._endpoint,
                body=exc.body,
            ) from exc
        out: list[OptionContract] = []
        for spec in specs:
            snap = snaps.get(spec.symbol) or {}
            out.append(_merge_contract(spec, snap, as_of=now))
        return out

    def _list_contracts(
        self,
        underlying: str,
        *,
        start_date: str | None,
        end_date: str | None,
        strike_gte: float | None,
        strike_lte: float | None,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        last_id = None
        for _ in range(_MAX_PAGES):
            res = self._data.instrument.get_option_contracts(
                category="US_OPTION",
                underlying_symbols=underlying,
                status="LISTING",
                start_date=start_date,
                end_date=end_date,
                strike_price_gte=strike_gte,
                strike_price_lte=strike_lte,
                page_size=_CONTRACT_PAGE,
                last_instrument_id=last_id,
            )
            payload = require_ok(res, "get_option_contracts", endpoint=self._endpoint)
            page = _contract_page_rows(payload)
            if not page:
                break
            rows.extend(page)
            last_id = page[-1].get("instrument_id") or page[-1].get("instrumentId")
            if len(page) < _CONTRACT_PAGE or not last_id:
                break
        return rows

    def _snapshot_map(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for i in range(0, len(symbols), _SNAPSHOT_BATCH):
            chunk = symbols[i : i + _SNAPSHOT_BATCH]
            try:
                res = self._data.option_market_data.get_option_snapshot(chunk, "US_OPTION")
                payload = require_ok(res, "get_option_snapshot", endpoint=self._endpoint)
            except WebullApiError as exc:
                logger.info("Option snapshot batch failed (%s): %s", chunk[:2], exc)
                if i == 0:
                    raise WebullApiError(
                        f"{exc} Option snapshots require OPRA / Advanced Quotes. "
                        "Chains cannot be scored without bid/ask/greeks.",
                        action="get_option_snapshot",
                        status=exc.status,
                        error_code=exc.error_code,
                        endpoint=self._endpoint,
                        body=exc.body,
                    ) from exc
                continue
            rows = payload if isinstance(payload, list) else as_record_list(
                payload, ("data", "snapshots", "result")
            )
            for row in rows:
                if not isinstance(row, dict):
                    continue
                sym = str(row.get("symbol") or row.get("ticker") or "").upper()
                if sym:
                    out[sym] = row
        return out


def _contract_page_rows(payload: Any) -> list[dict[str, Any]]:
    rows = payload if isinstance(payload, list) else as_record_list(
        payload, ("data", "result", "contracts", "items", "list")
    )
    return [r for r in rows if isinstance(r, dict)]


def _dte(expiration: date, as_of: datetime) -> int:
    return max(0, (expiration - as_of.date()).days)


class _Spec:
    __slots__ = ("symbol", "underlying", "right", "expiration", "strike")

    def __init__(
        self,
        symbol: str,
        underlying: str,
        right: str,
        expiration: date,
        strike: float,
    ) -> None:
        self.symbol = symbol
        self.underlying = underlying
        self.right = right
        self.expiration = expiration
        self.strike = strike


def _normalize_contract_spec(row: dict[str, Any], underlying: str) -> _Spec | None:
    right_raw = str(
        row.get("option_type")
        or row.get("optionType")
        or row.get("right")
        or row.get("type")
        or ""
    ).upper()
    if right_raw.startswith("C"):
        right = "CALL"
    elif right_raw.startswith("P"):
        right = "PUT"
    else:
        return None
    exp = _parse_expiration(
        row.get("expire_date")
        or row.get("expiration_date")
        or row.get("option_expire_date")
        or row.get("expireDate")
        or row.get("expiration")
    )
    strike = to_float(row.get("strike_price") or row.get("strikePrice") or row.get("strike"))
    if exp is None or strike is None or strike <= 0:
        return None
    symbol = str(
        row.get("symbol")
        or row.get("option_symbol")
        or row.get("optionSymbol")
        or occ_symbol(underlying, exp, right, strike)
    ).upper()
    return _Spec(symbol, underlying.upper(), right, exp, float(strike))


def _parse_expiration(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    if text.isdigit() and len(text) == 8:
        try:
            return datetime.strptime(text, "%Y%m%d").date()
        except ValueError:
            return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _merge_contract(spec: _Spec, snap: dict[str, Any], *, as_of: datetime) -> OptionContract:
    bid = to_float(snap.get("bid") or snap.get("bidPrice")) or 0.0
    ask = to_float(snap.get("ask") or snap.get("askPrice")) or 0.0
    last = to_float(snap.get("price") or snap.get("last") or snap.get("close")) or 0.0
    if bid > 0 and ask > 0:
        mid = (bid + ask) / 2.0
    elif last > 0:
        mid = last
    else:
        mid = max(bid, ask, 0.0)
    return OptionContract(
        underlying=spec.underlying,
        right=spec.right,
        expiration=spec.expiration,
        strike=spec.strike,
        bid=round(bid, 4),
        ask=round(ask, 4),
        last=round(last, 4),
        mid=round(mid, 4),
        volume=int(to_float(snap.get("volume")) or 0),
        open_interest=int(to_float(snap.get("open_interest") or snap.get("openInterest")) or 0),
        implied_volatility=float(to_float(snap.get("imp_vol") or snap.get("implied_volatility") or snap.get("iv")) or 0.0),
        delta=float(to_float(snap.get("delta")) or 0.0),
        gamma=float(to_float(snap.get("gamma")) or 0.0),
        theta=float(to_float(snap.get("theta")) or 0.0),
        vega=float(to_float(snap.get("vega")) or 0.0),
        as_of=as_of,
        symbol=spec.symbol,
        exchange="WEBULL",
    )
