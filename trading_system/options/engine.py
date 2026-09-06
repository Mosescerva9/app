"""Options Analysis Engine — contract selection for equity opportunities."""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timezone

from trading_system.data.base import MarketDataProvider
from trading_system.options.chain import MockOptionChainProvider, OptionChainProvider
from trading_system.options.factory import build_option_chain_provider
from trading_system.options.filters import (
    OptionFilterConfig,
    filter_contract,
    resolve_filter_config,
)
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
    - Prefer 30–60 DTE, |delta| ~0.25–0.45 when premium×100 fits the book
    - On a ≤$150 book (or when that mid-delta band is empty), allow
      |delta| 0.08–0.35 and DTE ≥14 so liquid OTM longs can surface
    - Max loss = premium × 100 must still fit the risk budget
    - No credit / naked short premium. Live execution remains locked.
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
        filter_cfg = resolve_filter_config(self.risk, self.filter_config)
        notes = [
            "Phase 5 options engine: long premium only (calls for LONG, puts for SHORT).",
            (
                "Prefer 30–60 DTE / mid-delta when debit×100 fits the per-trade budget. "
                f"Active window: DTE {filter_cfg.min_dte}–{filter_cfg.max_dte}, "
                f"|delta| {filter_cfg.min_abs_delta:.2f}–{filter_cfg.max_abs_delta:.2f} "
                f"(budget ${self.risk.max_risk_per_trade_usd:.0f})."
            ),
            (
                "Cheap OTM is more lottery-like than mid-delta; max loss is still 1× debit. "
                "Results are RESEARCH candidates — not trade orders. Live execution remains locked."
            ),
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
        primary_cfg = resolve_filter_config(self.risk, self.filter_config, relax=False)
        scored, evaluated, reject_reasons = self._score_chain(
            chain, opp=opp, side=side, cfg=primary_cfg, rejected=rejected, notes=notes
        )

        if (
            not scored
            and self.filter_config.auto_relax_when_budget_binds
            and reject_reasons.get("premium_exceeds_risk_budget", 0) > 0
        ):
            relaxed_cfg = resolve_filter_config(self.risk, self.filter_config, relax=True)
            if relaxed_cfg != primary_cfg:
                notes.append(
                    f"{opp.symbol}: mid-delta empty under "
                    f"${self.risk.max_risk_per_trade_usd:.0f} premium cap; "
                    f"retrying |delta| {relaxed_cfg.min_abs_delta:.2f}–"
                    f"{relaxed_cfg.max_abs_delta:.2f}, "
                    f"DTE {relaxed_cfg.min_dte}–{relaxed_cfg.max_dte}."
                )
                scored, extra, _ = self._score_chain(
                    chain,
                    opp=opp,
                    side=side,
                    cfg=relaxed_cfg,
                    rejected=rejected,
                    notes=notes,
                )
                evaluated += extra

        scored.sort(key=lambda c: c.scores.overall, reverse=True)
        return scored[: self.max_contracts_per_symbol], evaluated

    def _score_chain(
        self,
        chain,
        *,
        opp: Opportunity,
        side: str,
        cfg: OptionFilterConfig,
        rejected: Counter[str],
        notes: list[str],
    ) -> tuple[list[OptionCandidate], int, Counter[str]]:
        strategy = "long_call" if side == "LONG" else "long_put"
        scored: list[OptionCandidate] = []
        below_floor: list[OptionCandidate] = []
        evaluated = 0
        local = Counter()
        relaxed_band = cfg.min_abs_delta < 0.25
        delta_width = 0.30 if relaxed_band else 0.20

        for contract in chain:
            evaluated += 1
            result = filter_contract(
                contract,
                side_bias=side,
                limits=self.risk,
                config=cfg,
            )
            if not result.ok:
                local[result.reason] += 1
                rejected[result.reason] += 1
                continue

            scores = score_contract(
                contract,
                limits=self.risk,
                delta_fit_width=delta_width,
            )
            cand_notes = [
                f"equity={opp.symbol} {side} setup={opp.setup.value}",
                f"equity_score={opp.scores.overall:.1f}",
                f"option_score={scores.overall:.1f}",
                *scores.reasons[:4],
            ]
            candidate = OptionCandidate(
                contract=contract,
                scores=scores,
                equity_opportunity=opp,
                strategy=strategy,
                max_loss_usd=contract.premium_per_contract_usd,
                notes=tuple(cand_notes),
            )
            if scores.overall >= self.min_option_score:
                scored.append(candidate)
            else:
                below_floor.append(candidate)
                local["option_score_below_min"] += 1
                rejected["option_score_below_min"] += 1

        if (
            not scored
            and below_floor
            and cfg.prefer_feasible_over_empty
        ):
            floor = min(self.min_option_score, cfg.budget_feasible_min_score)
            fallback = [c for c in below_floor if c.scores.overall >= floor]
            fallback.sort(key=lambda c: c.scores.overall, reverse=True)
            if fallback:
                notes.append(
                    f"{opp.symbol}: kept budget-feasible long-premium contracts "
                    f"below min_option_score={self.min_option_score:.0f} "
                    f"(floor {floor:.0f}) rather than returning none."
                )
                scored = fallback

        return scored, evaluated, local

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
