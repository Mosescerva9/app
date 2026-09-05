## Phase 3 — Market Regime Engine

Implemented on branch `cursor/trading-system-phase3-regime-e1ab`.

### Delivered
- Deterministic feature extraction from OHLCV (trend, ATR%, realized vol, choppiness, momentum persistence, gaps, volume z)
- Rule-based classifier for: strong/weak bull/bear, high/low vol trend, mean-reverting, choppy, event-driven, unknown
- Strategy playbook (favored / avoided / risks) per regime
- Optional VIX enrichment when provider can snapshot `VIX`
- CLI: `python -m trading_system regime --benchmark SPY --lookback 90`
- Tests with synthetic bull/bear/chop series

### Still locked
- Live order placement
- LLM override of regime labels (explain-only later)

### Not yet (later phases)
- Scanner / scoring / options engine
- Backtests conditioned on regime
- Strategy decay monitor
