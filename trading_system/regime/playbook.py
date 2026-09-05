"""Strategy playbook by market regime (starting heuristics; refined later via backtests)."""

from __future__ import annotations

from trading_system.regime.types import MarketRegime

PLAYBOOK: dict[MarketRegime, dict[str, list[str]]] = {
    MarketRegime.STRONG_BULL: {
        "favored": [
            "breakout_continuation",
            "pullback_in_uptrend",
            "momentum_continuation",
            "relative_strength_breakout",
        ],
        "avoided": ["mean_reversion_shorts", "failed_breakout_fades_against_trend"],
        "risks": ["late-trend chase", "crowded momentum unwind", "gap-up premium expansion"],
    },
    MarketRegime.WEAK_BULL: {
        "favored": ["pullback_in_uptrend", "relative_strength_breakout"],
        "avoided": ["aggressive_breakout_chase", "naked_short_premium"],
        "risks": ["false breakouts", "sector rotation whipsaw"],
    },
    MarketRegime.STRONG_BEAR: {
        "favored": ["breakdown_continuation", "rally_failure_shorts", "put_debit_spreads_liquid"],
        "avoided": ["buy_the_dip_without_structure", "short_dated_calls"],
        "risks": ["violent short squeezes", "gap-down liquidity air pockets"],
    },
    MarketRegime.WEAK_BEAR: {
        "favored": ["rally_failure", "mean_reversion_into_resistance"],
        "avoided": ["aggressive_trend_shorts_size"],
        "risks": ["bear-market rallies", "IV crush after panic peaks"],
    },
    MarketRegime.HIGH_VOL_TREND: {
        "favored": ["defined_risk_options", "wider_stops_smaller_size", "breakout_with_vol_filter"],
        "avoided": ["tight_mean_reversion", "naked_short_vol", "oversized premium buys"],
        "risks": ["gap risk", "slippage", "correlation spike to 1"],
    },
    MarketRegime.LOW_VOL_TREND: {
        "favored": ["trend_pullbacks", "debit_spreads", "calendar_structures_selective"],
        "avoided": ["buying_expensive_lottery_OTM"],
        "risks": ["complacency", "sudden vol expansion regime shift"],
    },
    MarketRegime.MEAN_REVERTING: {
        "favored": ["oversold_bounce", "fade_extended_moves", "range_mean_reversion"],
        "avoided": ["breakout_continuation", "momentum_chase"],
        "risks": ["regime flip into trend", "earnings/news gap through levels"],
    },
    MarketRegime.CHOPPY: {
        "favored": ["stand_aside", "reduce_trade_frequency", "wait_for_structure"],
        "avoided": ["breakout_systems", "high_frequency_swing_entries"],
        "risks": ["death by a thousand stops", "false signals"],
    },
    MarketRegime.EVENT_DRIVEN: {
        "favored": ["defined_risk_only", "post_event_continuation_after_stabilization"],
        "avoided": ["holding_through_binary_events_by_default", "wide_undefined_risk"],
        "risks": ["discontinuous gaps", "IV crush", "headline reversals"],
    },
    MarketRegime.UNKNOWN: {
        "favored": ["stand_aside", "collect_more_data"],
        "avoided": ["all_discretionary_size_up"],
        "risks": ["insufficient sample", "feature instability"],
    },
}


def playbook_for(regime: MarketRegime) -> dict[str, list[str]]:
    return PLAYBOOK.get(regime, PLAYBOOK[MarketRegime.UNKNOWN])
