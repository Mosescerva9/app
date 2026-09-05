"""Per-symbol OHLCV feature extraction for opportunity scoring."""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import mean, pstdev

from trading_system.models import Bar


@dataclass(frozen=True)
class SymbolFeatures:
    symbol: str
    last: float
    ret_5d: float
    ret_20d: float
    sma_20: float
    sma_50: float
    above_sma_20: bool
    above_sma_50: bool
    atr_pct: float
    realized_vol_20: float
    volume_z: float
    distance_from_20d_high_pct: float
    distance_from_20d_low_pct: float
    pullback_from_high_pct: float
    trend_score: float
    momentum_score: float


def extract_symbol_features(bars: list[Bar], *, symbol: str) -> SymbolFeatures:
    if len(bars) < 30:
        raise ValueError(f"{symbol}: need >=30 bars, got {len(bars)}")

    closes = [b.close for b in bars]
    volumes = [float(b.volume) for b in bars]
    last = closes[-1]
    sma_20 = mean(closes[-20:])
    sma_50 = mean(closes[-50:]) if len(closes) >= 50 else mean(closes)

    ret_5d = (last / closes[-6] - 1.0) if len(closes) >= 6 else 0.0
    ret_20d = (last / closes[-21] - 1.0) if len(closes) >= 21 else 0.0

    trs: list[float] = []
    prev = closes[0]
    for bar in bars[-20:]:
        tr = max(bar.high - bar.low, abs(bar.high - prev), abs(bar.low - prev))
        trs.append(tr)
        prev = bar.close
    atr = mean(trs) if trs else 0.0
    atr_pct = atr / max(last, 1e-9)

    rets: list[float] = []
    for i in range(1, len(closes)):
        if closes[i - 1] > 0:
            rets.append(math.log(closes[i] / closes[i - 1]))
    sample = rets[-20:] if len(rets) >= 20 else rets
    realized = pstdev(sample) * math.sqrt(252) if len(sample) > 1 else 0.0

    vol_w = volumes[-20:]
    vol_mu = mean(vol_w)
    vol_sd = pstdev(vol_w) if len(vol_w) > 1 else 0.0
    volume_z = ((volumes[-1] - vol_mu) / vol_sd) if vol_sd > 1e-9 else 0.0

    high_20 = max(b.high for b in bars[-20:])
    low_20 = min(b.low for b in bars[-20:])
    dist_high = (last / high_20 - 1.0) if high_20 else 0.0
    dist_low = (last / low_20 - 1.0) if low_20 else 0.0
    pullback = (high_20 - last) / high_20 if high_20 else 0.0

    trend = 50.0
    if last > sma_20:
        trend += 15
    if last > sma_50:
        trend += 15
    if sma_20 > sma_50:
        trend += 10
    trend += max(-10.0, min(10.0, ret_20d * 100))
    trend = max(0.0, min(100.0, trend))

    momentum = max(0.0, min(100.0, 50.0 + ret_5d * 400 + ret_20d * 150))

    return SymbolFeatures(
        symbol=symbol.upper(),
        last=last,
        ret_5d=ret_5d,
        ret_20d=ret_20d,
        sma_20=sma_20,
        sma_50=sma_50,
        above_sma_20=last >= sma_20,
        above_sma_50=last >= sma_50,
        atr_pct=atr_pct,
        realized_vol_20=realized,
        volume_z=volume_z,
        distance_from_20d_high_pct=dist_high,
        distance_from_20d_low_pct=dist_low,
        pullback_from_high_pct=pullback,
        trend_score=trend,
        momentum_score=momentum,
    )
