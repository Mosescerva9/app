## Phase 5 — Options Analysis Engine

Branch: `cursor/trading-system-phase5-options-e1ab`

> Note: Architecture audit listed quantitative scoring as Phase 5 and options as Phase 6.
> Phase 4 already shipped weighted scoring, so this repo advances **options selection as Phase 5**.

### Delivered
- Normalized `OptionContract` model (bid/ask/mid, OI, IV, Greeks, premium×100)
- `OptionChainProvider` + offline `MockOptionChainProvider` (synthetic chains)
- Hard filters for ~$1k account:
  - DTE 30–60
  - |delta| 0.25–0.45
  - minimum open interest
  - max bid/ask spread %
  - premium×100 ≤ per-trade risk budget (~$40)
  - LONG → calls only; SHORT → long puts only
- Weighted contract scoring: liquidity, delta_fit, iv_sanity, theta_drag, risk_fit
- `OptionsAnalysisEngine` selects contracts from Phase 4 equity opportunities
- CLI: `python -m trading_system options`
- Live order placement remains **hard-disabled**

### Still locked / deferred
- Live / paper order placement
- Real Webull options chain adapter (needs Advanced Quotes)
- Multi-leg strategies (spreads, iron condors)
- Backtester (later phase)

### Try
```bash
python -m trading_system options
python -m trading_system options --symbols AAPL MSFT NVDA SPY --min-option-score 50
pytest -q
```
