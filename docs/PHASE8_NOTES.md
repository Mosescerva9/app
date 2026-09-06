## Phase 8 — Decision Packages (catalyst + adversarial)

Architecture audit Phase 8: *Adversarial AI + decision packages*.  
Branch: `cursor/trading-system-decision-packages-8955`  
Base: `cursor/trading-system-research-hardening-251c` (PR #7 options hardening)

This repo’s earlier local numbering used Phase 5 for options (audit Phase 6).
`PHASE` is now **8** to match the audit deliverable. Execution stays locked.

### Delivered
- Auditable **Decision Package** JSON from `python -m trading_system decide`
  - Existing technical / regime / options scores
  - **Catalyst** section (earnings proximity + simple filing flags)
  - **Adversarial** section: `why_trade_fails`, `instant_reject_conditions`,
    `better_strike_dte_or_stand_aside`, `confidence_penalty`
- `CatalystProvider` interface
  - **Mock** (default / CI): never invents news or earnings dates; returns
    `available=false` + unavailable notes unless a test fixture is injected
  - **Webull** when `MARKET_DATA_PROVIDER=webull` (or `CATALYST_PROVIDER=webull`):
    official SDK only
    - `DataClient.fundamentals.get_earnings_calendar`
      (`GET /openapi/fundamentals/stock/earnings-calendar`)
    - `DataClient.fundamentals.get_sec_filings`
      (`GET /openapi/fundamentals/stock/filings`)
    - Field mapping from official domain objects (`expectedPublishDate`,
      `epsActual`, filing `title` / `url` / `publishDate`)
    - Missing SDK method, HTTP/entitlement errors, or empty calendars →
      unavailable notes; **no fabricated headlines**
- Rule-based `RuleBasedAdversarialCritic` (deterministic)
- `NullLLMCritic` hook for a later overlay — **not called in CI**
- Prefer **stand aside** when catalyst is unknown and technicals are weak
- Instant reject when official earnings are ≤2 days out (IV crush / binary event)
- Long premium only; `$1,500` / `$150` risk budget unchanged
- `LIVE_EXECUTION_UNLOCKED` remains `False`

### Still deferred
- Full fundamentals scoring (income/balance/cash-flow, analyst targets)
- Backtester / walk-forward (audit Phase 7)
- Paper journal + paper ledger (audit Phase 9)
- Dashboard / Grok daily brief (audit Phase 10)
- Sandbox / live execution (audit Phases 11–12)
- Live LLM critique (hook exists; no API key required)

### Try
```bash
python -m trading_system decide --symbols AAPL MSFT NVDA SPY --min-equity-score 50
python -m trading_system status
pytest -q
```
