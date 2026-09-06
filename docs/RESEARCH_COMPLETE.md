# RESEARCH_COMPLETE checklist

System-level `RESEARCH_COMPLETE` is a hard product lock. It stays `false` until
**every** row below is honestly done. A Decision Package may still set
`incomplete_research=false` when *that symbol's* required dimensions exist —
that is **not** a GO and does not flip this flag.

CLI stamps on `status`, `scan`, `options`, `decide`, `backtest`, `journal`,
`paper-open`, `paper-close`, `paper-note`:

- `research_complete=false`
- `trade_recommendation=false`
- `go_signals_allowed=false`
- `go_signal=false`

`LIVE_EXECUTION_UNLOCKED` remains `false`. `LIVE_APPROVAL` cannot place orders.

| # | Criterion | Status |
|---|---|---|
| 1 | Regime + equity scores (Phases 3–4) | ✅ |
| 2 | Long-premium options engine (Phase 5 / audit 6) | ✅ |
| 3 | Catalyst (official earnings/filings or ETF n/a) | ✅ |
| 4 | Fundamentals: official forecast-EPS **and** statements/indicators/industry when the SDK returns them (no invented numbers) | ✅ this slice (degrades if API/SDK missing) |
| 5 | Adversarial critique (rule-based; LLM hook unused in CI) | ✅ |
| 6 | Backtester: costs, slippage, no look-ahead, OOS or walk-forward, ≥1 long-premium setup | ✅ **minimal** (synthetic option mark, **not** historical OPRA) |
| 7 | Paper journal + paper ledger (full loop, no broker risk) | ✅ simulated ledger + paper-only CLI (not a Webull paper account) |
| 8 | Dashboard + Grok daily brief | ❌ deferred |
| 9 | Sandbox execution adapter | ❌ deferred / locked |
| 10 | Explicit user unlock of `LIVE_APPROVAL` | ❌ never in this PR |

**Exit rule:** `RESEARCH_COMPLETE` stays false after this PR because items 8–10
are deferred and item 6 is still a synthetic mark (not historical OPRA). Prefer
`stand_aside` when evidence is thin. `phase9_complete` is true; that is **not**
`RESEARCH_COMPLETE`.
