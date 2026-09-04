"""Unit tests for alert parsing and trade engine."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from bot.config import Settings
from bot.engine import TradeEngine
from bot.parser import Action, OptionType, parse_alert
from bot.positions import PositionStore
from bot.webull_trader import WebullOptionsTrader


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        discord_bot_token="test-token",
        discord_guild_id=1,
        discord_channel_ids=frozenset(),
        discord_alert_author_ids=frozenset(),
        webull_app_key="",
        webull_app_secret="",
        webull_account_id="",
        webull_region="us",
        webull_api_endpoint="api.sandbox.webull.com",
        dry_run=True,
        default_quantity=1,
        max_quantity=5,
        buy_slippage=0.05,
        sell_slippage=0.05,
        require_limit_price=True,
        positions_db_path=tmp_path / "positions.db",
        log_level="INFO",
    )


def test_parse_bto_shorthand():
    alert = parse_alert("BTO AAPL 220C 3/21/26 @ 1.25 x2")
    assert alert is not None
    assert alert.action is Action.BUY
    assert alert.symbol == "AAPL"
    assert alert.option_type is OptionType.CALL
    assert alert.strike == 220.0
    assert alert.expiration == "2026-03-21"
    assert alert.limit_price == 1.25
    assert alert.quantity == 2


def test_parse_buy_with_named_expiry():
    alert = parse_alert("BUY TSLA MAR 21 250 PUT @ 8.50")
    assert alert is not None
    assert alert.action is Action.BUY
    assert alert.symbol == "TSLA"
    assert alert.option_type is OptionType.PUT
    assert alert.strike == 250.0
    assert alert.expiration.endswith("-03-21")
    assert alert.limit_price == 8.50


def test_parse_stc_exit():
    alert = parse_alert("STC NVDA 100P 2026-07-17 @ 6.00")
    assert alert is not None
    assert alert.action is Action.SELL
    assert alert.symbol == "NVDA"
    assert alert.option_type is OptionType.PUT
    assert alert.expiration == "2026-07-17"


def test_parse_embed_style():
    text = (
        "Symbol: AAPL\nStrike: 220\nType: CALL\n"
        "Exp: 2026-06-19\nAction: BUY\nPrice: 11.25\nQty: 1"
    )
    alert = parse_alert(text)
    assert alert is not None
    assert alert.symbol == "AAPL"
    assert alert.strike == 220.0
    assert alert.option_type is OptionType.CALL
    assert alert.action is Action.BUY
    assert alert.limit_price == 11.25


def test_ignore_non_alert():
    assert parse_alert("good morning traders") is None


def test_engine_buy_then_sell(settings: Settings):
    store = PositionStore(settings.positions_db_path)
    trader = WebullOptionsTrader(
        app_key="",
        app_secret="",
        account_id="",
        dry_run=True,
        buy_slippage=settings.buy_slippage,
        sell_slippage=settings.sell_slippage,
    )
    engine = TradeEngine(settings, trader, store)

    buy_msg = SimpleNamespace(
        id=101,
        content="BTO AAPL 220C 6/19/26 @ 1.00 x2",
        embeds=[],
    )
    buy_result = engine.handle_message(buy_msg)
    assert buy_result is not None and buy_result.ok
    open_positions = store.list_open()
    assert len(open_positions) == 1
    assert open_positions[0].quantity == 2

    # Duplicate message id ignored
    assert engine.handle_message(buy_msg) is None

    sell_msg = SimpleNamespace(
        id=102,
        content="STC AAPL 220C 6/19/26 @ 1.50 x2",
        embeds=[],
    )
    sell_result = engine.handle_message(sell_msg)
    assert sell_result is not None and sell_result.ok
    assert store.list_open() == []


def test_order_slippage_applied(settings: Settings):
    trader = WebullOptionsTrader(
        app_key="",
        app_secret="",
        account_id="",
        dry_run=True,
        buy_slippage=0.10,
        sell_slippage=0.10,
    )
    alert = parse_alert("BTO AAPL 220C 6/19/26 @ 1.00 x1")
    assert alert is not None
    order = trader.build_order(alert, 1)
    assert order["limit_price"] == "1.10"
    assert order["legs"][0]["option_type"] == "CALL"
