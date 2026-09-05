"""Market Regime Engine — orchestrates features + classification."""

from __future__ import annotations

import logging

from trading_system.data.base import MarketDataProvider
from trading_system.models import Bar
from trading_system.regime.classifier import classify_regime
from trading_system.regime.features import compute_features
from trading_system.regime.types import RegimeReport

logger = logging.getLogger(__name__)


class MarketRegimeEngine:
    def __init__(
        self,
        market_data: MarketDataProvider,
        *,
        benchmark: str = "SPY",
        lookback: int = 90,
        vix_symbol: str = "VIX",
    ) -> None:
        self.market_data = market_data
        self.benchmark = benchmark.upper()
        self.lookback = lookback
        self.vix_symbol = vix_symbol.upper()

    def analyze(
        self,
        bars: list[Bar] | None = None,
        *,
        benchmark: str | None = None,
    ) -> RegimeReport:
        symbol = (benchmark or self.benchmark).upper()
        if bars is None:
            bars = self.market_data.get_history_bars(symbol, timespan="D", count=self.lookback)
        if len(bars) < 25:
            raise ValueError(f"Insufficient bars for regime analysis: {len(bars)}")

        vix_level, vix_change, vix_note = self._try_vix()
        features = compute_features(
            bars,
            symbol=symbol,
            vix_level=vix_level,
            vix_change_5d=vix_change,
        )
        report = classify_regime(features, benchmark=symbol)
        if vix_note:
            report = RegimeReport(
                regime=report.regime,
                confidence=report.confidence,
                benchmark=report.benchmark,
                features=report.features,
                evidence=report.evidence,
                strategies_favored=report.strategies_favored,
                strategies_avoided=report.strategies_avoided,
                risks=report.risks,
                notes=[*report.notes, vix_note],
            )
        return report

    def _try_vix(self) -> tuple[float | None, float | None, str | None]:
        """Best-effort VIX read. Failures are non-fatal."""
        try:
            snaps = self.market_data.get_snapshots([self.vix_symbol])
            if not snaps or snaps[0].last is None:
                return None, None, f"No snapshot for {self.vix_symbol}"
            level = float(snaps[0].last)
            change = None
            try:
                vix_bars = self.market_data.get_history_bars(
                    self.vix_symbol, timespan="D", count=6
                )
                if len(vix_bars) >= 6 and vix_bars[-6].close:
                    change = level - float(vix_bars[-6].close)
            except Exception:  # noqa: BLE001
                change = None
            return level, change, None
        except Exception as exc:  # noqa: BLE001
            logger.info("VIX fetch skipped: %s", exc)
            return None, None, f"VIX fetch failed ({exc}); using realized vol only"
