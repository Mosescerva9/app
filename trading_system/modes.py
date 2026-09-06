"""System operating modes. Live execution remains locked through Phase 8."""

from __future__ import annotations

from enum import Enum


class TradingMode(str, Enum):
    RESEARCH = "RESEARCH"
    PAPER = "PAPER"
    LIVE_APPROVAL = "LIVE_APPROVAL"


PHASE = 8
LIVE_EXECUTION_UNLOCKED = False


def assert_mode_allowed(mode: TradingMode) -> None:
    if mode is TradingMode.LIVE_APPROVAL and not LIVE_EXECUTION_UNLOCKED:
        raise RuntimeError(
            "LIVE_APPROVAL is configured but live execution is locked until a later "
            "phase and explicit user confirmation."
        )
