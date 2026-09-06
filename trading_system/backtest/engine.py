"""Cost-aware long-premium backtester. No look-ahead; chronological OOS / walk-forward."""

from __future__ import annotations

from trading_system.backtest.costs import round_trip_costs
from trading_system.backtest.premium import initial_debit_usd, mark_usd, strike_for
from trading_system.backtest.signal import MIN_BARS, detect_signal
from trading_system.backtest.types import (
    BacktestReport,
    BacktestTrade,
    CostModel,
    PremiumSpec,
    SplitMetrics,
)
from trading_system.models import Bar
from trading_system.risk.limits import RiskLimits


SETUP_NAME = "regime_filtered_long_premium"


def _split_label(entry_index: int, n: int, mode: str, is_frac: float) -> str:
    if mode == "walk_forward":
        return "walk_forward"
    cut = max(MIN_BARS, int(n * is_frac))
    return "in_sample" if entry_index < cut else "oos"


def _walk_forward_keep(entry_index: int, n: int, train: int, test: int, step: int) -> bool:
    """True if entry falls in a walk-forward test fold (not the preceding train fold)."""
    start = 0
    while start + train + test <= n:
        test_lo = start + train
        test_hi = start + train + test
        if test_lo <= entry_index < test_hi:
            return True
        start += step
    # Remainder after the last full fold: treat as a final OOS tail if any.
    last_test_end = 0
    start = 0
    while start + train + test <= n:
        last_test_end = start + train + test
        start += step
    return last_test_end <= entry_index < n


def _exit_underlying(bar: Bar, side: str, stop: float, target: float) -> tuple[float, str] | None:
    """Intrabar exit. Gap through stop fills at open. Stop-first if both touched."""
    if side == "LONG":
        if bar.open <= stop:
            return bar.open, "stop_gap"
        hit_stop = bar.low <= stop
        hit_tgt = bar.high >= target
        if hit_stop and hit_tgt:
            return stop, "stop"
        if hit_stop:
            return stop, "stop"
        if hit_tgt:
            return target, "target"
        return None
    if bar.open >= stop:
        return bar.open, "stop_gap"
    hit_stop = bar.high >= stop
    hit_tgt = bar.low <= target
    if hit_stop and hit_tgt:
        return stop, "stop"
    if hit_stop:
        return stop, "stop"
    if hit_tgt:
        return target, "target"
    return None


def _metrics(label: str, trades: list[BacktestTrade]) -> SplitMetrics:
    if not trades:
        return SplitMetrics(
            label=label,
            n_trades=0,
            wins=0,
            losses=0,
            win_rate=None,
            gross_pnl_usd=0.0,
            costs_usd=0.0,
            net_pnl_usd=0.0,
            avg_net_usd=None,
            max_drawdown_usd=0.0,
            profit_factor=None,
        )
    nets = [t.net_pnl_usd for t in trades]
    wins = sum(1 for x in nets if x > 0)
    losses = sum(1 for x in nets if x <= 0)
    gross = sum(t.gross_pnl_usd for t in trades)
    costs = sum(t.costs_usd for t in trades)
    net = sum(nets)
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for x in nets:
        equity += x
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    pos = sum(x for x in nets if x > 0)
    neg = sum(-x for x in nets if x < 0)
    pf = None if neg <= 1e-12 else pos / neg
    return SplitMetrics(
        label=label,
        n_trades=len(trades),
        wins=wins,
        losses=losses,
        win_rate=wins / len(trades),
        gross_pnl_usd=gross,
        costs_usd=costs,
        net_pnl_usd=net,
        avg_net_usd=net / len(trades),
        max_drawdown_usd=abs(max_dd),
        profit_factor=pf,
    )


