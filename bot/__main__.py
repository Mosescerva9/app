"""Entry point: Discord options alert -> Webull copy trader."""

from __future__ import annotations

import asyncio
import logging
import sys

from bot.config import get_settings
from bot.discord_bot import run_bot
from bot.engine import TradeEngine
from bot.positions import PositionStore
from bot.webull_trader import WebullOptionsTrader


def main() -> int:
    try:
        settings = get_settings()
    except ValueError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 1

    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    log = logging.getLogger("bot")

    store = PositionStore(settings.positions_db_path)
    trader = WebullOptionsTrader(
        app_key=settings.webull_app_key,
        app_secret=settings.webull_app_secret,
        account_id=settings.webull_account_id,
        region=settings.webull_region,
        api_endpoint=settings.webull_api_endpoint,
        dry_run=settings.dry_run,
        buy_slippage=settings.buy_slippage,
        sell_slippage=settings.sell_slippage,
    )
    engine = TradeEngine(settings, trader, store)

    if not settings.dry_run:
        try:
            accounts = trader.ping_account()
            log.info("Webull account check ok: %s", accounts)
        except Exception:  # noqa: BLE001
            log.exception("Webull account check failed — aborting start")
            return 1

    log.info(
        "Starting bot dry_run=%s max_qty=%s buy_slip=%.2f sell_slip=%.2f",
        settings.dry_run,
        settings.max_quantity,
        settings.buy_slippage,
        settings.sell_slippage,
    )
    asyncio.run(run_bot(settings, engine))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
