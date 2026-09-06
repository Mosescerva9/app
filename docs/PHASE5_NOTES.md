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
  - Snapshot batches include **standard OCC only** (`^[A-Z]+\\d{6}[CP]\\d{8}$` and
    `symbol.startswith(underlying)`). Adjusted roots from `get_option_contracts`
    (`2NVDA261016C00210000`) are skipped — they are real series, but
    `get_option_snapshot` returns 417 INVALID_SYMBOL if they are in the batch.
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

**Operator-confirmed (box):** `get_history_bar` is newest→oldest. Unsorted `closes[-1]` was SPY ~709 (oldest) vs snapshot/newest ~770.19 → false STRONG_BEAR. After oldest→newest, last_close=770.19 and regime is CHOPPY ~0.8.

**What we verified and fixed:**
1. **Chronology** — Webull adapter + `ensure_chronological_bars()` before regime/scanner feature extraction. Regression: reverse-chronological input still yields last_close=770.19, not 709. Nested envelopes (`result[{symbol, result:[bars]}]`) are unwrapped.
2. **Category** — official Data API uses `US_STOCK` vs `US_ETF`. SPY/QQQ/IWM and the default ETF universe resolve as `US_ETF` with a `US_STOCK` fallback.
3. **Request types (live box, `api.webull.com`)** — `GET /openapi/market-data/stock/bars` returns **400 Parameters type miss match** if `count` is a string or if `real_time_required` / `trading_sessions` are sent. Operator probe: `get_history_bar('SPY','US_ETF','D', count=10)` (int, no extras) → 200. The installed SDK *accepts* those optional kwargs, but production query types do not. We pass **integer `count` only** and rely on official defaults for latest RTH daily bars.

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
