## Phase 4 — Opportunity Scanner

Branch: `cursor/trading-system-phase4-scanner-e1ab`

### Delivered
- Liquid default universe (large-caps + ETFs)
- OHLCV feature extraction (trend, momentum, ATR%, volume z, pullback/extension)
- Weighted scoring with documented base weights and renormalization when dimensions are missing
- Deferred dimensions explicitly excluded: `options_quality`, `catalyst`, `fundamental`
- Setup selection: breakout, pullback, momentum, mean-reversion, relative strength, stand-aside
- Provisional entry / stop / target + RR
- Regime-fit scoring using Phase 3 regime engine
- CLI: `python -m trading_system scan --benchmark SPY --min-score 55`
- Decisions: `CANDIDATE` / `WATCH` / reject (filtered from ranked list)
- Empty scans now include per-symbol `rejects` / `empty_scan_diagnosis` (`no_setup`, `regime_fit`, `score_floor`, `error`)

### Still locked
- Live order placement
- Multi-leg options / backtester (later phases)

### Try
```bash
python -m trading_system scan
python -m trading_system scan --symbols AAPL MSFT NVDA SPY --min-score 50
pytest -q
```
