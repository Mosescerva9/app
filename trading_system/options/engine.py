"""Options Analysis Engine — contract selection for equity opportunities."""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timezone

from trading_system.data.base import MarketDataProvider
from trading_system.options.chain import MockOptionChainProvider, OptionChainProvider
from trading_system.options.factory import build_option_chain_provider
from trading_system.options.filters import OptionFilterConfig, filter_contract
from trading_system.options.scoring import score_contract
from trading_system.options.types import OptionCandidate, OptionsAnalysisReport
from trading_system.risk.limits import RiskLimits, load_risk_limits
from trading_system.config import get_settings
from trading_system.scanner.engine import OpportunityScanner
from trading_system.scanner.types import Direction, Opportunity, ScanReport

logger = logging.getLogger(__name__)


class OptionsAnalysisEngine:
    """
    Takes ranked equity opportunities and selects long-premium option contracts.

    Rules (Phase 5):
    - LONG equity bias → long calls; SHORT bias → long puts
    - Prefer 30–60 DTE, |delta| ~0.25–0.45, liquid OI/spreads
    - Max loss = premium × 100 must fit risk budget (~$150 on $1,500)
    - Contract must pass its own filters/scores (equity score alone is not enough)
    """

    def __init__(
        self,
        market_data: MarketDataProvider,
        *,
        chain_provider: OptionChainProvider | None = None,
        risk: RiskLimits | None = None,
        filter_config: OptionFilterConfig | None = None,
        lookback: int = 90,
        min_equity_score: float = 55.0,
        min_option_score: float = 55.0,
        max_results: int = 10,
        max_contracts_per_symbol: int = 2,
        benchmark: str = "SPY",
        universe: tuple[str, ...] | list[str] | None = None,
    ) -> None:
        self.market_data = market_data
        if chain_provider is not None:
            self.chain_provider = chain_provider
        elif getattr(market_data, "name", "") == "webull":
            self.chain_provider = build_option_chain_provider(get_settings(), market_data)
        else:
            self.chain_provider = MockOptionChainProvider()
        self.risk = risk or load_risk_limits(get_settings())
        self.filter_config = filter_config or OptionFilterConfig()
        self.lookback = lookback
        self.min_equity_score = min_equity_score
        self.min_option_score = min_option_score
        self.max_results = max_results
        self.max_contracts_per_symbol = max_contracts_per_symbol
        self.benchmark = benchmark.upper()
        self.universe = universe
        self.scanner = OpportunityScanner(
            market_data,
            universe=universe,
            lookback=lookback,
            min_score=min_equity_score,
            max_results=max(max_results * 3, 15),
            benchmark=self.benchmark,
        )

    def analyze(self, *, scan_report: ScanReport | None = None) -> OptionsAnalysisReport:
        report = scan_report or self.scanner.scan()
        as_of = datetime.now(timezone.utc)
        rejected: Counter[str] = Counter()
        candidates: list[OptionCandidate] = []
        contracts_evaluated = 0
        notes = [
            "Phase 5 options engine: long premium only (calls for LONG, puts for SHORT).",
            "Prefer 30–60 DTE, mid-delta, liquid contracts within per-trade risk budget.",
            "Results are RESEARCH candidates — not trade orders. Live execution remains locked.",
            f"Chain provider: {type(self.chain_provider).__name__}",
        ]

        for opp in report.opportunities:
            if opp.direction is Direction.NONE:
                rejected["no_direction"] += 1
                continue
            symbol_candidates, evaluated = self._analyze_opportunity(
                opp, as_of=as_of, rejected=rejected, notes=notes
            )
            contracts_evaluated += evaluated
            candidates.extend(symbol_candidates)

        candidates.sort(key=lambda c: c.scores.overall, reverse=True)
        selected = candidates[: self.max_results]

        if not report.opportunities and getattr(report, "rejects", None):
            counts: dict[str, int] = {}
            for row in report.rejects:
                counts[row.reason] = counts.get(row.reason, 0) + 1
            notes.append(
                "Equity scan produced 0 opportunities; option engine has nothing to size. "
                f"Scan rejects: {counts}"
            )
        if not selected:
            notes.append("No option contracts passed filters/scores for current equity set.")

        return OptionsAnalysisReport(
            as_of=as_of,
            equity_candidates_considered=len(report.opportunities),
            contracts_evaluated=contracts_evaluated,
            candidates=tuple(selected),
            rejected_counts=dict(rejected),
            notes=tuple(notes),
        )

    def _analyze_opportunity(
        self,
        opp: Opportunity,
        *,
        as_of: datetime,
        rejected: Counter[str],
        notes: list[str],
    ) -> tuple[list[OptionCandidate], int]:
        spot = self._spot(opp.symbol, fallback=opp.entry)
        try:
            chain = self.chain_provider.get_chain(opp.symbol, as_of=as_of, spot=spot)
        except Exception as exc:  # noqa: BLE001
            logger.info("Chain failed for %s: %s", opp.symbol, exc)
            rejected["chain_error"] += 1
            notes.append(f"{opp.symbol} chain_error: {exc}")
            return [], 0

        side = opp.direction.value
        strategy = "long_call" if side == "LONG" else "long_put"
        scored: list[OptionCandidate] = []
        evaluated = 0

        for contract in chain:
            evaluated += 1
            result = filter_contract(
                contract,
                side_bias=side,
                limits=self.risk,
                config=self.filter_config,
            )
            if not result.ok:
                rejected[result.reason] += 1
                continue

            scores = score_contract(contract, limits=self.risk)
            if scores.overall < self.min_option_score:
                rejected["option_score_below_min"] += 1
                continue

            notes = [
                f"equity={opp.symbol} {side} setup={opp.setup.value}",
                f"equity_score={opp.scores.overall:.1f}",
                f"option_score={scores.overall:.1f}",
                *scores.reasons[:4],
            ]
            scored.append(
                OptionCandidate(
                    contract=contract,
                    scores=scores,
                    equity_opportunity=opp,
                    strategy=strategy,
                    max_loss_usd=contract.premium_per_contract_usd,
                    notes=tuple(notes),
                )
            )

        scored.sort(key=lambda c: c.scores.overall, reverse=True)
        return scored[: self.max_contracts_per_symbol], evaluated

    def _spot(self, symbol: str, fallback: float | None) -> float:
        try:
            snaps = self.market_data.get_snapshots([symbol])
            if snaps and snaps[0].last:
                return float(snaps[0].last)
        except Exception:  # noqa: BLE001
            pass
        if fallback is not None and fallback > 0:
            return float(fallback)
        return 100.0
