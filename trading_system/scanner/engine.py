"""Opportunity scanner — ranks liquid symbols under the current market regime."""

from __future__ import annotations

import logging

from trading_system.data.base import MarketDataProvider
from trading_system.regime.engine import MarketRegimeEngine
from trading_system.regime.types import MarketRegime, RegimeReport
from trading_system.scanner.features import extract_symbol_features
from trading_system.scanner.scoring import (
    choose_setup_and_levels,
    combine_scores,
    score_crowding_risk,
    score_liquidity,
    score_regime_fit,
    score_risk_reward,
)
from trading_system.scanner.types import (
    DEFAULT_UNIVERSE,
    Direction,
    Opportunity,
    ScanReport,
    SetupType,
    SymbolReject,
)

logger = logging.getLogger(__name__)


class OpportunityScanner:
    def __init__(
        self,
        market_data: MarketDataProvider,
        *,
        universe: tuple[str, ...] | list[str] | None = None,
        lookback: int = 90,
        min_score: float = 55.0,
        max_results: int = 10,
        benchmark: str = "SPY",
    ) -> None:
        self.market_data = market_data
        self.universe = tuple(s.upper() for s in (universe or DEFAULT_UNIVERSE))
        self.lookback = lookback
        self.min_score = min_score
        self.max_results = max_results
        self.benchmark = benchmark.upper()
        self.regime_engine = MarketRegimeEngine(
            market_data, benchmark=self.benchmark, lookback=lookback
        )

    def scan(self, *, regime_report: RegimeReport | None = None) -> ScanReport:
        regime_report = regime_report or self.regime_engine.analyze()
        regime = regime_report.regime
        notes = [
            "Phase 4 scanner uses OHLCV + regime only.",
            "options_quality / catalyst / fundamental excluded until later phases.",
            "Results are RESEARCH candidates — not trade orders.",
        ]
        if regime in {MarketRegime.CHOPPY, MarketRegime.EVENT_DRIVEN, MarketRegime.UNKNOWN}:
            notes.append(f"Regime={regime.value}: prefer caution / fewer setups.")

        opportunities: list[Opportunity] = []
        rejects: list[SymbolReject] = []
        for symbol in self.universe:
            try:
                scored = self._score_symbol(symbol, regime_report)
            except Exception as exc:  # noqa: BLE001
                logger.info("Skip %s: %s", symbol, exc)
                notes.append(f"Skipped {symbol}: {exc}")
                rejects.append(SymbolReject(symbol, "error", str(exc)))
                continue
            if isinstance(scored, SymbolReject):
                rejects.append(scored)
                continue
            opportunities.append(scored)

        opportunities.sort(key=lambda o: o.scores.overall, reverse=True)
        selected = [o for o in opportunities if o.decision != "REJECT"][: self.max_results]
        if not selected:
            counts: dict[str, int] = {}
            for row in rejects:
                counts[row.reason] = counts.get(row.reason, 0) + 1
            summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "none"
            notes.append(
                f"Empty Top {self.max_results}: opportunity_count=0. Rejects: {summary}."
            )

        return ScanReport(
            benchmark=self.benchmark,
            regime=regime.value,
            regime_confidence=regime_report.confidence,
            universe_size=len(self.universe),
            opportunities=selected,
            notes=notes,
            rejects=rejects,
        )

    def _score_symbol(
        self, symbol: str, regime_report: RegimeReport
    ) -> Opportunity | SymbolReject:
        bars = self.market_data.get_history_bars(symbol, timespan="D", count=self.lookback)
        features = extract_symbol_features(bars, symbol=symbol)
        setup, direction, entry, stop, target = choose_setup_and_levels(
            features, regime_report.regime
        )

        if setup is SetupType.STAND_ASIDE or direction is Direction.NONE:
            return SymbolReject(
                symbol,
                "no_setup",
                f"stand_aside under {regime_report.regime.value}",
            )

        liquidity = score_liquidity(features)
        crowding = score_crowding_risk(features)
        regime_fit = score_regime_fit(features, regime_report.regime, direction=direction)
        rr_score = score_risk_reward(entry, stop, target)
        risk = abs(entry - stop)
        reward = abs(target - entry)
        rr = (reward / risk) if risk > 1e-9 else None

        scores = combine_scores(
            technical=features.trend_score,
            momentum=features.momentum_score,
            liquidity=liquidity,
            regime_fit=regime_fit,
            risk_reward=rr_score,
            crowding_risk=crowding,
        )

        why = [
            f"setup={setup.value}",
            f"trend_score={features.trend_score:.1f}",
            f"momentum_score={features.momentum_score:.1f}",
            f"regime_fit={regime_fit:.1f} under {regime_report.regime.value}",
            f"RR≈{rr:.2f}" if rr is not None else "RR unavailable",
        ]
        do_not = [
            f"overall score < {self.min_score}",
            "regime flips against setup",
            "liquidity/crowding deteriorates",
            "stop distance exceeds risk budget",
        ]
        invalidation = [
            f"close beyond stop {stop:.2f}",
            "breakdown of SMA structure supporting setup",
        ]

        if regime_fit < 35:
            return SymbolReject(
                symbol,
                "regime_fit",
                f"regime_fit={regime_fit:.1f} < 35 under {regime_report.regime.value} "
                f"for {direction.value} {setup.value}",
            )
        if scores.overall < self.min_score:
            return SymbolReject(
                symbol,
                "score_floor",
                f"overall={scores.overall:.1f} < min_score={self.min_score}",
            )
        decision = "WATCH" if scores.overall < self.min_score + 10 else "CANDIDATE"

        return Opportunity(
            symbol=symbol,
            direction=direction,
            setup=setup,
            scores=scores,
            entry=round(entry, 4),
            stop=round(stop, 4),
            target=round(target, 4),
            risk_reward=rr,
            regime=regime_report.regime.value,
            regime_confidence=regime_report.confidence,
            why=why,
            do_not_trade_if=do_not,
            invalidation=invalidation,
            decision=decision,
        )
