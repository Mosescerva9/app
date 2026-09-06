## Phase 7 — Backtester (audit) + richer official fundamentals

Architecture audit Phase 7: *Backtester (costs, slippage, OOS, walk-forward)*.  
This slice also deepens Phase 8 fundamentals beyond forecast-EPS.

Branch: `cursor/trading-system-phase7-backtester-56e4`  
Base: `cursor/trading-system-decision-packages-8955` (PR #8)

`PHASE` stays **8** (Decision Packages remain the latest complete research surface).
Execution stays locked. `RESEARCH_COMPLETE` stays **false**.

### Delivered

#### Backtester
- `python -m trading_system backtest [SYMBOL] --split oos|walk_forward`
- Setup: **regime-filtered equity signal → synthetic long call/put**
  - Signal at bar close using only `bars[:i+1]` (regime + SMA20/SMA50 alignment)
  - Fill at **next bar open** (no look-ahead)
  - CHOPPY / EVENT_DRIVEN / UNKNOWN → stand aside
- Cost model: commission per contract (round trip) + `slippage_pct` of debit/mark each side
- Synthetic long-premium mark (honest proxy, **not** a historical OPRA chain):
  - Slightly OTM strike, debit clamped to the $150 book
  - Exit mark = intrinsic + linearly decaying extrinsic
  - Stop / target / time; stop-first if both print in the same bar; gap-through-stop fills at open
- Splits:
  - `oos`: chronological 70/30 in-sample vs out-of-sample labels
  - `walk_forward`: rolling train/test folds; only test-fold entries are kept
- Tests use `synthetic_trend_bars` / `synthetic_chop_bars` — no live quotes

#### Richer fundamentals (official SDK only)
Installed `webull-openapi-python-sdk` `DataClient.fundamentals` methods used:

| Method | Official path |
|---|---|
| `get_forecast_eps` | `GET /openapi/fundamentals/stock/forecast-eps` |
| `get_financials_indicators` | `GET /openapi/fundamentals/financial/indicators` |
| `get_financials_income` | `GET /openapi/fundamentals/financial/income` |
| `get_financials_cashflow` | `GET /openapi/fundamentals/financial/cash-flow` |
| `get_financials_balance_sheet` | `GET /openapi/fundamentals/financial/balance-sheet` |
| `get_industry_comparison` | `GET /openapi/fundamentals/stock/industry-comparison` |

- Mock / CI: never invents EPS, ratios, or statements
- Missing method, HTTP/entitlement error, or empty payload → that slice is unavailable
- ETFs: official stock financials document `US_STOCK` only → `not_applicable`
- **Not called:** `DataClient.instrument.get_analyst_target_price` / `get_analyst_rating` / `get_company_profile` (not fundamentals.*)
- **Not called:** fund-* methods (ETF holdings analytics) — would be a later explicit slice

Package-level fundamentals dimension is satisfied by official EPS beat/miss **or** official statements/indicators (`present`/`partial`) **or** ETF `not_applicable`.

#### Phase 9 (later slice)
Phase 9 is no longer a stub. See [`docs/PHASE9_NOTES.md`](PHASE9_NOTES.md).
Backtest rows remain journal **annotations** and do not debit paper cash.

### Still deferred / honest limits
- Historical option chains / IV surface (backtest uses a decaying-extrinsic proxy)
- Dashboard / Grok brief
- Live LLM critique
- Sandbox / live execution
- Analyst targets (instrument API, not this slice)

### RESEARCH_COMPLETE
**False.** Criteria: see [`docs/RESEARCH_COMPLETE.md`](RESEARCH_COMPLETE.md).

### Try
```bash
python -m trading_system backtest SPY --count 180 --split oos
python -m trading_system backtest AAPL --split walk_forward
python -m trading_system journal
python -m trading_system decide --symbols AAPL MSFT
python -m trading_system status
pytest -q
```
