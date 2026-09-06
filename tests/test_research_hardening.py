"""Research hardening: bars, rejects, option-chain adapter, account errors, $150 risk."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from trading_system.data.bars import (
    bars_from_payload,
    categories_to_try,
    ensure_chronological_bars,
    extract_bar_rows,
    resolve_equity_category,
)
from trading_system.data.mock import MockMarketDataProvider
from trading_system.data.webull import WebullMarketDataProvider
from trading_system.models import Bar, utc_now
from trading_system.modes import LIVE_EXECUTION_UNLOCKED
from trading_system.regime.classifier import classify_regime
from trading_system.regime.features import compute_features
from trading_system.regime.types import MarketRegime
from trading_system.scanner.features import extract_symbol_features
from trading_system.options.filters import filter_contract
from trading_system.options.types import (
    OptionContract,
    is_standard_occ_option_symbol,
    normalize_occ_option_symbol,
    occ_symbol,
)
from trading_system.options.webull_chain import WebullOptionChainProvider, _merge_contract, _normalize_contract_spec
from trading_system.risk.limits import RiskLimits
from trading_system.scanner.engine import OpportunityScanner
from trading_system.webull_support import WebullApiError, collect_account_ids, require_ok


def _limits(*, equity: float = 1500.0, pct: float = 0.10) -> RiskLimits:
    return RiskLimits(
        account_equity_usd=equity,
        max_risk_per_trade_pct=pct,
        max_simultaneous_positions=2,
        max_daily_loss_pct=0.05,
        max_weekly_loss_pct=0.10,
        emergency_stop=False,
    )


def _contract(*, mid: float, right: str = "CALL") -> OptionContract:
    as_of = datetime(2026, 9, 5, tzinfo=timezone.utc)
    expiration = (as_of + timedelta(days=45)).date()
    return OptionContract(
        underlying="TEST",
        right=right,
        expiration=expiration,
        strike=100.0,
        bid=mid - 0.02,
        ask=mid + 0.02,
        last=mid,
        mid=mid,
        volume=500,
        open_interest=2000,
        implied_volatility=0.28,
        delta=0.35 if right == "CALL" else -0.35,
        gamma=0.01,
        theta=-0.02,
        vega=0.05,
        as_of=as_of,
        symbol=occ_symbol("TEST", expiration, right, 100.0),
    )


class _FakeResponse:
    def __init__(self, body, status_code=200):
        self._body = body
        self.status_code = status_code

    def json(self):
        return self._body


def test_execution_stays_locked():
    assert LIVE_EXECUTION_UNLOCKED is False


def test_risk_budget_is_one_fifty_on_fifteen_hundred():
    risk = _limits()
    assert risk.max_risk_per_trade_usd == 150.0


def test_premium_one_fifty_fits_new_budget_not_old_forty():
    contract = _contract(mid=1.50)  # $150 cash outlay
    assert filter_contract(contract, side_bias="LONG", limits=_limits(equity=1000, pct=0.04)).ok is False
    assert filter_contract(contract, side_bias="LONG", limits=_limits()).ok is True


def _spy_webull_newest_first(*, n: int = 90, newest: float = 770.19, oldest: float = 709.0) -> list[Bar]:
    """Operator-shaped series: Webull get_history_bar order (newest → oldest)."""
    now = utc_now()
    step = (newest - oldest) / max(n - 1, 1)
    chrono: list[Bar] = []
    for i in range(n):
        close = oldest + i * step
        open_px = close - 0.4
        chrono.append(
            Bar(
                symbol="SPY",
                timestamp=now - timedelta(days=n - 1 - i),
                open=open_px,
                high=close + 0.6,
                low=close - 0.8,
                close=round(close, 2) if i not in {0, n - 1} else close,
                volume=1_000_000 + i,
                timespan="D",
            )
        )
    chrono[0] = Bar(
        symbol="SPY",
        timestamp=chrono[0].timestamp,
        open=oldest - 0.4,
        high=oldest + 0.6,
        low=oldest - 0.8,
        close=oldest,
        volume=1_000_000,
        timespan="D",
    )
    chrono[-1] = Bar(
        symbol="SPY",
        timestamp=chrono[-1].timestamp,
        open=newest - 0.4,
        high=newest + 0.6,
        low=newest - 0.8,
        close=newest,
        volume=1_000_000 + n,
        timespan="D",
    )
    newest_first = list(reversed(chrono))
    assert newest_first[0].close == newest
    assert newest_first[-1].close == oldest
    return newest_first


def test_reverse_chronological_bars_use_newest_close():
    """Regression: newest→oldest input must still yield last_close=770.19, not 709."""
    raw = _spy_webull_newest_first()
    assert raw[0].close == pytest.approx(770.19)
    assert raw[-1].close == pytest.approx(709.0)

    ordered = ensure_chronological_bars(raw)
    assert ordered[-1].close == pytest.approx(770.19)
    assert ordered[0].close == pytest.approx(709.0)
    assert ordered[0].timestamp < ordered[-1].timestamp

    regime_feats = compute_features(raw, symbol="SPY")
    assert regime_feats.last_close == pytest.approx(770.19)
    scan_feats = extract_symbol_features(raw, symbol="SPY")
    assert scan_feats.last == pytest.approx(770.19)

    report = classify_regime(regime_feats, benchmark="SPY")
    assert report.regime is not MarketRegime.STRONG_BEAR
    assert report.features.last_close == pytest.approx(770.19)


def test_history_bar_request_uses_int_count_and_omits_session_kwargs():
    """Live api.webull.com 400s on count=str / real_time_required / trading_sessions."""
    calls: list[dict] = []

    class _Md:
        def get_history_bar(self, symbol, category, timespan, **kwargs):
            calls.append(
                {"symbol": symbol, "category": category, "timespan": timespan, **kwargs}
            )
            return _FakeResponse(
                [
                    {
                        "time": "2026-09-04T20:00:00.000+0000",
                        "open": "768",
                        "high": "772",
                        "low": "765",
                        "close": "770.19",
                        "volume": "10",
                    },
                    {
                        "time": "2026-04-15T20:00:00.000+0000",
                        "open": "700",
                        "high": "712",
                        "low": "698",
                        "close": "709",
                        "volume": "8",
                    },
                ]
            )

    provider = WebullMarketDataProvider.__new__(WebullMarketDataProvider)
    provider._data = SimpleNamespace(market_data=_Md())
    provider._endpoint = "api.webull.com"
    bars = provider._history_bars_once("SPY", timespan="D", count=10, category="US_ETF")
    assert len(calls) == 1
    assert calls[0]["count"] == 10
    assert isinstance(calls[0]["count"], int)
    assert "real_time_required" not in calls[0]
    assert "trading_sessions" not in calls[0]
    assert bars[-1].close == pytest.approx(770.19)
    assert bars[0].close == pytest.approx(709.0)


def test_nested_result_envelope_and_newest_first_sorted():
    # Official batch/single envelope: result[{symbol, result:[bars newest-first]}]
    newest = {"time": "2026-09-04T20:00:00.000+0000", "open": "768", "high": "772", "low": "765", "close": "770", "volume": "10"}
    oldest = {"time": "2026-04-15T20:00:00.000+0000", "open": "700", "high": "712", "low": "698", "close": "709", "volume": "8"}
    payload = {"result": [{"symbol": "SPY", "instrument_id": "1", "result": [newest, oldest]}]}
    rows = extract_bar_rows(payload)
    assert len(rows) == 2
    bars = bars_from_payload(payload, symbol="SPY", timespan="D")
    assert [b.close for b in bars] == [709.0, 770.0]
    assert bars[-1].close == 770.0
    assert bars[0].timestamp < bars[-1].timestamp


def test_csv_bar_string_ohlc_order():
    payload = {
        "bars": [
            "1710000000000,100,105,99,104,1000",
            "1710086400000,104,106,103,105,1100",
        ]
    }
    bars = bars_from_payload(payload, symbol="AAPL", timespan="D")
    assert len(bars) == 2
    assert bars[0].open == 100.0
    assert bars[0].high == 105.0
    assert bars[0].close == 104.0
    assert bars[-1].close == 105.0


def test_etf_category_resolution():
    assert resolve_equity_category("SPY") == "US_ETF"
    assert resolve_equity_category("AAPL") == "US_STOCK"
    assert resolve_equity_category("SPY", "US_FUTURES") == "US_FUTURES"
    assert categories_to_try("SPY")[0] == "US_ETF"
    assert "US_STOCK" in categories_to_try("SPY")


def test_require_ok_surfaces_us_option_entitlement():
    res = _FakeResponse(
        {"error_code": "MARKET_DATA_NOT_SUBSCRIBED", "message": "subscribe to US_OPTION"},
        status_code=403,
    )
    with pytest.raises(WebullApiError, match="MARKET_DATA_NOT_SUBSCRIBED") as exc:
        require_ok(res, "get_option_snapshot", endpoint="api.webull.com")
    assert "US_OPTION" in str(exc.value)
    assert "get_option_contracts" in str(exc.value)


def test_webull_chain_surfaces_snapshot_403_after_listing_contracts():
    class _Instrument:
        def get_option_contracts(self, **kwargs):
            return _FakeResponse(
                [
                    {
                        "symbol": "SPY260918C00770000",
                        "option_type": "CALL",
                        "strike_price": "770",
                        "expire_date": "2026-10-16",
                        "instrument_id": "1",
                    }
                ]
            )

    class _OptionMd:
        def get_option_snapshot(self, symbols, category):
            return _FakeResponse(
                {"error_code": "MARKET_DATA_NOT_SUBSCRIBED", "message": "subscribe to US_OPTION"},
                status_code=403,
            )

    provider = WebullOptionChainProvider(
        data_client=SimpleNamespace(instrument=_Instrument(), option_market_data=_OptionMd()),
        min_dte=30,
        max_dte=60,
    )
    with pytest.raises(WebullApiError, match="MARKET_DATA_NOT_SUBSCRIBED") as exc:
        provider.get_chain("SPY", as_of=datetime(2026, 9, 6, tzinfo=timezone.utc), spot=770.19)
    assert "SPY260918C00770000" in str(exc.value)
    assert "Listed 1 OCC contracts" in str(exc.value)
    assert "US_OPTION" in str(exc.value)


def test_require_ok_surfaces_access_denied():
    res = _FakeResponse({"error_code": "ACCOUNT_ACCESS_DENIED", "message": "nope"}, status_code=200)
    with pytest.raises(WebullApiError, match="ACCOUNT_ACCESS_DENIED") as exc:
        require_ok(res, "get_account_balance", endpoint="api.sandbox.webull.com")
    assert "get_account_list" in str(exc.value)
    assert "sandbox" in str(exc.value).lower()


def test_collect_account_ids():
    ids = collect_account_ids(
        [{"account_id": "AAA"}, {"accountId": "BBB"}, {"id": "AAA"}]
    )
    assert ids == ["AAA", "BBB"]


def test_scan_empty_includes_reject_diagnosis():
    scanner = OpportunityScanner(
        MockMarketDataProvider(),
        universe=["AAPL", "MSFT", "NVDA"],
        min_score=99.9,
        max_results=3,
    )
    payload = scanner.scan().to_dict()
    assert payload["opportunity_count"] == 0
    assert payload["reject_count"] >= 1
    assert payload["reject_counts"]
    assert "empty_scan_diagnosis" in payload
    assert payload["empty_scan_diagnosis"]["summary"]
    assert any("Empty Top" in n or "opportunity_count=0" in n for n in payload["notes"])
    for row in payload["rejects"]:
        assert row["reason"] in {"no_setup", "regime_fit", "score_floor", "error"}


def test_standard_occ_keeps_roots_and_skips_adjusted_series():
    assert is_standard_occ_option_symbol("NVDA261016C00230000", underlying="NVDA")
    assert not is_standard_occ_option_symbol("2NVDA261016C00210000", underlying="NVDA")
    assert not is_standard_occ_option_symbol("2TSLA261016P00306500", underlying="TSLA")
    assert not is_standard_occ_option_symbol("2AAPL261009C00320430", underlying="AAPL")
    assert normalize_occ_option_symbol("NVDA261016C00230000", underlying="NVDA") == "NVDA261016C00230000"
    # Do not strip the leading 2 and pretend — skip adjusted series.
    assert normalize_occ_option_symbol("2NVDA261016C00210000", underlying="NVDA") == ""
    assert (
        normalize_occ_option_symbol(
            "2NVDA261016C00210000",
            underlying="NVDA",
            expiration=date(2026, 10, 16),
            right="CALL",
            strike=210.0,
        )
        == ""
    )


def test_webull_chain_sends_only_standard_occ_to_snapshot():
    seen: list[str] = []

    class _Instrument:
        def get_option_contracts(self, **kwargs):
            return _FakeResponse(
                [
                    {
                        "symbol": "NVDA261016C00230000",
                        "option_type": "CALL",
                        "strike_price": "230",
                        "expire_date": "2026-10-16",
                        "instrument_id": "1",
                    },
                    {
                        "symbol": "2NVDA261016C00210000",
                        "option_type": "CALL",
                        "strike_price": "210",
                        "expire_date": "2026-10-16",
                        "instrument_id": "2",
                    },
                    {
                        "symbol": "2NVDA261016P00210000",
                        "option_type": "PUT",
                        "strike_price": "210",
                        "expire_date": "2026-10-16",
                        "instrument_id": "3",
                    },
                    {
                        "symbol": "NVDA261016P00225000",
                        "option_type": "PUT",
                        "strike_price": "225",
                        "expire_date": "2026-10-16",
                        "instrument_id": "4",
                    },
                ]
            )

    class _OptionMd:
        def get_option_snapshot(self, symbols, category):
            seen.extend(symbols)
            return _FakeResponse(
                [
                    {
                        "symbol": "NVDA261016C00230000",
                        "bid": "4.0",
                        "ask": "4.2",
                        "delta": "0.35",
                        "imp_vol": "0.4",
                        "open_interest": "1000",
                    },
                    {
                        "symbol": "NVDA261016P00225000",
                        "bid": "8.0",
                        "ask": "8.3",
                        "delta": "-0.33",
                        "imp_vol": "0.45",
                        "open_interest": "800",
                    },
                ]
            )

    provider = WebullOptionChainProvider(
        data_client=SimpleNamespace(instrument=_Instrument(), option_market_data=_OptionMd()),
        min_dte=30,
        max_dte=60,
    )
    chain = provider.get_chain("NVDA", as_of=datetime(2026, 9, 6, tzinfo=timezone.utc), spot=230.0)
    assert seen == ["NVDA261016C00230000", "NVDA261016P00225000"]
    assert all(s.startswith("NVDA") and not s.startswith("2") for s in seen)
    assert {c.symbol for c in chain} == {"NVDA261016C00230000", "NVDA261016P00225000"}


def test_webull_chain_merges_contracts_and_snapshots():
    class _Instrument:
        def get_option_contracts(self, **kwargs):
            return _FakeResponse(
                [
                    {
                        "symbol": "AAPL260620C00150000",
                        "option_type": "CALL",
                        "strike_price": "150",
                        "expire_date": "2026-10-16",
                        "instrument_id": "1",
                    },
                    {
                        "symbol": "AAPL260620P00150000",
                        "option_type": "PUT",
                        "strike_price": "150",
                        "expire_date": "2026-10-16",
                        "instrument_id": "2",
                    },
                ]
            )

    class _OptionMd:
        def get_option_snapshot(self, symbols, category):
            return _FakeResponse(
                [
                    {
                        "symbol": "AAPL260620C00150000",
                        "bid": "1.20",
                        "ask": "1.30",
                        "price": "1.25",
                        "delta": "0.34",
                        "gamma": "0.01",
                        "theta": "-0.02",
                        "vega": "0.08",
                        "imp_vol": "0.29",
                        "open_interest": "2500",
                        "volume": "400",
                    },
                    {
                        "symbol": "AAPL260620P00150000",
                        "bid": "1.10",
                        "ask": "1.22",
                        "price": "1.16",
                        "delta": "-0.33",
                        "imp_vol": "0.31",
                        "open_interest": "1800",
                        "volume": "200",
                    },
                ]
            )

    provider = WebullOptionChainProvider(
        data_client=SimpleNamespace(instrument=_Instrument(), option_market_data=_OptionMd()),
        min_dte=30,
        max_dte=60,
    )
    as_of = datetime(2026, 9, 6, tzinfo=timezone.utc)
    chain = provider.get_chain("AAPL", as_of=as_of, spot=150.0)
    assert len(chain) == 2
    rights = {c.right for c in chain}
    assert rights == {"CALL", "PUT"}
    call = next(c for c in chain if c.right == "CALL")
    assert call.exchange == "WEBULL"
    assert call.mid == pytest.approx(1.25)
    assert call.open_interest == 2500
    assert 30 <= call.dte <= 60
    assert call.premium_per_contract_usd == pytest.approx(125.0)


def test_normalize_contract_spec_aliases():
    spec = _normalize_contract_spec(
        {
            "optionType": "PUT",
            "strikePrice": "200.5",
            "expiration_date": "2026-10-17",
            "option_symbol": "MSFT261017P00200500",
        },
        "MSFT",
    )
    assert spec is not None
    assert spec.right == "PUT"
    assert spec.strike == 200.5
    assert spec.expiration == date(2026, 10, 17)


def test_runtime_account_mismatch_is_explicit():
    from trading_system.broker.mock import MockBrokerReadClient
    from trading_system.config import Settings
    from trading_system.modes import TradingMode
    from trading_system.risk import load_risk_limits
    from trading_system.services.runtime import ResearchRuntime

    settings = Settings(
        mode=TradingMode.RESEARCH,
        market_data_provider="mock",
        broker_provider="mock",
        webull_app_key="",
        webull_app_secret="",
        webull_region="us",
        webull_api_endpoint="api.sandbox.webull.com",
        webull_account_id="PAPER-FROM-APP",
        account_equity_usd=1500.0,
        max_risk_per_trade_pct=0.10,
        max_simultaneous_positions=2,
        max_daily_loss_pct=0.05,
        max_weekly_loss_pct=0.10,
        emergency_stop=False,
        log_level="INFO",
    )
    runtime = ResearchRuntime(
        settings=settings,
        market_data=MockMarketDataProvider(),
        broker=MockBrokerReadClient(equity=1500),
        risk=load_risk_limits(settings),
    )
    payload = runtime.account_overview()
    assert payload["error_code"] == "ACCOUNT_ID_ENDPOINT_MISMATCH"
    assert "PAPER-FROM-APP" in payload["error"]
    assert "MOCK-001" in payload["available_account_ids"]
    assert runtime.options_engine.chain_provider.__class__.__name__ == "MockOptionChainProvider"
    assert LIVE_EXECUTION_UNLOCKED is False


def test_merge_contract_uses_bid_ask_mid():
    spec = _normalize_contract_spec(
        {
            "option_type": "CALL",
            "strike_price": "100",
            "expire_date": "2026-10-16",
            "symbol": "AAA261016C00100000",
        },
        "AAA",
    )
    contract = _merge_contract(
        spec,
        {"bid": "0.90", "ask": "1.10", "imp_vol": "0.2", "delta": "0.3"},
        as_of=datetime(2026, 9, 6, tzinfo=timezone.utc),
    )
    assert contract.mid == pytest.approx(1.0)
    assert contract.exchange == "WEBULL"
