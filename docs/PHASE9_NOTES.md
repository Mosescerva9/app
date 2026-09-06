## Phase 9 — Paper journal loop (no broker)

Architecture audit Phase 9: *Paper trading mode + journal*.  
Branch: `cursor/trading-system-phase9-paper-journal-1d98`  
Base: `cursor/trading-system-phase7-backtester-56e4` (PR #9)

`PHASE` is now **9**. Execution stays locked. `RESEARCH_COMPLETE` stays **false**.

### Delivered
- Structured paper ledger (`data/paper_journal.json`, gitignored)
  - Simulated cash, open/closed long-premium positions, fills, journal notes
  - P&L: realized + mark-to-market unrealized
  - Risk caps aligned to the **$1,500 / $150** book:
    - max risk/trade $150 (10%)
    - max 2 simultaneous positions
    - daily loss halt $75 (5%)
    - weekly loss halt $150 (10%)
  - Cash cannot go negative; oversize debit is refused
- Explicit **paper-only** CLI (never calls `place_order`):
  - `python -m trading_system paper-open SYMBOL` — simulate buy-to-open from a Decision Package
  - `python -m trading_system paper-close POSITION_ID --exit-mark USD` — simulate sell-to-close
  - `python -m trading_system paper-note "text"` — journal without changing cash
  - `python -m trading_system journal` — ledger snapshot
- Incomplete / `stand_aside` / `reject` / `watch` packages are **not** opened
- `phase9_complete=true` because the loop is real (still not a Webull paper account)
- `status` exposes `paper_journal=paper_ledger`, `paper_account`, and an honest `research_complete_checklist`
- Backtest rows remain **annotations** (do not debit paper cash)

### Gates (prefer stand aside)
A paper open is refused when any of these hold:
- `incomplete_research` or missing required dimensions
- recommendation is not `candidate`
- no long-premium option (`long_call` / `long_put` only)
- emergency stop, cash, per-trade cap, max positions, daily/weekly loss halt

### Still deferred / honest limits
- Not a Webull sandbox or official paper account
- No broker fills, no order preview, no `place_order`
- Historical OPRA option chains (Phase 7 still uses a synthetic mark)
- Dashboard + Grok daily brief (audit Phase 10)
- Sandbox / live execution (audit Phases 11–12)

### RESEARCH_COMPLETE
**False.** Item 7 on [`docs/RESEARCH_COMPLETE.md`](RESEARCH_COMPLETE.md) is now done. Items 8–10 (dashboard/Grok, sandbox adapter, live unlock) remain deferred. Phase 7 remains a **minimal** synthetic backtest, not historical OPRA.

### Try
```bash
python -m trading_system status
python -m trading_system decide --symbols AAPL
python -m trading_system paper-open AAPL
python -m trading_system journal
python -m trading_system paper-close PAPER-0001 --exit-mark 80
python -m trading_system paper-note "stood aside — incomplete catalyst"
pytest -q
```
