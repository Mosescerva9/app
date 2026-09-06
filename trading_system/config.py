"""Environment-backed configuration. Secrets never live in source."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

from trading_system.modes import TradingMode

load_dotenv()


def _bool(raw: str | None, default: bool = False) -> bool:
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    mode: TradingMode
    market_data_provider: str
    broker_provider: str

    webull_app_key: str
    webull_app_secret: str
    webull_region: str
    webull_api_endpoint: str
    webull_account_id: str

    account_equity_usd: float
    max_risk_per_trade_pct: float
    max_simultaneous_positions: int
    max_daily_loss_pct: float
    max_weekly_loss_pct: float

    emergency_stop: bool
    log_level: str
    catalyst_provider: str = "auto"
    fundamentals_provider: str = "auto"

    @property
    def webull_configured(self) -> bool:
        return bool(self.webull_app_key and self.webull_app_secret)

    @classmethod
    def from_env(cls) -> Settings:
        mode_raw = os.getenv("TRADING_MODE", "RESEARCH").strip().upper()
        try:
            mode = TradingMode(mode_raw)
        except ValueError as exc:
            raise ValueError(
                f"Invalid TRADING_MODE={mode_raw!r}; "
                f"expected one of {[m.value for m in TradingMode]}"
            ) from exc

        return cls(
            mode=mode,
            market_data_provider=os.getenv("MARKET_DATA_PROVIDER", "mock").strip().lower(),
            broker_provider=os.getenv("BROKER_PROVIDER", "mock").strip().lower(),
            webull_app_key=os.getenv("WEBULL_APP_KEY", "").strip(),
            webull_app_secret=os.getenv("WEBULL_APP_SECRET", "").strip(),
            webull_region=os.getenv("WEBULL_REGION", "us").strip() or "us",
            webull_api_endpoint=(
                os.getenv("WEBULL_API_ENDPOINT", "api.sandbox.webull.com").strip()
                or "api.sandbox.webull.com"
            ),
            webull_account_id=os.getenv("WEBULL_ACCOUNT_ID", "").strip(),
            account_equity_usd=float(os.getenv("ACCOUNT_EQUITY_USD", "1500")),
            max_risk_per_trade_pct=float(os.getenv("MAX_RISK_PER_TRADE_PCT", "0.10")),
            max_simultaneous_positions=int(os.getenv("MAX_SIMULTANEOUS_POSITIONS", "2")),
            max_daily_loss_pct=float(os.getenv("MAX_DAILY_LOSS_PCT", "0.05")),
            max_weekly_loss_pct=float(os.getenv("MAX_WEEKLY_LOSS_PCT", "0.10")),
            emergency_stop=_bool(os.getenv("EMERGENCY_STOP"), default=False),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            catalyst_provider=os.getenv("CATALYST_PROVIDER", "auto").strip().lower() or "auto",
            fundamentals_provider=os.getenv("FUNDAMENTALS_PROVIDER", "auto").strip().lower()
            or "auto",
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
