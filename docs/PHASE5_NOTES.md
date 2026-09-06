## Phase 5 — Options Analysis Engine (research hardening)

Branch: `cursor/trading-system-research-hardening-251c`  
Base: `cursor/trading-system-phase5-options-e1ab`

> Note: Architecture audit listed quantitative scoring as Phase 5 and options as Phase 6.
> Phase 4 already shipped weighted scoring, so this repo keeps **options selection as Phase 5**.

### Delivered
- Normalized `OptionContract` model (bid/ask/mid, OI, IV, Greeks, premium×100)
- `OptionChainProvider` + offline `MockOptionChainProvider` (synthetic chains)
- **`WebullOptionChainProvider`** when `MARKET_DATA_PROVIDER=webull`
  - Official `DataClient.instrument.get_option_contracts` (`GET /openapi/instrument/option/contracts`)
  - Official `option_market_data.get_option_snapshot` (max 20 symbols; US options)
  - Clear entitlement / `chain_error` notes when OPRA / Advanced Quotes is missing
- Hard filters for ~$1,500 account / **~$150 max premium×100** (`ACCOUNT_EQUITY_USD=1500`, `MAX_RISK_PER_TRADE_PCT=0.10`)
  - DTE 30–60
  - |delta| 0.25–0.45
  - minimum open interest
  - max bid/ask spread %
  - LONG → calls only; SHORT → long puts only
- Weighted contract scoring: liquidity, delta_fit, iv_sanity, theta_drag, risk_fit
- `OptionsAnalysisEngine` selects contracts from Phase 4 equity opportunities
- CLI: `python -m trading_system options`
- Live order placement remains **hard-disabled** (`LIVE_EXECUTION_UNLOCKED=False`)

### Bar history vs live snapshots
Operator report: SPY `regime`/`bars` `last_close` ≈ 709 while production snapshots ≈ 770.

**What we verified and fixed (no live keys in CI):**
1. **Payload unwrap** — official history envelopes nest `result[{symbol, result:[bars]}]` (and sometimes `bars`). The old parser treated the outer envelope as a bar, or kept newest-first order so `closes[-1]` was the *oldest* print (~90 sessions back). Bars are now extracted recursively and **sorted oldest→newest**. `last_close` is always the newest bar.
2. **Category** — official Data API uses `US_STOCK` vs `US_ETF`. SPY/QQQ/IWM and the default ETF universe resolve as `US_ETF` with a `US_STOCK` fallback.
3. **Session** — daily history requests `real_time_required=Y` and `trading_sessions=RTH` so they share the snapshot default (extended hours off).

**Discarded as primary cause:** sandbox-vs-prod mix can still happen if `WEBULL_API_ENDPOINT` differs between commands, but a ~8% gap is the signature of reading the oldest bar as last close, not a 15-minute delay.

**Remaining known lag (documented, not a bug):**
- In-progress RTH daily close vs last print (usually cents to a point).
- Delayed-quote entitlement auto-offsets `end_time` (official SDK note).
- After-hours: daily close stays RTH; snapshot last stays RTH unless you later request extended hours.
- Weekend/holiday: last completed session vs last snapshot of that session.

`python -m trading_system bars SPY` and `regime` now include `snapshot_last` / `last_close_vs_snapshot_pct` so a remaining gap is visible.

### Account reads
- Official fields: `total_net_liquidation_value`, `total_cash_balance`, `account_currency_assets[].buying_power`.
- `ACCOUNT_ACCESS_DENIED` and account-id mismatches print the endpoint plus: use `account_id` from `TradeClient.account_v2.get_account_list()` **on the same host**.
  - `api.sandbox.webull.com` IDs ≠ `api.webull.com` IDs
  - Webull-app paper-trading IDs are not OpenAPI account IDs
- Endpoints used are only those already in the official SDK (`/openapi/account/list`, `/openapi/assets/balance`, …). No invented paths.

### Scanner rejects
`scan` JSON includes `rejects`, `reject_counts`, and `empty_scan_diagnosis` when `opportunity_count=0` (`no_setup` / `regime_fit` / `score_floor` / `error`).

### Still locked / deferred
- Live / paper order placement, preview-as-submit, autonomous execution
- Multi-leg strategies (credit spreads, iron condors, short premium)
- Backtester
- Paper ledger / `LIVE_APPROVAL` unlock

### Try
```bash
python -m trading_system status
python -m trading_system bars SPY --timespan D --count 30
python -m trading_system snapshots SPY
python -m trading_system regime --benchmark SPY
python -m trading_system scan --symbols AAPL MSFT NVDA SPY --min-score 50
python -m trading_system options --symbols AAPL MSFT NVDA SPY --min-option-score 50
python -m trading_system account
pytest -q
```
