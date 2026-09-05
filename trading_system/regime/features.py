"""Deterministic feature extraction from OHLCV bars."""

from __future__ import annotations

import math
from statistics import mean, pstdev

from trading_system.models import Bar
from trading_system.regime.types import RegimeFeatures


def _sma(values: list[float], window: int) -> float:
    if len(values) < window:
        window = max(1, len(values))
    return mean(values[-window:])


def _true_ranges(bars: list[Bar]) -> list[float]:
    trs: list[float] = []
    prev_close = bars[0].close
    for bar in bars:
        tr = max(
            bar.high - bar.low,
            abs(bar.high - prev_close),
            abs(bar.low - prev_close),
        )
        trs.append(tr)
        prev_close = bar.close
    return trs


def compute_features(
    bars: list[Bar],
    *,
    symbol: str,
    vix_level: float | None = None,
    vix_change_5d: float | None = None,
    fast: int = 20,
    slow: int = 50,
) -> RegimeFeatures:
    if len(bars) < 25:
        raise ValueError(f"Need at least 25 bars for regime features; got {len(bars)}")

    closes = [b.close for b in bars]
    volumes = [b.volume for b in bars]
    last = closes[-1]
    sma_fast = _sma(closes, fast)
    sma_slow = _sma(closes, slow)

    # Slope of fast SMA over last 5 observations of the SMA series.
    sma_series = [_sma(closes[: i + 1], min(fast, i + 1)) for i in range(len(closes))]
    slope_window = sma_series[-6:]
    sma_fast_slope = (slope_window[-1] - slope_window[0]) / max(abs(slope_window[0]), 1e-9)

    # Trend strength: distance of price vs slow SMA, scaled by ATR%.
    trs = _true_ranges(bars)
    atr = mean(trs[-14:]) if len(trs) >= 14 else mean(trs)
    atr_pct = atr / max(last, 1e-9)
    dist = (last - sma_slow) / max(last, 1e-9)
    trend_strength = max(0.0, min(1.0, abs(dist) / max(atr_pct * 3.0, 1e-6)))

    # Realized volatility (20d annualized, daily bars assumed).
    rets = []
    for i in range(1, len(closes)):
        if closes[i - 1] > 0:
            rets.append(math.log(closes[i] / closes[i - 1]))
    recent = rets[-20:] if len(rets) >= 20 else rets
    realized = (pstdev(recent) * math.sqrt(252)) if len(recent) > 1 else 0.0

    # Volume z-score vs 20d mean.
    vol_window = volumes[-20:] if len(volumes) >= 20 else volumes
    vol_mu = mean(vol_window)
    vol_sd = pstdev(vol_window) if len(vol_window) > 1 else 0.0
    volume_z = ((volumes[-1] - vol_mu) / vol_sd) if vol_sd > 1e-9 else 0.0

    # Choppiness proxy: ATR sum / range over 14 bars (normalized 0-1-ish).
    window = bars[-14:] if len(bars) >= 14 else bars
    hi = max(b.high for b in window)
    lo = min(b.low for b in window)
    atr_sum = sum(_true_ranges(window))
    chop_raw = atr_sum / max(hi - lo, 1e-9)
    choppiness = max(0.0, min(1.0, (chop_raw - 1.0) / 3.0))

    # Momentum persistence: fraction of last 20 closes moving in SMA slope direction.
    direction = 1 if sma_fast_slope >= 0 else -1
    sample = closes[-21:]
    wins = 0
    total = 0
    for i in range(1, len(sample)):
        total += 1
        move = sample[i] - sample[i - 1]
        if (move >= 0 and direction > 0) or (move <= 0 and direction < 0):
            wins += 1
    momentum_persistence = wins / total if total else 0.5

    # Gap frequency: |open-prev_close|/prev_close > 1% over last 20.
    gaps = 0
    gap_n = 0
    for i in range(1, min(21, len(bars))):
        prev = bars[-i - 1] if i + 1 <= len(bars) else None
        cur = bars[-i]
        if prev is None or prev.close <= 0:
            continue
        gap_n += 1
        if abs(cur.open - prev.close) / prev.close > 0.01:
            gaps += 1
    # recount cleanly
    gaps = 0
    gap_n = 0
    for i in range(1, len(bars)):
        if i < len(bars) - 20:
            continue
        prev = bars[i - 1]
        cur = bars[i]
        if prev.close <= 0:
            continue
        gap_n += 1
        if abs(cur.open - prev.close) / prev.close > 0.01:
            gaps += 1
    gap_frequency = gaps / gap_n if gap_n else 0.0

    return RegimeFeatures(
        symbol=symbol.upper(),
        lookback=len(bars),
        last_close=last,
        sma_fast=sma_fast,
        sma_slow=sma_slow,
        sma_fast_slope=sma_fast_slope,
        trend_strength=trend_strength,
        atr_pct=atr_pct,
        realized_vol_20=realized,
        volume_z=volume_z,
        choppiness=choppiness,
        momentum_persistence=momentum_persistence,
        gap_frequency=gap_frequency,
        vix_level=vix_level,
        vix_change_5d=vix_change_5d,
        raw={
            "fast": fast,
            "slow": slow,
            "atr": atr,
        },
    )
