"""Hard risk limits. AI confidence must never override these."""

from __future__ import annotations

from dataclasses import dataclass

from trading_system.config import Settings


@dataclass(frozen=True)
class RiskLimits:
    account_equity_usd: float
    max_risk_per_trade_pct: float
    max_simultaneous_positions: int
    max_daily_loss_pct: float
    max_weekly_loss_pct: float
    emergency_stop: bool

    @property
    def max_risk_per_trade_usd(self) -> float:
        return round(self.account_equity_usd * self.max_risk_per_trade_pct, 2)

    @property
    def max_daily_loss_usd(self) -> float:
        return round(self.account_equity_usd * self.max_daily_loss_pct, 2)

    @property
    def max_weekly_loss_usd(self) -> float:
        return round(self.account_equity_usd * self.max_weekly_loss_pct, 2)

    def assert_can_trade(self) -> None:
        if self.emergency_stop:
            raise RuntimeError("EMERGENCY_STOP is enabled — trading disabled")


def load_risk_limits(settings: Settings) -> RiskLimits:
    return RiskLimits(
        account_equity_usd=settings.account_equity_usd,
        max_risk_per_trade_pct=settings.max_risk_per_trade_pct,
        max_simultaneous_positions=settings.max_simultaneous_positions,
        max_daily_loss_pct=settings.max_daily_loss_pct,
        max_weekly_loss_pct=settings.max_weekly_loss_pct,
        emergency_stop=settings.emergency_stop,
    )
