"""Orchestrates Discord alert -> parse -> Webull order."""

from __future__ import annotations

import logging
import time
from typing import Any

from bot.config import Settings
from bot.parser import Action, TradeAlert, parse_alert_from_parts
from bot.positions import PositionStore
from bot.webull_trader import OrderResult, WebullOptionsTrader

logger = logging.getLogger(__name__)


class TradeEngine:
    def __init__(
        self,
        settings: Settings,
        trader: WebullOptionsTrader,
        store: PositionStore,
    ) -> None:
        self.settings = settings
        self.trader = trader
        self.store = store

    def extract_text_parts(self, message: Any) -> list[str]:
        parts: list[str] = []
        content = getattr(message, "content", None) or ""
        if content.strip():
            parts.append(content)

        for embed in getattr(message, "embeds", []) or []:
            if getattr(embed, "title", None):
                parts.append(str(embed.title))
            if getattr(embed, "description", None):
                parts.append(str(embed.description))
            for field in getattr(embed, "fields", []) or []:
                name = getattr(field, "name", "") or ""
                value = getattr(field, "value", "") or ""
                parts.append(f"{name}: {value}")
        return parts

    def handle_message(self, message: Any) -> OrderResult | None:
        """Hot path: parse and place as fast as possible."""
        t0 = time.perf_counter()
        message_id = str(getattr(message, "id", ""))
        if message_id and self.store.already_processed(message_id):
            return None

        parts = self.extract_text_parts(message)
        alert = parse_alert_from_parts(
            parts, default_quantity=self.settings.default_quantity
        )
        if alert is None:
            return None

        if message_id:
            self.store.mark_processed(message_id)

        result = self.execute_alert(alert, discord_message_id=message_id)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "Handled %s %s in %.1fms ok=%s dry_run=%s",
            alert.action.value,
            alert.contract_key,
            elapsed_ms,
            result.ok if result else None,
            getattr(result, "dry_run", None),
        )
        return result

    def execute_alert(
        self, alert: TradeAlert, discord_message_id: str | None = None
    ) -> OrderResult:
        qty = alert.quantity or self.settings.default_quantity
        qty = max(1, min(qty, self.settings.max_quantity))

        if self.settings.require_limit_price and alert.limit_price is None:
            logger.error(
                "Skipping %s — no limit price in alert (set REQUIRE_LIMIT_PRICE=false to override)",
                alert.contract_key,
            )
            return OrderResult(
                ok=False,
                client_order_id="",
                error="missing limit price",
            )

        if alert.action is Action.SELL:
            open_pos = self.store.get(alert.contract_key)
            if open_pos is None:
                logger.warning(
                    "Sell alert for %s but no open local position — still submitting",
                    alert.contract_key,
                )
            else:
                qty = min(qty, open_pos.quantity)

        result = self.trader.place_option_order(alert, qty)

        if result.ok:
            if alert.action is Action.BUY:
                self.store.upsert_open(
                    contract_key=alert.contract_key,
                    symbol=alert.symbol,
                    option_type=alert.option_type.value,
                    strike=alert.strike,
                    expiration=alert.expiration,
                    quantity=qty,
                    entry_price=alert.limit_price,
                    discord_message_id=discord_message_id,
                    webull_order_id=result.client_order_id,
                )
            else:
                self.store.reduce_or_close(alert.contract_key, qty)

        return result
