## Phase 10 — Daily/weekly text report (research desk)

Architecture audit Phase 10: *Dashboard + alerts + daily/weekly reports*.  
This slice ships the **minimal text report** Grok can consume. No fancy UI.

Branch: `cursor/trading-system-phase10-research-complete-6e9d`  
Base: `cursor/trading-system-phase9-paper-journal-1d98` (PR #10)

`PHASE` is now **10**. Execution stays locked. `RESEARCH_COMPLETE` is **true** as a
research-desk flag only.

### Delivered
- `python -m trading_system report` — daily text brief
- `python -m trading_system report --weekly` — 7-day journal / backtest window
- Aggregates:
  - `status` (mode, providers, risk, paper cash)
  - `regime` (label, confidence, favored strategies)
  - `decide` stand_aside / watch / reject / paper-research candidate flags
  - paper journal snapshot (cash, P&L, open symbols)
  - backtest **pointer** (last recorded synthetic run or `backtest` CLI hint)
- Prefer `stand_aside` when packages are incomplete
- `trade_recommendation` / `go_signals_allowed` may be true only for complete
  **paper/research** candidates
- `go_signal` (broker GO) stays **false**
- `LIVE_EXECUTION_UNLOCKED` stays **false**
- Sandbox / live execution adapters are **not** imported or required
- `report` sends logging to **stderr** at WARNING+ so stdout stays the text brief
  (Webull SDK INFO must not pollute Grok's report)

### Honest limits (not RESEARCH_COMPLETE blockers)
- No visual dashboard / alerts UI
- Phase 7 backtest remains a synthetic long-premium mark (not historical OPRA)
- Not a Webull sandbox or official paper account
- LLM critic hook remains unused in CI

### Post-research (explicitly excluded)
- Sandbox execution adapter (audit Phase 11)
- `LIVE_APPROVAL` / `LIVE_EXECUTION` unlock (audit Phase 12)

### Try
```bash
python -m trading_system status
python -m trading_system report --symbols AAPL MSFT SPY
python -m trading_system report --weekly --symbols AAPL
python -m trading_system decide --symbols AAPL
python -m trading_system journal
pytest -q
```
