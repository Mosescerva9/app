# AI Trading Research System

Phase 2 scaffold: **read-only market data + account reads**, research mode, hard risk defaults for a ~$1,000 account.

**No live order placement in this phase.**

## What works now

| Capability | Status |
|---|---|
| `RESEARCH` / `PAPER` / `LIVE_APPROVAL` modes | Configured; live execution **locked** |
| Mock market data (bars, snapshots, options snapshots) | ✅ |
| Webull market data adapter (official SDK) | ✅ (needs OpenAPI keys + Advanced Quotes) |
| Mock broker account reads | ✅ |
| Webull broker read adapter (accounts/positions/orders) | ✅ (needs keys; sandbox default) |
| Risk limit object ($ risk math + emergency stop) | ✅ |
| CLI: `status`, `bars`, `snapshots`, `account` | ✅ |
| Order placement | ❌ intentionally disabled |

Architecture audit: [`docs/ARCHITECTURE_AUDIT.md`](docs/ARCHITECTURE_AUDIT.md)

## Quick start (offline / mock)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

python -m trading_system status
python -m trading_system bars AAPL --timespan D --count 20
python -m trading_system snapshots AAPL SPY QQQ
python -m trading_system account
pytest -q
```

## Connect Webull (read-only)

1. Create App Key / Secret at [Webull Open API Management](https://www.webull.com/center#/openapi)
2. Subscribe to **OpenAPI Advanced Quotes** (app quotes ≠ API quotes)
3. Prefer sandbox first: `WEBULL_API_ENDPOINT=api.sandbox.webull.com`
4. In `.env`:

```env
TRADING_MODE=RESEARCH
MARKET_DATA_PROVIDER=webull
BROKER_PROVIDER=webull
WEBULL_APP_KEY=...
WEBULL_APP_SECRET=...
WEBULL_ACCOUNT_ID=...
WEBULL_API_ENDPOINT=api.sandbox.webull.com
```

5. Re-run CLI commands above.

## Risk defaults (~$1,000)

- Max risk/trade: 4% → **$40**
- Max positions: **2**
- Max daily loss: 5% → **$50**
- Max weekly loss: 10% → **$100**
- `EMERGENCY_STOP=true` blocks trading checks

## Grok oversight (next wiring)

- Use **Webull Cloud MCP** (`https://api.webull.com/mcp`) read-only for balances/positions in chat
- Point Grok at daily reports this system will produce in later phases
- Never grant Grok unsupervised order placement

## Phase map

1. Architecture audit ✅  
2. Scaffold + market/account data ✅ (this PR)  
3. Regime engine  
4. Scanner / scoring  
5. Options engine  
6. Backtester  
7. Adversarial review  
8. Paper trading  
9. Dashboard + Grok daily brief  
10. Sandbox execution  
11. `LIVE_APPROVAL` only after your explicit go-ahead  

## Safety rules

- Secrets only in `.env` / secret manager  
- `place_order` raises in Phase 2  
- `LIVE_APPROVAL` cannot execute until `LIVE_EXECUTION_UNLOCKED=True` in a future phase **and** you confirm  
