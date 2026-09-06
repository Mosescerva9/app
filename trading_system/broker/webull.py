"""Webull Trading API read adapter (accounts / balances / positions / open orders).

Uses official TradeClient.account_v2 / order_v3 methods only.
No order placement.
"""

from __future__ import annotations

import logging
from typing import Any

from trading_system.broker.base import BrokerReadClient
from trading_system.models import AccountBalance, OpenOrder, Position, to_float
from trading_system.webull_support import (
    WebullApiError,
    account_access_hint,
    as_record_list,
    collect_account_ids,
    extract_account_id,
    require_ok,
)

logger = logging.getLogger(__name__)


class WebullBrokerReadClient(BrokerReadClient):
    name = "webull"

    def __init__(
        self,
        *,
        app_key: str,
        app_secret: str,
        region: str = "us",
        api_endpoint: str = "api.sandbox.webull.com",
    ) -> None:
        if not app_key or not app_secret:
            raise ValueError("WebullBrokerReadClient requires WEBULL_APP_KEY and WEBULL_APP_SECRET")

        from webull.core.client import ApiClient
        from webull.trade.trade_client import TradeClient

        api_client = ApiClient(app_key, app_secret, region)
        api_client.add_endpoint(region, api_endpoint)
        self._trade = TradeClient(api_client)
        self._endpoint = api_endpoint
        logger.info("Webull broker read client ready (endpoint=%s)", api_endpoint)

    @property
    def endpoint(self) -> str:
        return self._endpoint

    def list_accounts(self) -> list[dict]:
        res = self._trade.account_v2.get_account_list()
        payload = require_ok(res, "get_account_list", endpoint=self._endpoint)
        rows = _account_rows(payload)
        if not rows:
            logger.info("Account list empty on %s", self._endpoint)
        return rows

    def get_balance(self, account_id: str) -> AccountBalance:
        if not account_id:
            raise WebullApiError(
                "Missing account_id. " + account_access_hint(endpoint=self._endpoint),
                action="get_account_balance",
                error_code="MISSING_ACCOUNT_ID",
                endpoint=self._endpoint,
            )
        res = self._trade.account_v2.get_account_balance(account_id)
        try:
            payload = require_ok(res, "get_account_balance", endpoint=self._endpoint)
        except WebullApiError as exc:
            raise _with_account_context(exc, account_id=account_id, endpoint=self._endpoint) from exc
        data = payload if isinstance(payload, dict) else {"raw": payload}
        currency_row = _first_currency_asset(data)
        equity = to_float(
            data.get("total_net_liquidation_value")
            or data.get("net_liquidation")
            or data.get("totalEquity")
            or data.get("equity")
            or data.get("total_market_value")
        )
        cash = to_float(
            data.get("total_cash_balance")
            or data.get("cash_balance")
            or data.get("cash")
            or data.get("settledCash")
            or (currency_row.get("cash_balance") if currency_row else None)
        )
        buying_power = to_float(
            data.get("buying_power")
            or data.get("buyingPower")
            or data.get("dayBuyingPower")
            or (currency_row.get("buying_power") if currency_row else None)
            or (currency_row.get("option_buying_power") if currency_row else None)
        )
        return AccountBalance(
            account_id=account_id,
            total_equity=equity,
            cash=cash,
            buying_power=buying_power,
            raw=data,
        )

    def get_positions(self, account_id: str) -> list[Position]:
        res = self._trade.account_v2.get_account_position(account_id)
        try:
            payload = require_ok(res, "get_account_position", endpoint=self._endpoint)
        except WebullApiError as exc:
            raise _with_account_context(exc, account_id=account_id, endpoint=self._endpoint) from exc
        rows = as_record_list(payload, keys=("positions", "data", "result", "holdings"))
        out: list[Position] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            sym = str(row.get("symbol") or row.get("ticker") or row.get("instrument_id") or "").upper()
            qty = to_float(row.get("quantity") or row.get("qty") or row.get("position")) or 0.0
            out.append(
                Position(
                    symbol=sym,
                    quantity=qty,
                    market_value=to_float(row.get("market_value") or row.get("marketValue")),
                    average_cost=to_float(row.get("average_cost") or row.get("avgCost") or row.get("costPrice")),
                    instrument_type=str(row.get("instrument_type") or row.get("assetType") or "") or None,
                    raw=dict(row),
                )
            )
        return out

    def get_open_orders(self, account_id: str) -> list[OpenOrder]:
        res = self._trade.order_v3.get_order_open(account_id)
        try:
            payload = require_ok(res, "get_order_open", endpoint=self._endpoint)
        except WebullApiError as exc:
            raise _with_account_context(exc, account_id=account_id, endpoint=self._endpoint) from exc
        rows = as_record_list(payload, keys=("orders", "data", "result"))
        out: list[OpenOrder] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            out.append(
                OpenOrder(
                    order_id=str(row.get("order_id") or row.get("orderId") or row.get("id") or ""),
                    client_order_id=(
                        str(row.get("client_order_id") or row.get("clientOrderId"))
                        if (row.get("client_order_id") or row.get("clientOrderId"))
                        else None
                    ),
                    symbol=str(row.get("symbol") or row.get("ticker") or "").upper(),
                    side=str(row.get("side") or row.get("action") or "") or None,
                    status=str(row.get("status") or row.get("order_status") or "") or None,
                    quantity=to_float(row.get("quantity") or row.get("qty")),
                    raw=dict(row),
                )
            )
        return out


def _account_rows(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [dict(x) for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("accounts", "data", "result"):
            if isinstance(payload.get(key), list):
                return [dict(x) for x in payload[key] if isinstance(x, dict)]
        if extract_account_id(payload):
            return [payload]
    return []


def _first_currency_asset(data: dict[str, Any]) -> dict[str, Any]:
    rows = data.get("account_currency_assets") or data.get("accountCurrencyAssets") or []
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict):
                return row
    return {}


def _with_account_context(exc: WebullApiError, *, account_id: str, endpoint: str) -> WebullApiError:
    extra = account_access_hint(endpoint=endpoint, account_id=account_id)
    if extra in str(exc):
        return exc
    return WebullApiError(
        f"{exc} {extra}",
        action=exc.action,
        status=exc.status,
        error_code=exc.error_code,
        endpoint=endpoint,
        body=exc.body,
    )


def known_account_ids(accounts: list[dict]) -> list[str]:
    return collect_account_ids(accounts)
