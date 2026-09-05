"""Webull Trading API read adapter (accounts / balances / positions / open orders).

No order placement in Phase 2.
"""

from __future__ import annotations

import logging
from typing import Any

from trading_system.broker.base import BrokerReadClient
from trading_system.models import AccountBalance, OpenOrder, Position, to_float

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

    def list_accounts(self) -> list[dict]:
        res = self._trade.account_v2.get_account_list()
        payload = _require_ok(res, "get_account_list")
        if isinstance(payload, list):
            return [dict(x) for x in payload]
        if isinstance(payload, dict):
            for key in ("accounts", "data", "result"):
                if isinstance(payload.get(key), list):
                    return [dict(x) for x in payload[key]]
            return [payload]
        return []

    def get_balance(self, account_id: str) -> AccountBalance:
        res = self._trade.account_v2.get_account_balance(account_id)
        payload = _require_ok(res, "get_account_balance")
        data = payload if isinstance(payload, dict) else {"raw": payload}
        return AccountBalance(
            account_id=account_id,
            total_equity=to_float(
                data.get("total_market_value")
                or data.get("net_liquidation")
                or data.get("totalEquity")
                or data.get("equity")
            ),
            cash=to_float(data.get("cash_balance") or data.get("cash") or data.get("settledCash")),
            buying_power=to_float(
                data.get("buying_power") or data.get("buyingPower") or data.get("dayBuyingPower")
            ),
            raw=data,
        )

    def get_positions(self, account_id: str) -> list[Position]:
        res = self._trade.account_v2.get_account_position(account_id)
        payload = _require_ok(res, "get_account_position")
        rows = _as_list(payload, keys=("positions", "data", "result", "holdings"))
        out: list[Position] = []
        for row in rows:
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
        payload = _require_ok(res, "get_order_open")
        rows = _as_list(payload, keys=("orders", "data", "result"))
        out: list[OpenOrder] = []
        for row in rows:
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


def _require_ok(res: Any, action: str) -> Any:
    status = getattr(res, "status_code", None)
    body = res.json() if hasattr(res, "json") else res
    if status is not None and int(status) >= 400:
        raise RuntimeError(f"Webull {action} failed HTTP {status}: {body}")
    return body


def _as_list(payload: Any, keys: tuple[str, ...]) -> list[dict]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
        return [payload]
    return []
