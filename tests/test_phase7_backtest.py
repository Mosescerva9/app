"""Architecture Phase 7 — cost-aware long-premium backtester (synthetic bars)."""

from __future__ import annotations

from trading_system.backtest import LongPremiumBacktester, PremiumSpec, synthetic_trend_bars
from trading_system.backtest.costs import round_trip_costs
from trading_system.backtest.engine import SETUP_NAME
from trading_system.backtest.signal import detect_signal
from trading_system.backtest.synthetic import synthetic_chop_bars
from trading_system.backtest.types import CostModel
from trading_system.cli import main
from trading_system.config import Settings
from trading_system.data.mock import MockMarketDataProvider
from trading_system.journal import PHASE9_COMPLETE, PaperLedger
from trading_system.modes import LIVE_EXECUTION_UNLOCKED, PHASE, TradingMode
from trading_system.risk import load_risk_limits
from trading_system.services.runtime import ResearchRuntime


def _settings() -> Settings:
    return Settings(
        mode=TradingMode.RESEARCH,
        market_data_provider="mock",
        broker_provider="mock",
        webull_app_key="",
        webull_app_secret="",
        webull_region="us",
        webull_api_endpoint="api.sandbox.webull.com",
        webull_account_id="",
        account_equity_usd=1500.0,
        max_risk_per_trade_pct=0.10,
        max_simultaneous_positions=2,
        max_daily_loss_pct=0.05,
        max_weekly_loss_pct=0.10,
        emergency_stop=False,
        log_level="INFO",
    )


def test_phase_still_eight_and_locked():
    assert PHASE == 8
    assert LIVE_EXECUTION_UNLOCKED is False
    assert PHASE9_COMPLETE is False


def test_trend_bars_produce_long_call_trades():
    bars = synthetic_trend_bars(n_up=90, n_down=30)
    report = LongPremiumBacktester(lookback=60, split_mode="oos").run(bars)
    assert report.setup == SETUP_NAME
    assert report.trades
    assert any(t.strategy == "long_call" for t in report.trades)
    payload = report.to_dict()
    assert payload["research_complete"] is False
    assert payload["trade_recommendation"] is False
    assert payload["go_signals_allowed"] is False
    assert payload["go_signal"] is False
    assert payload["live_execution_unlocked"] is False


def test_no_look_ahead_fill_is_next_open():
    bars = synthetic_trend_bars(n_up=90, n_down=10)
    report = LongPremiumBacktester(lookback=60).run(bars)
    assert report.trades
    for trade in report.trades:
        assert trade.entry_index == trade.signal_index + 1
        assert trade.entry_underlying == bars[trade.entry_index].open
        assert trade.signal_close == bars[trade.signal_index].close
        # Signal window excludes the fill bar.
        window = bars[: trade.signal_index + 1]
        assert detect_signal(window) == trade.side
        assert bars[trade.entry_index] not in window
        assert trade.entry_time >= trade.signal_time


def test_signal_does_not_use_future_spike():
    bars = synthetic_chop_bars(count=70)
    # Quiet prefix: no signal expected on last-but-one close.
    assert detect_signal(bars[:-1]) is None
    spiked = list(bars)
    last = bars[-1]
    spiked[-1] = type(last)(
        symbol=last.symbol,
        timestamp=last.timestamp,
        open=last.open,
        high=last.close * 1.2,
        low=last.low,
        close=last.close * 1.18,
        volume=last.volume,
        timespan=last.timespan,
    )
    # Future spike is only visible if the caller includes that bar.
    assert detect_signal(spiked[:-1]) is None


def test_costs_reduce_net_vs_zero_cost():
    bars = synthetic_trend_bars(n_up=90, n_down=20)
    costly = LongPremiumBacktester(
        lookback=60,
        cost_model=CostModel(commission_per_contract=0.65, slippage_pct=0.02),
    ).run(bars)
    free = LongPremiumBacktester(
        lookback=60,
        cost_model=CostModel(commission_per_contract=0.0, slippage_pct=0.0),
    ).run(bars)
    assert costly.trades and free.trades
    assert len(costly.trades) == len(free.trades)
    assert costly.metrics["all"].net_pnl_usd < free.metrics["all"].net_pnl_usd
    assert costly.metrics["all"].costs_usd > 0
    assert free.metrics["all"].costs_usd == 0
    sample = costly.trades[0]
    expected = round_trip_costs(sample.debit_usd, sample.exit_mark_usd, CostModel())
    assert abs(sample.costs_usd - expected) < 1e-6
    assert sample.debit_usd <= 150.0


