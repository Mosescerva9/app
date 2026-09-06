## Phase 2 status (implemented)

Scaffold delivered on branch `cursor/trading-system-phase2-scaffold-e1ab`:

- Package: `trading_system/`
- Modes: `RESEARCH` (default), `PAPER`, `LIVE_APPROVAL` (execution locked)
- Market data: mock + Webull OpenAPI read adapter
- Broker: mock + Webull read adapter (accounts/positions/orders)
- Risk limits object (now default ~$1,500 / 10% → $150 per trade)
- CLI: `python -m trading_system {status,bars,snapshots,account}`
- Tests: mock-only, no live orders

**Still locked:** order placement, autonomous live trading. Later phases added regime/scanner/options/decision packages; execution remains locked.
