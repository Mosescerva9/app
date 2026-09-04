# Discord → Webull Options Alert Bot

Low-latency copy trader: listens to Discord options alerts over the gateway WebSocket, parses the contract, and places the matching single-leg options order on Webull.

## Why this is fast

- **Discord gateway push** (not channel polling) — messages arrive in tens of milliseconds
- **Hot-path parse → order** with message-id dedupe and local position matching
- **Aggressive limit prices** via configurable slippage (Webull options do **not** support market orders)
- Webull auth is established at startup so the first alert does not pay a cold-start cost

Typical Discord → submit path is designed to finish well under a second on a healthy network; actual fill time still depends on Webull and the options market.

## Requirements

1. **Discord bot** with Message Content Intent enabled, invited to the alert server with read access to the alert channel(s)
2. **Webull OpenAPI** app key/secret from [Open API Management](https://www.webull.com/center#openApiManagement) and an account that can trade options
3. Python 3.10+

> Start with `DRY_RUN=true` and Webull **sandbox** (`api.sandbox.webull.com`) until parses and order payloads look correct.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install pytest  # for tests
cp .env.example .env
# edit .env with Discord + Webull credentials
```

### Discord bot checklist

1. Create an application at https://discord.com/developers/applications
2. Bot → Reset Token → put in `DISCORD_BOT_TOKEN`
3. Enable **Message Content Intent**
4. OAuth2 URL Generator → scopes: `bot` → permissions: Read Messages/View Channels, Read Message History
5. Invite the bot into the alerts server
6. Copy channel ID(s) into `DISCORD_CHANNEL_IDS` (Developer Mode → right-click channel → Copy ID)

### Webull checklist

1. Create API credentials in Webull Open API Management
2. Prefer sandbox first: `WEBULL_API_ENDPOINT=api.sandbox.webull.com`
3. Set `WEBULL_APP_KEY`, `WEBULL_APP_SECRET`, `WEBULL_ACCOUNT_ID`
4. Confirm options trading is enabled on the account
5. Set `DRY_RUN=false` only when ready for live / paper API orders

## Run

```bash
python -m bot
```

## Supported alert formats

The parser accepts common Discord alert shapes, for example:

```text
BTO AAPL 220C 3/21/26 @ 1.25 x2
BUY TSLA 7/17 250 PUT @ 8.50
STC NVDA 100P 2026-07-17 @ 6.00
Symbol: AAPL | Strike: 220 | Type: CALL | Exp: 2026-06-19 | Action: BUY | Price: 11.25 | Qty: 1
```

Actions: `BUY` / `BTO` / `ENTRY` / `ADD` → buy; `SELL` / `STC` / `EXIT` / `CLOSE` / `TRIM` → sell.

If your server uses a different template, paste a few real samples and extend `bot/parser.py` `PATTERNS`.

## Safety controls

| Variable | Purpose |
|---|---|
| `DRY_RUN` | Log orders without submitting |
| `MAX_QUANTITY` | Cap contracts per alert |
| `BUY_SLIPPAGE` / `SELL_SLIPPAGE` | Widen limit for faster fills |
| `REQUIRE_LIMIT_PRICE` | Skip alerts without a price |
| `DISCORD_ALERT_AUTHOR_IDS` | Only trust specific alert bots/users |
| `DISCORD_CHANNEL_IDS` | Only watch the alert channel(s) |

Open positions are tracked in SQLite (`POSITIONS_DB_PATH`) so exits size against what this bot actually opened.

## Tests

```bash
pytest -q
```

## Architecture

```text
Discord gateway message
        │
        ▼
  filter channel/author
        │
        ▼
  parse alert (ticker/strike/type/exp/side/qty/price)
        │
        ▼
  size + slip limit price
        │
        ▼
  Webull order_v3.place_order (OPTION / SINGLE / LIMIT)
        │
        ▼
  update local positions.db
```

## Important notes

- Trading involves risk of loss. This software can place real orders when `DRY_RUN=false`.
- You must be allowed to automate trading under Webull’s OpenAPI terms and have permission to run a bot in the Discord server.
- Webull options orders are **limit-only**; without enough slippage on fast movers, fills can miss.
- Alert format mismatch is the #1 failure mode — validate with dry-run logs before going live.
