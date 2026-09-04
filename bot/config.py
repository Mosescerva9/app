"""Configuration loaded from environment / .env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _csv_ids(raw: str | None) -> frozenset[int]:
    if not raw or not raw.strip():
        return frozenset()
    out: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part:
            out.add(int(part))
    return frozenset(out)


def _bool(raw: str | None, default: bool = False) -> bool:
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    discord_bot_token: str
    discord_guild_id: int | None
    discord_channel_ids: frozenset[int]
    discord_alert_author_ids: frozenset[int]

    webull_app_key: str
    webull_app_secret: str
    webull_account_id: str
    webull_region: str
    webull_api_endpoint: str

    dry_run: bool
    default_quantity: int
    max_quantity: int
    buy_slippage: float
    sell_slippage: float
    require_limit_price: bool

    positions_db_path: Path
    log_level: str

    @classmethod
    def from_env(cls) -> Settings:
        token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
        if not token:
            raise ValueError("DISCORD_BOT_TOKEN is required")

        guild_raw = os.getenv("DISCORD_GUILD_ID", "").strip()
        guild_id = int(guild_raw) if guild_raw else None

        dry_run = _bool(os.getenv("DRY_RUN"), default=True)
        app_key = os.getenv("WEBULL_APP_KEY", "").strip()
        app_secret = os.getenv("WEBULL_APP_SECRET", "").strip()
        account_id = os.getenv("WEBULL_ACCOUNT_ID", "").strip()
        if not dry_run and (not app_key or not app_secret or not account_id):
            raise ValueError(
                "WEBULL_APP_KEY, WEBULL_APP_SECRET, and WEBULL_ACCOUNT_ID "
                "are required when DRY_RUN=false"
            )

        return cls(
            discord_bot_token=token,
            discord_guild_id=guild_id,
            discord_channel_ids=_csv_ids(os.getenv("DISCORD_CHANNEL_IDS")),
            discord_alert_author_ids=_csv_ids(os.getenv("DISCORD_ALERT_AUTHOR_IDS")),
            webull_app_key=app_key,
            webull_app_secret=app_secret,
            webull_account_id=account_id,
            webull_region=os.getenv("WEBULL_REGION", "us").strip() or "us",
            webull_api_endpoint=(
                os.getenv("WEBULL_API_ENDPOINT", "api.sandbox.webull.com").strip()
                or "api.sandbox.webull.com"
            ),
            dry_run=dry_run,
            default_quantity=max(1, int(os.getenv("DEFAULT_QUANTITY", "1"))),
            max_quantity=max(1, int(os.getenv("MAX_QUANTITY", "10"))),
            buy_slippage=float(os.getenv("BUY_SLIPPAGE", "0.05")),
            sell_slippage=float(os.getenv("SELL_SLIPPAGE", "0.05")),
            require_limit_price=_bool(os.getenv("REQUIRE_LIMIT_PRICE"), default=True),
            positions_db_path=Path(
                os.getenv("POSITIONS_DB_PATH", "./data/positions.db")
            ),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )


settings: Settings | None = None


def get_settings() -> Settings:
    global settings
    if settings is None:
        settings = Settings.from_env()
    return settings
