"""Shared types for the Options Analysis Engine."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from trading_system.scanner.types import Opportunity


@dataclass(frozen=True)
class OptionContract:
    """Normalized option contract quote."""

    underlying: str
    right: str  # CALL | PUT
    expiration: date
    strike: float
    bid: float
    ask: float
    last: float
    mid: float
    volume: int
    open_interest: int
    implied_volatility: float
    delta: float
    gamma: float
    theta: float
    vega: float
    as_of: datetime
    symbol: str = ""
    exchange: str = "MOCK"

    @property
    def dte(self) -> int:
        return max(0, (self.expiration - self.as_of.date()).days)

    @property
    def spread_pct(self) -> float:
        if self.mid <= 0:
            return 1.0
        return max(0.0, (self.ask - self.bid) / self.mid)

    @property
    def premium_per_contract_usd(self) -> float:
        """Cash outlay for 1 long contract (100 shares)."""
        return round(self.mid * 100.0, 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "underlying": self.underlying,
            "right": self.right,
            "expiration": self.expiration.isoformat(),
            "dte": self.dte,
            "strike": self.strike,
            "bid": self.bid,
            "ask": self.ask,
            "last": self.last,
            "mid": self.mid,
            "spread_pct": round(self.spread_pct, 4),
            "volume": self.volume,
            "open_interest": self.open_interest,
            "implied_volatility": self.implied_volatility,
            "delta": self.delta,
            "gamma": self.gamma,
            "theta": self.theta,
            "vega": self.vega,
            "premium_per_contract_usd": self.premium_per_contract_usd,
            "exchange": self.exchange,
            "as_of": self.as_of.isoformat(),
        }


@dataclass(frozen=True)
class OptionContractScores:
    liquidity: float
    delta_fit: float
    iv_sanity: float
    theta_drag: float
    risk_fit: float
    overall: float
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "liquidity": self.liquidity,
            "delta_fit": self.delta_fit,
            "iv_sanity": self.iv_sanity,
            "theta_drag": self.theta_drag,
            "risk_fit": self.risk_fit,
            "overall": self.overall,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class OptionCandidate:
    """A filtered + scored option contract tied to an equity opportunity."""

    contract: OptionContract
    scores: OptionContractScores
    equity_opportunity: Opportunity
    strategy: str
    max_loss_usd: float
    notes: tuple[str, ...] = ()

    @property
    def symbol(self) -> str:
        return self.contract.underlying

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "max_loss_usd": self.max_loss_usd,
            "notes": list(self.notes),
            "contract": self.contract.to_dict(),
            "scores": self.scores.to_dict(),
            "equity_opportunity": {
                "symbol": self.equity_opportunity.symbol,
                "direction": self.equity_opportunity.direction.value,
                "setup": self.equity_opportunity.setup.value,
                "overall_score": self.equity_opportunity.scores.overall,
                "regime_fit": self.equity_opportunity.scores.regime_fit,
            },
        }


@dataclass(frozen=True)
class OptionsAnalysisReport:
    as_of: datetime
    equity_candidates_considered: int
    contracts_evaluated: int
    candidates: tuple[OptionCandidate, ...]
    rejected_counts: dict[str, int] = field(default_factory=dict)
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_of": self.as_of.astimezone(timezone.utc).isoformat(),
            "equity_candidates_considered": self.equity_candidates_considered,
            "contracts_evaluated": self.contracts_evaluated,
            "candidate_count": len(self.candidates),
            "candidates": [c.to_dict() for c in self.candidates],
            "rejected_counts": dict(self.rejected_counts),
            "notes": list(self.notes),
        }


def occ_symbol(underlying: str, expiration: date, right: str, strike: float) -> str:
    """Build a readable OCC-like symbol for logs/tests."""
    yy = expiration.strftime("%y%m%d")
    r = "C" if right.upper().startswith("C") else "P"
    strike_int = int(round(strike * 1000))
    return f"{underlying.upper()}{yy}{r}{strike_int:08d}"


# Standard OCC: ROOT + YYMMDD + C|P + 8-digit strike*1000. Webull contract
# listings sometimes prefix a vendor digit (e.g. 2NVDA261016C00210000).
_OCC_BODY = re.compile(r"^([A-Z]{1,6})(\d{6})([CP])(\d{8})$")


def normalize_occ_option_symbol(
    raw: str,
    *,
    underlying: str = "",
    expiration: date | None = None,
    right: str = "",
    strike: float | None = None,
) -> str:
    """Return a snapshot-safe OCC symbol.

    Strip a leading vendor prefix such as ``2`` before the root
    (``2NVDA261016C00210000`` → ``NVDA261016C00210000``). If the raw value
    is not OCC-shaped, reconstruct from strike/expiry/right when known.
    """
    text = str(raw or "").strip().upper().replace(" ", "").replace("-", "")
    if _OCC_BODY.match(text):
        return text
    stripped = text.lstrip("0123456789")
    if _OCC_BODY.match(stripped):
        return stripped
    if underlying and expiration is not None and right and strike is not None and strike > 0:
        return occ_symbol(underlying, expiration, right, strike)
    return stripped or text
