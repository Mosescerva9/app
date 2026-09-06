# AI Trading Research System

Read-only market data, regime, opportunity scan, and **long-premium options research**. Default account model: **$1,500 equity / ~$150 max risk per trade**.

**No live or paper order placement.** `LIVE_EXECUTION_UNLOCKED` stays false.

## What works now

| Capability | Status |
|---|---|
| `RESEARCH` / `PAPER` / `LIVE_APPROVAL` modes | Configured; live execution **locked** |
| Mock market data + mock option chains | ✅ offline / tests |
| Webull market data (official SDK) | ✅ needs OpenAPI keys + Advanced Quotes |
| Daily bars aligned with RTH snapshots | ✅ sorted + ETF category; live call is `count=int` only (no session kwargs) |
| Webull option chain adapter | ✅ `get_option_contracts` + option snapshots (or clear entitlement errors) |
| Mock broker account reads | ✅ |
| Webull broker read adapter | ✅ same-endpoint account ids; sandbox ≠ prod |
| Opportunity scan with reject diagnosis | ✅ |
| Options engine (long calls / long puts only) | ✅ ~$150 premium×100 cap |
| CLI: `status`, `bars`, `snapshots`, `regime`, `scan`, `options`, `account` | ✅ |
| Order placement | ❌ intentionally disabled |

Architecture audit: [`docs/ARCHITECTURE_AUDIT.md`](docs/ARCHITECTURE_AUDIT.md)  
Options / hardening notes: [`docs/PHASE5_NOTES.md`](docs/PHASE5_NOTES.md)

## Quick start (offline / mock)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

python -m trading_system status
python -m trading_system bars AAPL --timespan D --count 20
python -m trading_system snapshots AAPL SPY QQQ
python -m trading_system regime
python -m trading_system scan
python -m trading_system options
python -m trading_system account
pytest -q
```

## Connect Webull (read-only)

1. Create App Key / Secret at [Webull Open API Management](https://www.webull.com/center#/openapi)
2. Subscribe to **OpenAPI Advanced Quotes**. Options chains also need **OPRA** options market data. App/desktop quotes ≠ API quotes.
3. Set the host that matches the account you will read:
   - Sandbox / UAT: `WEBULL_API_ENDPOINT=api.sandbox.webull.com`
   - Production: `WEBULL_API_ENDPOINT=api.webull.com`
4. In `.env`:

```env
TRADING_MODE=RESEARCH
MARKET_DATA_PROVIDER=webull
BROKER_PROVIDER=webull
WEBULL_APP_KEY=...
WEBULL_APP_SECRET=...
WEBULL_API_ENDPOINT=api.sandbox.webull.com
WEBULL_ACCOUNT_ID=
ACCOUNT_EQUITY_USD=1500
MAX_RISK_PER_TRADE_PCT=0.10
```

5. Run `python -m trading_system account` and copy an `account_id` from **that** host into `WEBULL_ACCOUNT_ID`.
   - Sandbox OpenAPI ids do not work on `api.webull.com`
   - Production ids do not work on `api.sandbox.webull.com`
   - Paper-trading ids from the Webull app are not OpenAPI account ids (`ACCOUNT_ACCESS_DENIED`)
6. `bars` / `regime` print `snapshot_last` next to `last_close` so you can confirm they agree in the same RTH session.

## Risk defaults (~$1,500)

- Max risk/trade: 10% → **$150** (option premium×100 must fit this)
- Max positions: **2**
- Max daily loss: 5% → **$75**
- Max weekly loss: 10% → **$150**
- `EMERGENCY_STOP=true` blocks trading checks

Long premium only in this phase: LONG equity bias → long calls; SHORT → long puts. No credit spreads or naked short premium.

## Safety rules

- Secrets only in `.env` / secret manager — never commit real keys
- `place_order` raises
- `LIVE_APPROVAL` cannot execute until `LIVE_EXECUTION_UNLOCKED=True` in a future phase **and** you confirm

## Phase map

1. Architecture audit ✅
2. Scaffold + market/account data ✅
3. Regime engine ✅
4. Scanner / scoring ✅
5. Options engine + research hardening ✅ (this branch)
6. Backtester (deferred)
7. Adversarial review
8. Paper trading ledger
9. Dashboard + Grok daily brief
10. Sandbox execution (still gated)
11. `LIVE_APPROVAL` only after your explicit go-ahead
