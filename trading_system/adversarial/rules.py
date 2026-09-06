"""Deterministic adversarial rules for long-premium RESEARCH ideas."""

from __future__ import annotations

from trading_system.adversarial.base import AdversarialCritic, CritiqueContext
from trading_system.adversarial.types import AdversarialCritique
from trading_system.scanner.types import Direction


_WEAK_TECHNICAL = 55.0
_WEAK_EQUITY = 60.0
_CHEAP_OTM_DELTA = 0.15
_PENALTY_CAP = 55.0


class RuleBasedAdversarialCritic(AdversarialCritic):
    """No LLM. Same inputs → same critique."""

    name = "rule_based"

    def critique(self, context: CritiqueContext) -> AdversarialCritique:
        opp = context.opportunity
        option = context.option
        cat = context.catalyst
        risk = context.risk
        tech = opp.scores.technical
        equity = opp.scores.overall
        flags = set(cat.event_flags)
        why: list[str] = []
        rejects: list[str] = []
        notes: list[str] = [
            "Rule-based critic only. LLM overlay is a no-op unless injected.",
            "Long premium only; credit / naked short remain forbidden.",
        ]
        penalty = 0.0
        stand_aside = False

        if risk.emergency_stop:
            rejects.append("emergency_stop")
            why.append("EMERGENCY_STOP is on — no new risk.")

        if option is not None:
            if option.strategy not in {"long_call", "long_put"}:
                rejects.append("not_long_premium")
                why.append(f"strategy={option.strategy} is not long premium.")
            if option.max_loss_usd > risk.max_risk_per_trade_usd + 1e-9:
                rejects.append("premium_exceeds_risk_budget")
                why.append(
                    f"Premium ${option.max_loss_usd:.2f} exceeds "
                    f"${risk.max_risk_per_trade_usd:.2f} risk budget."
                )
            if opp.direction is Direction.LONG and option.contract.right != "CALL":
                rejects.append("long_bias_requires_call")
                why.append("LONG equity bias must be a long call.")
            if opp.direction is Direction.SHORT and option.contract.right != "PUT":
                rejects.append("short_bias_requires_put")
                why.append("SHORT equity bias must be a long put.")

        if opp.direction is Direction.NONE:
            stand_aside = True
            why.append("Scanner has no directional bias — stand aside.")

        if not opp.invalidation and (opp.stop is None):
            rejects.append("missing_stop_or_invalidation")
            why.append("Idea has no stop/invalidation.")

        if "earnings_within_2d" in flags:
            rejects.append("earnings_within_2d")
            why.append(
                "Earnings in ≤2 days: binary gap + IV crush against long premium."
            )

        catalyst_unknown = (not cat.available) or (
            cat.earnings_status in {"unavailable", "unknown"}
        )
        weak_technicals = tech is None or tech < _WEAK_TECHNICAL or equity < _WEAK_EQUITY

        if catalyst_unknown:
            penalty += 15.0
            notes.append(
                "Catalyst calendar unavailable or unknown — confidence reduced; "
                "no news was invented."
            )
            if weak_technicals:
                stand_aside = True
                why.append(
                    "Stand aside: catalyst unknown and technicals/equity score are weak."
                )

        if "earnings_within_7d" in flags and "earnings_within_2d" not in flags:
            stand_aside = True
            penalty += 18.0
            why.append(
                "Earnings inside 7 days: long premium is short vol into the print."
            )
        elif "earnings_within_21d" in flags and "earnings_within_7d" not in flags:
            penalty += 8.0
            why.append("Earnings inside 21 days: IV and gap risk still elevated.")

        if weak_technicals and not catalyst_unknown:
            penalty += 10.0 if (tech is not None and tech < 50) else 6.0
            why.append("Technical/equity score is only marginally supportive.")

        if option is not None and abs(option.contract.delta) < _CHEAP_OTM_DELTA:
            penalty += 10.0
            why.append(
                f"|delta|={abs(option.contract.delta):.2f} is lottery-like on a $150 book."
            )
            if catalyst_unknown:
                stand_aside = True
                why.append("Cheap OTM plus unknown catalyst: stand aside.")

        if option is not None and option.contract.spread_pct > 0.08:
            penalty += 5.0
            why.append("Bid/ask spread is wide relative to mid.")

        if option is not None and option.scores.overall < 50:
            penalty += 8.0
            why.append("Option quality score is below 50.")

        if opp.scores.crowding_risk is not None and opp.scores.crowding_risk >= 70:
            penalty += 8.0
            why.append("Crowding proxy is elevated (extension / volume spike).")

        if opp.scores.regime_fit is not None and opp.scores.regime_fit < 45:
            penalty += 10.0
            why.append(f"Regime fit is weak under {opp.regime}.")

        if opp.regime in {"choppy", "unknown", "event_driven"} and (
            opp.scores.regime_fit is None or opp.scores.regime_fit < 50
        ):
            stand_aside = True
            why.append(f"Regime={opp.regime}: prefer stand-aside over forcing a debit.")

        if (
            option is not None
            and cat.days_to_earnings is not None
            and option.contract.dte < cat.days_to_earnings
        ):
            penalty += 12.0
            stand_aside = True
            why.append(
                f"Contract DTE {option.contract.dte} expires before earnings "
                f"in {cat.days_to_earnings} days."
            )

        penalty = min(_PENALTY_CAP, penalty)
        suggestion = _suggestion(
            option=option,
            catalyst_unknown=catalyst_unknown,
            weak_technicals=weak_technicals,
            flags=flags,
            reject=bool(rejects),
            stand_aside=stand_aside,
        )
        if not why:
            why.append(
                "No hard failure mode from the rule set; still a RESEARCH idea, "
                "not an order."
            )
        return AdversarialCritique(
            why_trade_fails=tuple(why),
            instant_reject_conditions=tuple(rejects),
            better_strike_dte_or_stand_aside=suggestion,
            confidence_penalty=round(penalty, 2),
            critic=self.name,
            stand_aside=stand_aside and not rejects,
            reject=bool(rejects),
            notes=tuple(notes),
        )


def _suggestion(
    *,
    option,
    catalyst_unknown: bool,
    weak_technicals: bool,
    flags: set[str],
    reject: bool,
    stand_aside: bool,
) -> str:
    if reject:
        return "Stand aside — instant-reject condition fired; do not place an order."
    if catalyst_unknown and weak_technicals:
        return (
            "Stand aside until an official earnings date is available and "
            "technicals are no longer weak."
        )
    if "earnings_within_7d" in flags or "earnings_within_2d" in flags:
        return (
            "Stand aside through the print, or wait for a 30–45 DTE expiry "
            "after the official earnings date."
        )
    if option is not None and abs(option.contract.delta) < _CHEAP_OTM_DELTA:
        return (
            "Prefer a higher |delta| still inside the $150 premium cap; "
            "otherwise stand aside rather than buy a 0.10 lottery ticket."
        )
    if option is not None and option.contract.dte < 21:
        return (
            "Prefer 30–45 DTE if a liquid mid still fits the $150 book; "
            "short DTE is mostly theta."
        )
    if stand_aside:
        return "Stand aside — conditions do not justify a new long-premium debit."
    return (
        "Current strike/DTE is acceptable as a RESEARCH candidate only: "
        "size 1 contract, defined-risk debit, no live order."
    )
