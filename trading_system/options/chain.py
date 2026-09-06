"""Option chain provider interface + offline mock."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta, timezone
from math import exp, sqrt
from typing import Sequence

from trading_system.options.types import OptionContract, occ_symbol


class OptionChainProvider(ABC):
    @abstractmethod
    def get_chain(
        self,
        underlying: str,
        *,
        as_of: datetime | None = None,
        spot: float | None = None,
    ) -> Sequence[OptionContract]:
        raise NotImplementedError


class MockOptionChainProvider(OptionChainProvider):
    """
    Synthetic chain for offline development.

    Generates liquid mid-delta calls/puts across several expirations so the
    options engine can be tested without Webull Advanced Quotes.

    Premiums are deliberately scaled so some mid-delta contracts fit the
    per-trade risk budget (~$150 on a $1,500 account).
    """

    def __init__(
        self,
        *,
        base_iv: float = 0.28,
        strikes_around_spot: int = 6,
        strike_step_pct: float = 0.025,
        dtes: Sequence[int] = (21, 35, 45, 60, 90),
    ) -> None:
        self.base_iv = base_iv
        self.strikes_around_spot = strikes_around_spot
        self.strike_step_pct = strike_step_pct
        self.dtes = tuple(dtes)

    def get_chain(
        self,
        underlying: str,
        *,
        as_of: datetime | None = None,
        spot: float | None = None,
    ) -> Sequence[OptionContract]:
        now = as_of or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        px = float(spot if spot is not None else 100.0)
        out: list[OptionContract] = []

        for dte in self.dtes:
            expiration = (now + timedelta(days=dte)).date()
            t_years = max(dte / 365.0, 1e-6)
            for i in range(-self.strikes_around_spot, self.strikes_around_spot + 1):
                strike = round(px * (1.0 + i * self.strike_step_pct), 2)
                for right in ("CALL", "PUT"):
                    out.append(
                        self._make_contract(
                            underlying=underlying.upper(),
                            right=right,
                            expiration=expiration,
                            strike=strike,
                            spot=px,
                            t_years=t_years,
                            as_of=now,
                        )
                    )
        return out

    def _make_contract(
        self,
        *,
        underlying: str,
        right: str,
        expiration: date,
        strike: float,
        spot: float,
        t_years: float,
        as_of: datetime,
    ) -> OptionContract:
        iv = self.base_iv * (1.05 if right == "PUT" else 1.0)
        # Rough Black-Scholes-ish delta for ranking (not production pricing).
        moneyness = (spot - strike) / max(spot, 1e-9)
        vol_term = iv * sqrt(t_years)
        raw_delta = 0.5 + moneyness / max(vol_term * 2.5, 0.05)
        if right == "CALL":
            delta = max(0.05, min(0.95, raw_delta))
        else:
            delta = -max(0.05, min(0.95, 1.0 - raw_delta))

        intrinsic = max(0.0, spot - strike) if right == "CALL" else max(0.0, strike - spot)
        # Mid ≈ $0.20–$0.40 for OTM/ATM so premium×100 can fit the research budget.
        time_value = 0.15 + abs(delta) * 0.25 + iv * sqrt(t_years) * 0.35
        mid = max(0.05, time_value + intrinsic * 0.05)
        # Deep ITM becomes too expensive — intentional rejection fodder.
        if intrinsic > 2.0:
            mid = max(mid, 0.8 + intrinsic * 0.15)

        liquidity_boost = 1.0 - abs(abs(delta) - 0.35) * 1.2
        spread = mid * max(0.02, 0.12 - 0.08 * max(0.0, liquidity_boost))
        bid = max(0.01, mid - spread / 2)
        ask = mid + spread / 2
        oi = int(800 + 4000 * max(0.0, liquidity_boost) * exp(-abs(moneyness) * 8))
        volume = int(oi * 0.15)

        gamma = abs(delta) * (1 - abs(delta)) / max(spot * vol_term, 1e-6) * 0.01
        theta = -mid * 0.02 / max(t_years * 365, 1.0) * 100
        vega = mid * 0.1

        return OptionContract(
            underlying=underlying,
            right=right,
            expiration=expiration,
            strike=strike,
            bid=round(bid, 2),
            ask=round(ask, 2),
            last=round(mid, 2),
            mid=round(mid, 2),
            volume=volume,
            open_interest=oi,
            implied_volatility=round(iv, 4),
            delta=round(delta, 4),
            gamma=round(gamma, 6),
            theta=round(theta, 4),
            vega=round(vega, 4),
            as_of=as_of,
            symbol=occ_symbol(underlying, expiration, right, strike),
            exchange="MOCK",
        )
