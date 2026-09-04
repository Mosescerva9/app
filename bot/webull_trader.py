"""Webull OpenAPI options order client."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from bot.parser import Action, TradeAlert

logger = logging.getLogger(__name__)


@dataclass
class OrderResult:
    ok: bool
    client_order_id: str
    response: Any = None
    error: str | None = None
    dry_run: bool = False


class WebullOptionsTrader:
    """Thin wrapper around the official Webull OpenAPI TradeClient."""

    def __init__(
        self,
        *,
        app_key: str,
        app_secret: str,
        account_id: str,
        region: str = "us",
        api_endpoint: str = "api.sandbox.webull.com",
        dry_run: bool = True,
        buy_slippage: float = 0.05,
        sell_slippage: float = 0.05,
    ) -> None:
        self.account_id = account_id
        self.dry_run = dry_run
        self.buy_slippage = buy_slippage
        self.sell_slippage = sell_slippage
        self._trade_client = None

        if dry_run:
            logger.warning("Webull trader running in DRY_RUN mode — no live orders")
            return

        # Import lazily so dry-run / unit tests work without the SDK installed.
        from webull.core.client import ApiClient
        from webull.trade.trade_client import TradeClient

        api_client = ApiClient(app_key, app_secret, region)
        api_client.add_endpoint(region, api_endpoint)
        self._trade_client = TradeClient(api_client)
        logger.info(
            "Webull TradeClient ready (region=%s endpoint=%s account=%s)",
            region,
            api_endpoint,
            account_id,
        )

    def _limit_price(self, alert: TradeAlert) -> float | None:
        if alert.limit_price is None:
            return None
        if alert.action is Action.BUY:
            # Pay up to improve fill probability on fast moves.
            return round(alert.limit_price * (1.0 + self.buy_slippage), 2)
        return round(max(0.01, alert.limit_price * (1.0 - self.sell_slippage)), 2)

    def build_order(self, alert: TradeAlert, quantity: int) -> dict[str, Any]:
        limit = self._limit_price(alert)
        if limit is None:
            raise ValueError("limit_price is required for Webull options orders")

        strike = f"{alert.strike:.2f}"
        client_order_id = uuid.uuid4().hex[:32]
        side = alert.action.value
        return {
            "client_order_id": client_order_id,
            "combo_type": "NORMAL",
            "order_type": "LIMIT",
            "limit_price": f"{limit:.2f}",
            "quantity": str(quantity),
            "option_strategy": "SINGLE",
            "side": side,
            "time_in_force": "DAY",
            "entrust_type": "QTY",
            "instrument_type": "OPTION",
            "market": "US",
            "symbol": alert.symbol,
            "legs": [
                {
                    "side": side,
                    "quantity": str(quantity),
                    "symbol": alert.symbol,
                    "strike_price": strike,
                    "option_expire_date": alert.expiration,
                    "instrument_type": "OPTION",
                    "option_type": alert.option_type.value,
                    "market": "US",
                }
            ],
        }

    def place_option_order(self, alert: TradeAlert, quantity: int) -> OrderResult:
        order = self.build_order(alert, quantity)
        client_order_id = order["client_order_id"]

        if self.dry_run or self._trade_client is None:
            logger.info("DRY_RUN order: %s", order)
            return OrderResult(
                ok=True,
                client_order_id=client_order_id,
                response={"dry_run": True, "order": order},
                dry_run=True,
            )

        try:
            res = self._trade_client.order_v3.place_order(
                self.account_id, [order]
            )
            status = getattr(res, "status_code", None)
            body = res.json() if hasattr(res, "json") else res
            if status is not None and status >= 400:
                logger.error("Webull order rejected (%s): %s", status, body)
                return OrderResult(
                    ok=False,
                    client_order_id=client_order_id,
                    response=body,
                    error=f"HTTP {status}: {body}",
                )
            logger.info("Webull order accepted: %s", body)
            return OrderResult(
                ok=True, client_order_id=client_order_id, response=body
            )
        except Exception as exc:  # noqa: BLE001 — surface any SDK/network failure
            logger.exception("Webull place_order failed")
            return OrderResult(
                ok=False, client_order_id=client_order_id, error=str(exc)
            )

    def ping_account(self) -> Any:
        if self.dry_run or self._trade_client is None:
            return {"dry_run": True}
        res = self._trade_client.account_v2.get_account_list()
        return res.json() if hasattr(res, "json") else res