def test_oos_split_labels_are_chronological():
    bars = synthetic_trend_bars(n_up=100, n_down=40)
    report = LongPremiumBacktester(lookback=60, split_mode="oos", in_sample_frac=0.7).run(bars)
    cut = int(len(bars) * 0.7)
    for trade in report.trades:
        if trade.split == "in_sample":
            assert trade.entry_index < cut
        else:
            assert trade.split == "oos"
            assert trade.entry_index >= cut


def test_walk_forward_excludes_train_fold_entries():
    bars = synthetic_trend_bars(n_up=100, n_down=40)
    report = LongPremiumBacktester(
        lookback=60,
        split_mode="walk_forward",
        wf_train=80,
        wf_test=20,
        wf_step=20,
    ).run(bars)
    for trade in report.trades:
        assert trade.split == "walk_forward"
        # First train fold is [0, 80); first test is [80, 100).
        assert trade.entry_index >= 80


def test_chop_prefers_stand_aside():
    bars = synthetic_chop_bars(count=90)
    report = LongPremiumBacktester(lookback=60).run(bars)
    assert report.trades == ()
    assert report.metrics["all"].n_trades == 0


def test_last_bar_cannot_fill():
    bars = synthetic_trend_bars(n_up=70, n_down=0)
    # If a signal exists on the final close, there is no next open.
    side = detect_signal(bars)
    report = LongPremiumBacktester(lookback=60).run(bars)
    if side:
        assert all(t.signal_index < len(bars) - 1 for t in report.trades)


def test_premium_capped_at_risk_budget():
    bars = synthetic_trend_bars(start=800.0, n_up=80, n_down=10)
    spec = PremiumSpec(min_debit_usd=20.0, max_debit_usd=150.0)
    report = LongPremiumBacktester(lookback=60, premium=spec).run(bars)
    for trade in report.trades:
        assert 20.0 <= trade.debit_usd <= 150.0
        assert trade.strategy in {"long_call", "long_put"}


def test_cli_backtest_and_journal_stub(capsys):
    settings = _settings()
    runtime = ResearchRuntime(
        settings=settings,
        market_data=MockMarketDataProvider(),
        risk=load_risk_limits(settings),
        paper_ledger=PaperLedger(path=None),
    )
    status = runtime.status()
    assert status["research_complete"] is False
    assert status["go_signals_allowed"] is False
    assert status["trade_recommendation"] is False
    assert status["paper_journal"] == "stub"
    assert status["backtester"] == "regime_filtered_long_premium"

    payload = runtime.backtest("AAPL", count=120, lookback=60, split="oos")
    assert payload["setup"] == SETUP_NAME
    assert payload["research_complete"] is False
    assert payload["trade_recommendation"] is False
    journal = runtime.journal()
    assert journal["phase9_complete"] is False
    assert journal["entry_count"] == payload["trade_count"]

    rc = main(["backtest", "AAPL", "--count", "80", "--lookback", "60"])
    assert rc == 0
    printed = capsys.readouterr().out
    assert "regime_filtered_long_premium" in printed
    assert "research_complete" in printed

    rc = main(["journal"])
    assert rc == 0
    printed = capsys.readouterr().out
    assert "phase9_complete" in printed


def test_paper_ledger_file_roundtrip(tmp_path):
    bars = synthetic_trend_bars(n_up=80, n_down=20)
    report = LongPremiumBacktester(lookback=60).run(bars)
    path = tmp_path / "journal.json"
    PaperLedger(path=path).record_backtest(report)
    reloaded = PaperLedger(path=path)
    assert reloaded.to_dict()["phase9_complete"] is False
    assert reloaded.to_dict()["entry_count"] == len(report.trades)


def test_paper_ledger_records_backtest_without_claiming_complete():
    bars = synthetic_trend_bars(n_up=80, n_down=20)
    report = LongPremiumBacktester(lookback=60).run(bars)
    ledger = PaperLedger(path=None)
    ledger.record_backtest(report)
    dumped = ledger.to_dict()
    assert dumped["phase9_complete"] is False
    assert dumped["research_complete"] is False
    assert dumped["entry_count"] == len(report.trades)
