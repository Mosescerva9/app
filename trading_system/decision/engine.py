"""Build Decision Packages from scan → options → catalyst → adversarial."""

from __future__ import annotations

from datetime import datetime, timezone

from trading_system.adversarial.base import (
    AdversarialCritic,
    CompositeAdversarialCritic,
    CritiqueContext,
)
from trading_system.adversarial.llm import NullLLMCritic
from trading_system.adversarial.rules import RuleBasedAdversarialCritic
from trading_system.decision.types import DecisionPackage, DecisionReport, DecisionScores
from trading_system.events.base import CatalystProvider
from trading_system.events.mock import MockCatalystProvider
from trading_system.options.engine import OptionsAnalysisEngine
from trading_system.options.types import OptionCandidate, OptionsAnalysisReport
from trading_system.risk.limits import RiskLimits
from trading_system.scanner.types import Opportunity, ScanReport


class DecisionPackageEngine:
    """Architecture Phase 8 slice: auditable packages, no order placement."""

    def __init__(
        self,
        *,
        options_engine: OptionsAnalysisEngine,
        catalyst_provider: CatalystProvider | None = None,
        critic: AdversarialCritic | None = None,
        risk: RiskLimits | None = None,
        max_packages: int = 10,
    ) -> None:
        self.options_engine = options_engine
        self.catalyst_provider = catalyst_provider or MockCatalystProvider()
        self.critic = critic or CompositeAdversarialCritic(
            RuleBasedAdversarialCritic(),
            NullLLMCritic(),
        )
        self.risk = risk or options_engine.risk
        self.max_packages = max_packages

    def build(
        self,
        *,
        options_report: OptionsAnalysisReport | None = None,
        scan_report: ScanReport | None = None,
        as_of: datetime | None = None,
    ) -> DecisionReport:
        now = as_of or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        report = options_report or self.options_engine.analyze(scan_report=scan_report)
        notes = [
            "Architecture Phase 8 Decision Packages: technical + options + catalyst + adversarial.",
            "Empty/unavailable catalysts do not crash; they lower confidence and note missing data.",
            "No news headlines are generated. Live execution remains locked.",
            f"Catalyst provider: {getattr(self.catalyst_provider, 'name', type(self.catalyst_provider).__name__)}",
            f"Adversarial critic: {getattr(self.critic, 'name', type(self.critic).__name__)}",
        ]

        packages: list[DecisionPackage] = []
        seen: set[str] = set()
        for cand in report.candidates:
            packages.append(self._package_from_option(cand, as_of=now))
            seen.add(cand.symbol.upper())
            if len(packages) >= self.max_packages:
                break

        if not packages:
            fallback_scan = scan_report or getattr(self.options_engine, "scanner", None)
            opportunities = []
            if scan_report is not None:
                opportunities = list(scan_report.opportunities)
            elif fallback_scan is not None:
                try:
                    opportunities = list(fallback_scan.scan().opportunities)
                except Exception:  # noqa: BLE001
                    opportunities = []
            for opp in opportunities:
                if opp.symbol.upper() in seen:
                    continue
                packages.append(self._package_from_equity(opp, as_of=now))
                if len(packages) >= self.max_packages:
                    break
            if packages:
                notes.append(
                    "No option contracts passed filters; packages are equity-only "
                    "with stand-aside bias until a budget-feasible long exists."
                )

        if not packages:
            notes.append("No Decision Packages: empty options set and no equity fallback.")

        summary = {
            "equity_candidates_considered": report.equity_candidates_considered,
            "contracts_evaluated": report.contracts_evaluated,
            "option_candidate_count": len(report.candidates),
            "rejected_counts": dict(report.rejected_counts),
            "options_notes": list(report.notes),
        }
        return DecisionReport(
            as_of=now,
            packages=tuple(packages),
            options_summary=summary,
            notes=tuple(notes),
        )

    def _package_from_option(
        self,
        candidate: OptionCandidate,
        *,
        as_of: datetime,
    ) -> DecisionPackage:
        return self._assemble(
            opportunity=candidate.equity_opportunity,
            option=candidate,
            as_of=as_of,
        )

    def _package_from_equity(
        self,
        opportunity: Opportunity,
        *,
        as_of: datetime,
    ) -> DecisionPackage:
        return self._assemble(opportunity=opportunity, option=None, as_of=as_of)

    def _assemble(
        self,
        *,
        opportunity: Opportunity,
        option: OptionCandidate | None,
        as_of: datetime,
    ) -> DecisionPackage:
        try:
            catalyst = self.catalyst_provider.get_catalyst(opportunity.symbol, as_of=as_of)
        except Exception as exc:  # noqa: BLE001
            from trading_system.events.mock import unavailable_snapshot

            catalyst = unavailable_snapshot(
                opportunity.symbol,
                source=getattr(self.catalyst_provider, "name", "unknown"),
                note="Catalyst provider raised; treating as unavailable (no invented date).",
                error=str(exc),
            )

        critique = self.critic.critique(
            CritiqueContext(
                opportunity=opportunity,
                option=option,
                catalyst=catalyst,
                risk=self.risk,
            )
        )
        if critique is None:
            critique = RuleBasedAdversarialCritic().critique(
                CritiqueContext(
                    opportunity=opportunity,
                    option=option,
                    catalyst=catalyst,
                    risk=self.risk,
                )
            )

        option_quality = option.scores.overall if option is not None else None
        blended = opportunity.scores.overall
        if option_quality is not None:
            blended = 0.55 * opportunity.scores.overall + 0.45 * option_quality
        confidence = max(0.0, min(100.0, blended - critique.confidence_penalty))
        missing = list(opportunity.scores.missing_dimensions)
        if catalyst.score is None and "catalyst" not in missing:
            missing.append("catalyst")
        if "fundamental" not in missing:
            missing.append("fundamental")

        scores = DecisionScores(
            technical=opportunity.scores.technical,
            momentum=opportunity.scores.momentum,
            liquidity=opportunity.scores.liquidity,
            regime_fit=opportunity.scores.regime_fit,
            risk_reward=opportunity.scores.risk_reward,
            crowding_risk=opportunity.scores.crowding_risk,
            options_quality=option_quality,
            catalyst=catalyst.score,
            fundamental=None,
            overall=round(blended, 2),
            confidence=round(confidence, 2),
            missing_dimensions=tuple(missing),
        )
        recommendation = _recommendation(critique, confidence, opportunity.decision)
        notes = [
            "RESEARCH Decision Package — not a trade ticket.",
            f"recommendation={recommendation} confidence={confidence:.1f} "
            f"(penalty {critique.confidence_penalty:.1f})",
        ]
        if option is None:
            notes.append("No qualifying long-premium contract attached.")
        if not catalyst.available:
            notes.append("Catalyst data missing: confidence penalized; stand-aside preferred if technicals are weak.")

        return DecisionPackage(
            as_of=as_of,
            symbol=opportunity.symbol,
            recommendation=recommendation,
            decision=opportunity.decision,
            scores=scores,
            equity_opportunity=opportunity,
            option_candidate=option,
            catalyst=catalyst,
            adversarial=critique,
            risk={
                "account_equity_usd": self.risk.account_equity_usd,
                "max_risk_per_trade_usd": self.risk.max_risk_per_trade_usd,
                "max_loss_usd": option.max_loss_usd if option is not None else None,
                "strategy": option.strategy if option is not None else None,
                "long_premium_only": True,
            },
            notes=tuple(notes),
        )


def _recommendation(critique, confidence: float, equity_decision: str) -> str:
    if critique.reject:
        return "reject"
    if critique.stand_aside:
        return "stand_aside"
    if confidence < 50:
        return "stand_aside"
    if confidence < 60 or equity_decision == "WATCH":
        return "watch"
    return "candidate"
