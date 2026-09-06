# RESEARCH_COMPLETE checklist

System-level `RESEARCH_COMPLETE` is a **research-desk** flag. It becomes `true`
when every **research** row below is honestly done. It does **not** unlock live
trading, sandbox order placement, or broker GO.

A Decision Package may still set `incomplete_research=false` when *that symbol's*
required dimensions exist. Prefer `stand_aside` when any required dimension is
missing. Package completeness is **not** a broker GO.

## What this flag is

`research_complete=true` means the research loop exists:

1. Regime + equity scores
2. Long-premium options engine
3. Official catalyst (or ETF n/a)
4. Official fundamentals (or ETF n/a)
5. Adversarial critique
6. Minimal backtester (synthetic long-premium)
7. Paper journal + paper ledger
8. Daily/weekly **text** report CLI for Grok oversight

## What this flag is not

These are **post-research gates** and are **excluded** from `RESEARCH_COMPLETE`:

- Fancy dashboard / visual UI
- Sandbox execution adapter (`place_order` / preview / cancel)
- `LIVE_EXECUTION` / `LIVE_APPROVAL` unlock
- Broker GO / automatic order placement
- Historical OPRA option-chain backtests (Phase 7 remains a synthetic mark)

`LIVE_EXECUTION_UNLOCKED` remains `false`. `LIVE_APPROVAL` cannot place orders.

## CLI stamps

| Surface | `research_complete` | `trade_recommendation` / `go_signals_allowed` | `go_signal` (broker GO) | `live_execution_unlocked` |
|---|---|---|---|---|
| `status`, `scan`, `options`, `backtest`, `journal`, `paper-*` | `true` | `false` (no decide candidates) | `false` | `false` |
| `decide`, `report` | `true` | `true` **only** when a complete **paper/research** candidate exists | `false` | `false` |

Incomplete packages stay `stand_aside` / `reject` / `watch`. Never a broker GO.

| # | Criterion | Status |
|---|---|---|
| 1 | Regime + equity scores (Phases 3–4) | ✅ |
| 2 | Long-premium options engine (Phase 5 / audit 6) | ✅ |
| 3 | Catalyst (official earnings/filings or ETF n/a) | ✅ |
| 4 | Fundamentals: official forecast-EPS **and** statements/indicators/industry when the SDK returns them (no invented numbers) | ✅ this slice (degrades if API/SDK missing) |
| 5 | Adversarial critique (rule-based; LLM hook unused in CI) | ✅ |
| 6 | Backtester: costs, slippage, no look-ahead, OOS or walk-forward, ≥1 long-premium setup | ✅ **minimal** (synthetic option mark, **not** historical OPRA — not a RESEARCH_COMPLETE blocker) |
| 7 | Paper journal + paper ledger (full loop, no broker risk) | ✅ simulated ledger + paper-only CLI (not a Webull paper account) |
| 8 | Daily/weekly text report CLI (`python -m trading_system report [--weekly]`) | ✅ text-only Grok brief; dashboard UI not required |
| 9 | Sandbox execution adapter | ❌ deferred / locked — **post-research**, not required for RESEARCH_COMPLETE |
| 10 | Explicit user unlock of `LIVE_APPROVAL` | ❌ never in this PR — **post-research** |

**Exit rule:** `RESEARCH_COMPLETE` is **true** when research items 1–7 (through the
paper journal) **and** the Phase 10 report CLI exist. Sandbox execution and LIVE
unlock are explicitly **out of scope** for this flag. Historical OPRA and a
visual dashboard are known limits, not research-complete blockers.

`phase9_complete` and `phase10_complete` being true does **not** unlock
`LIVE_EXECUTION`.