class LongPremiumBacktester:
    """Regime-filtered equity signal → synthetic long call/put. RESEARCH only."""

    def __init__(
        self,
        *,
        lookback: int = 60,
        cost_model: CostModel | None = None,
        premium: PremiumSpec | None = None,
        risk: RiskLimits | None = None,
        split_mode: str = "oos",
        in_sample_frac: float = 0.7,
        wf_train: int = 80,
        wf_test: int = 20,
        wf_step: int = 20,
    ) -> None:
        if lookback < MIN_BARS:
            raise ValueError(f"lookback must be >= {MIN_BARS}")
        self.lookback = lookback
        self.cost_model = cost_model or CostModel()
        self.premium = premium or PremiumSpec()
        self.risk = risk
        mode = (split_mode or "oos").strip().lower()
        if mode not in {"oos", "walk_forward"}:
            raise ValueError("split_mode must be oos or walk_forward")
        self.split_mode = mode
        self.in_sample_frac = in_sample_frac
        self.wf_train = wf_train
        self.wf_test = wf_test
        self.wf_step = wf_step

    def run(self, bars: list[Bar], *, symbol: str | None = None) -> BacktestReport:
        if not bars:
            raise ValueError("Need bars to backtest")
        series = list(bars)
        key = (symbol or series[0].symbol).upper()
        n = len(series)
        trades: list[BacktestTrade] = []
        i = self.lookback - 1
        notes = [
            "Architecture Phase 7 backtester: regime-filtered equity signal → synthetic long premium.",
            "Signal uses only bars through that close. Fill is the next bar's open (no look-ahead).",
            "Option P&L is a decaying-extrinsic proxy, not a historical OPRA chain.",
            "Costs: commission per contract (round trip) + slippage_pct of debit/mark each side.",
            f"split_mode={self.split_mode}. RESEARCH only — not a trade recommendation.",
        ]

        while i < n - 1:
            window = series[: i + 1]
            side = detect_signal(window)
            if side is None:
                i += 1
                continue
            entry_i = i + 1
            entry_bar = series[entry_i]
            entry_px = entry_bar.open
            if entry_px <= 0:
                i += 1
                continue
            strike = strike_for(entry_px, side, self.premium)
            debit = initial_debit_usd(entry_px, self.premium, self.risk)
            if side == "LONG":
                stop = entry_px * (1.0 - self.premium.stop_pct)
                target = entry_px * (1.0 + self.premium.target_pct)
                strategy = "long_call"
            else:
                stop = entry_px * (1.0 + self.premium.stop_pct)
                target = entry_px * (1.0 - self.premium.target_pct)
                strategy = "long_put"

            exit_i = entry_i
            exit_px = entry_bar.close
            reason = "time"
            held = 0
            j = entry_i
            while j < n and held < self.premium.hold_bars:
                bar = series[j]
                hit = _exit_underlying(bar, side, stop, target)
                if hit is not None:
                    exit_px, reason = hit
                    exit_i = j
                    break
                exit_px = bar.close
                exit_i = j
                held += 1
                j += 1
            else:
                reason = "time"

            bars_held = max(1, exit_i - entry_i + 1)
            exit_mark = mark_usd(
                underlying=exit_px,
                strike=strike,
                side=side,
                debit_usd=debit,
                bars_held=bars_held,
                hold_bars=self.premium.hold_bars,
            )
            costs = round_trip_costs(debit, exit_mark, self.cost_model)
            gross = exit_mark - debit
            net = gross - costs
            split = _split_label(entry_i, n, self.split_mode, self.in_sample_frac)
            if self.split_mode == "walk_forward" and not _walk_forward_keep(
                entry_i, n, self.wf_train, self.wf_test, self.wf_step
            ):
                # Still simulate the path so we don't look ahead, but exclude train-fold entries.
                i = exit_i + 1
                continue
            trades.append(
                BacktestTrade(
                    symbol=key,
                    side=side,
                    strategy=strategy,
                    signal_index=i,
                    entry_index=entry_i,
                    exit_index=exit_i,
                    signal_time=series[i].timestamp,
                    entry_time=entry_bar.timestamp,
                    exit_time=series[exit_i].timestamp,
                    signal_close=series[i].close,
                    entry_underlying=entry_px,
                    exit_underlying=exit_px,
                    strike=strike,
                    debit_usd=debit,
                    exit_mark_usd=exit_mark,
                    gross_pnl_usd=gross,
                    costs_usd=costs,
                    net_pnl_usd=net,
                    exit_reason=reason,
                    split=split,
                    notes=(
                        "Fill at next open after signal close.",
                        f"bars_held={bars_held}",
                    ),
                )
            )
            i = exit_i + 1

        metrics = {
            "all": _metrics("all", trades),
            "in_sample": _metrics("in_sample", [t for t in trades if t.split == "in_sample"]),
            "oos": _metrics("oos", [t for t in trades if t.split == "oos"]),
            "walk_forward": _metrics(
                "walk_forward", [t for t in trades if t.split == "walk_forward"]
            ),
        }
        if not trades:
            notes.append("No trades: regime filter stood aside or series too short after lookback.")
        return BacktestReport(
            symbol=key,
            setup=SETUP_NAME,
            bar_count=n,
            lookback=self.lookback,
            split_mode=self.split_mode,
            cost_model=self.cost_model,
            premium=self.premium,
            trades=tuple(trades),
            metrics=metrics,
            notes=tuple(notes),
        )
