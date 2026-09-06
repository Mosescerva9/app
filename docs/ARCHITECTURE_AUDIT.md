# Architecture Audit — AI Trading Research & Execution System

**Status:** Phase 1 audit complete; Phase 2 scaffold implemented (read-only). No live order placement.  
**Date:** 2026-09-05  
**Capital assumption:** ~$1,000 (Phase 1). Later research phases use **$1,500 / 10% → $150 per trade**.  
**Default mode:** `RESEARCH` → then `PAPER` → only later `LIVE_APPROVAL`

---

## A. Current project inspection

| Item | Finding |
|------|---------|
| Repo | `github.com/Mosescerva9/app` |
| Current `main` | Near-empty (`README.md` only) |
| Existing feature branch | `cursor/discord-webull-options-bot-e1ab` — Discord alert → Webull copy-trader |
| Fit for new goal | **Poor.** That bot follows external Discord signals. New goal is an independent research/execution system with regime detection, scoring, adversarial review, and explicit approval. |
| Recommendation | **Do not extend the Discord bot as the core.** Keep any reusable Webull order-shaping ideas as reference only. Build a new modular system under e.g. `trading_system/`. |
| This cloud environment | `webull-uat` MCP namespace is **currently broken** (tool discovery failed). Do not treat it as available until fixed/re-authed. |

---

## B. Webull — current official capabilities (source of truth)

Primary docs: [developer.webull.com](https://developer.webull.com/apis/docs)

### B1. What exists officially

| Capability | Official path | Notes |
|------------|---------------|-------|
| Trading API (stocks/options/futures/crypto/events) | OpenAPI + Python SDK | App Key / App Secret; place / replace / cancel |
| Account list, balances, positions | Trading API | Supported |
| Order history / open orders / detail | Trading API | Supported |
| Order event stream | gRPC Trade Events | Supported |
| Market data (stocks, options, etc.) | Market Data API | **Separate OpenAPI Advanced Quotes subscription required** (app/desktop quotes ≠ OpenAPI) |
| Sandbox / UAT | `api.sandbox.webull.com` | Official test environment |
| Cloud MCP | `https://api.webull.com/mcp` | OAuth; managed; **read-focused** (account, positions, order query, market data, fundamentals/filings) |
| Local MCP | `webull-inc/webull-openapi-mcp` | App Key/Secret; **includes order placement** (stocks/options/strategies) |
| Agent Skills / CLI | Official repos | Useful for Grok/Cursor operators |

### B2. Capability matrix (what we can build against)

| Need | Feasible? | How |
|------|-----------|-----|
| Connect Webull account | Yes | OpenAPI keys and/or Cloud MCP OAuth |
| Read buying power / positions | Yes | Trading API / MCP |
| Read orders | Yes | Trading API / MCP |
| Submit / modify / cancel stock orders | Yes | Trading API or **Local** MCP |
| Submit / modify / cancel option orders | Yes | Trading API or **Local** MCP (limit/stop; **no option MARKET**) |
| Options chain / snapshot / bars | Yes (with data sub) | Market Data API / Local MCP option tools |
| Paper / simulation | Partial | Official **sandbox API**; plus our own internal `PAPER` ledger |
| Unrestricted autonomous live trading | **Must not enable** | Product rule + hard gates |

### B3. Critical Webull design facts

1. **Cloud MCP ≠ full execution path.** Official Cloud MCP capability groups emphasize Account Infos, Order Query, Market Data, Security Master. Order **placement** is documented on **Local MCP / Trading API**, not as the primary Cloud MCP trading surface.
2. **Grok oversight path:** Webull documents Cloud MCP connection for ChatGPT / Claude / **Grok**. Use Cloud MCP (read) + our system’s daily reports for oversight. Use Local MCP / Trading API only behind approval gates for execution.
3. **Options are limit/stop based** — no option MARKET orders in the Options Trading docs.
4. **Market data is paid/subscribed for OpenAPI** — do not assume free app quotes work for the API.
5. **Rate limits exist** — Market Data API documented example: **300 req/min** (full per-endpoint table on Webull Rate Limits page). Design scanners with caching and batching.
6. **Secrets** — App Key/Secret only in env / secret manager; never in git.

### B4. This environment’s Webull MCP

- Namespace `webull-uat` is registered but **failed live tool discovery**.
- Until fixed: design against official SDK/MCP interfaces; verify with sandbox credentials in Phase 11+.

---

## C. TradingView — current official integration options

Official support: [Webhook alerts](https://www.tradingview.com/support/solutions/43000529348-how-to-configure-webhook-alerts/)

| Approach | Allowed for us? | Role |
|----------|-----------------|------|
| Charts / Pine / visualization | Yes | Human charting layer |
| Alert webhooks (HTTPS POST, ports 80/443, ~3s timeout, 2FA required) | Yes (paid plan) | Optional signal/event input into our system |
| Public retail market-data API | **No** | Do not depend on one |
| Scraping / unofficial sockets | **No** | Violates ToS; fragile; out of scope |
| Broker REST API | Broker partners only | Not available as a retail shortcut |

**Decision:** TradingView = charts + optional webhooks. Machine-readable OHLCV/options/news come from Webull Market Data API and other licensed providers. Never scrape TradingView.

---

## D. GPT-6 Astra / orchestration layer — what can and cannot connect

| Claim | Reality check |
|-------|----------------|
| “GPT-6 Astra as trading brain” | Astra (per public reporting ~Sept 2026) is a **general agentic** model (computer use, coding, tools/MCP), **not** a certified options-trading specialist. |
| “Model that proves excellent at trading options” | **Not assumed.** Options edge must come from **measurable strategies + backtests + regime filters**, with LLMs for orchestration, explanation, and adversarial critique. |
| Connect Astra to Webull | Feasible via **MCP** (Cloud read; Local/API for trade) and/or our HTTP orchestration API — subject to OpenAI/Webull account access. |
| Connect Astra to our system | Build our own **Trading Intelligence API** with structured JSON schemas; Astra/Grok call tools — they do not replace risk engines. |
| Free-form chat = approve trade | **Forbidden.** Only explicit `APPROVE TRADE` / `APPROVE TRADE #N`. |

**Orchestration rule:** LLMs propose and critique; **deterministic engines** score, size, gate, and execute.

---

## E. Simplest architecture that still meets the objective

Do **not** build 12 agents as separate long-running services on day one. Build **one modular monolith** with hard interfaces, then expose agent “roles” as prompt+tool profiles over the same engines.

```
┌─────────────────────────────────────────────────────────────────┐
│ YOU  ↔  Chat Ops (Grok / Astra / Cursor)                        │
│         - daily briefing, Q&A, APPROVE TRADE                    │
│         - Webull Cloud MCP (read-only oversight)                │
└───────────────────────────────┬─────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────┐
│ Orchestrator API (structured commands only)                     │
│ MODE = RESEARCH | PAPER | LIVE_APPROVAL                         │
│ EMERGENCY_STOP                                                  │
└───┬───────────┬───────────┬───────────┬───────────┬─────────────┘
    │           │           │           │           │
    ▼           ▼           ▼           ▼           ▼
 Market Data  Regime    Scanner+     Options     Risk +
 Adapter      Engine    Scoring      Engine      Adversarial
 (Webull +    (rules+   (weighted)   (contract   (hard limits
  optional     stats)                 quality)    + LLM critique)
  providers)
    │                                   │
    └──────────────┬────────────────────┘
                   ▼
            Decision Package (auditable JSON)
                   │
                   ▼  explicit approval only
            Execution Adapter
            (Webull Trading API / Local MCP)
            PAPER ledger first
                   │
                   ▼
            Journal + Strategy Health + Dashboard
```

**Why this is simplest:** one deployable app, shared DB, testable modules, Grok talks to reports + Cloud MCP without needing write access.

---

## F. Technical architecture diagram (logical)

```
ME
 ↓
GPT-6 Astra / Grok (orchestration + daily chat)
 ↓
Trading Intelligence Layer (our code)
 ├── Market Data Service
 ├── News/Events Service (earnings, filings, macro calendar)
 ├── Market Regime Engine
 ├── Crowding / Participation Index (proxies only; no fake AI-% claims)
 ├── Opportunity Scanner
 ├── Quantitative Scoring Engine (documented weights)
 ├── Options Analysis Engine
 ├── Risk Management Engine (hard stops)
 ├── Adversarial AI Role (structured critique)
 ├── Backtester + Walk-Forward
 ├── Strategy Health / Decay Monitor
 ├── Trade Journal
 └── Approval + Execution Gateway
 ↓
Adapters: Webull OpenAPI | Webull Local MCP | TradingView Webhooks
 ↓
USER APPROVAL  →  Webull order (sandbox/paper first)
```

---

## G. Phased development plan

| Phase | Deliverable | Exit criteria |
|-------|-------------|---------------|
| **1** | This audit | Confirmed by you |
| **2** | Market-data layer (provider-agnostic) + Webull adapter (read) | Can pull OHLCV/snapshots in sandbox; tests pass |
| **3** | Market Regime Engine | Deterministic regime label + confidence + evidence JSON |
| **4** | Opportunity Scanner (liquid large-caps/ETFs) | Ranked candidates with audit trail |
| **5** | Quantitative scoring (weighted, documented) | Scores reproducible from same inputs |
| **6** | Options engine (30–60 DTE, liquidity filters) | Contract selection report with Greeks/IV/spread checks |
| **7** | Backtester (costs, slippage, OOS, walk-forward) | At least 1–2 setups validated without look-ahead |
| **8** | Adversarial AI + decision packages | Every proposal has counter-thesis + reject rules |
| **9** | Paper trading mode + journal | Full loop without broker risk |
| **10** | Dashboard + alerts + daily/weekly reports | You can operate visually + via Grok chat |
| **11** | Webull execution adapter (sandbox) | Preview/place/cancel in sandbox only |
| **12** | `LIVE_APPROVAL` behind explicit command + kill switch | **Requires your written confirmation** |

**Rule:** Do not skip to live execution. Do not proceed past a critical failure without resolving it.

---

## H. External accounts / APIs / services you need

### Required to start research (Phases 2–7)

1. **Webull US account** with options trading permission (when you eventually trade)
2. **Webull OpenAPI** App Key + App Secret — [Open API Management](https://www.webull.com/center#openApiManagement)
3. **Webull OpenAPI Advanced Quotes** subscription (market data for API)
4. Hosting for the app (local first is fine; later a small VPS)

### Required for Grok daily oversight

5. **Grok** (xAI) with ability to connect **Webull Cloud MCP** (`https://api.webull.com/mcp`) for read-only account/market context
6. Access to our system’s daily report (API, shared folder, or chat export)

### Optional but valuable

7. **TradingView** paid plan (Essential/Pro+) for charts + webhook alerts  
8. **OpenAI API** access if using GPT-6 Astra as orchestrator  
9. Supplemental data (only if Webull gaps block a feature): e.g. FRED (macro, free), official SEC EDGAR (filings; Webull Cloud MCP already exposes some filings/earnings tools)  
10. Secret store (env files locally; later Doppler/1Password/AWS SM)

### Explicitly not required / not used

- Discord signal servers  
- Unofficial TradingView scrapers  
- Unofficial reverse-engineered Webull mobile APIs  

---

## I. Estimated ongoing monthly costs (order-of-magnitude)

| Item | Est. monthly | Notes |
|------|--------------|-------|
| Webull OpenAPI Advanced Quotes | **TBD — check Webull quote center** | Required for serious scanning; do not guess exact tier price |
| TradingView Essential/Pro+ | ~$15–$60 | Charts + webhooks |
| VPS (optional) | ~$5–$20 | If not running locally |
| OpenAI Astra / strong model usage | Highly variable | Public reporting cited ~$10/$50 per M tokens for Astra — research-heavy use can dominate cost |
| Grok subscription | Per xAI plan | Oversight chat |
| Supplemental data | $0–$100+ | Only if needed |
| Trading capital | $1,000 | Not a “cost”; at-risk principal |

**Practical note for $1,000:** One liquid option contract often risks more premium than a 3–5% account risk budget ($30–$50). System should prefer **cheap liquid contracts**, **defined-risk structures**, or **shares/ETFs** when options sizing is impossible under risk caps.

---

## J. Security and regulatory risks

| Risk | Mitigation |
|------|------------|
| API key leak | Env/secrets only; rotate; never commit |
| LLM places trades from chat ambiguity | Explicit `APPROVE TRADE` only; default RESEARCH/PAPER |
| Cloud MCP over-permission | Authorize least privilege; prefer read-only for Grok |
| Local MCP write access | Whitelists, max notional, preview-before-send, audit log |
| Pattern day trader / options approval | Respect broker rules; system does not bypass Webull permissions |
| System is **not** a registered adviser | Software/tooling for your own account; not advice to others |
| Wash sales / tax | Journaling only; you own tax compliance |
| Overfitting / false confidence | Walk-forward, OOS, decay monitor; no auto-live-rule changes from one week |
| Webhook spoofing (TradingView) | Shared secret, IP allowlist (TradingView published IPs), idempotency |

---

## K. What cannot currently be automated (honest limits)

1. **Guaranteed profitability** — impossible to automate.  
2. **True “% of volume from AI traders”** — no reliable public series; crowding index uses **proxies only**.  
3. **TradingView as primary market-data feed** — not officially available to retail programmatically.  
4. **Option market orders on Webull OpenAPI** — not supported; use limits/stops.  
5. **Using mobile/desktop quote entitlements for OpenAPI** — separate subscription required.  
6. **Unrestricted autonomous live trading** — product requirement forbids it.  
7. **Perfect IV rank/percentile for all names** — only if data provider supplies it; otherwise compute from available history or mark unavailable.  
8. **This environment’s broken `webull-uat` MCP** — until connection is fixed, cannot live-test MCP tools here.  
9. **“Looks good” chat as approval** — never.

---

## L. Confirmation gates (required from you)

Before any code that can place **live** orders, confirm:

1. Proceed with **Phase 2** (market data + project scaffold), replacing Discord-bot direction?  
2. Confirm you will obtain **Webull OpenAPI keys** + **OpenAPI Advanced Quotes**.  
3. Confirm default modes: `RESEARCH` → `PAPER` → only later `LIVE_APPROVAL`.  
4. Confirm Grok’s Webull access should be **read-only Cloud MCP** for oversight.  
5. Explicit later confirmation before enabling `LIVE_APPROVAL`.

---

## Scoring weight system (preview — to be validated in Phase 5)

Not a flat average. Initial proposal for documentation/tests (subject to change after backtests):

| Factor | Weight | Rationale |
|--------|--------|-----------|
| Market regime fit | 0.18 | Strategy only if regime allows |
| Liquidity | 0.15 | Hard filter for $1k account |
| Risk/reward | 0.15 | Survival over frequency |
| Options quality | 0.12 | Contract must stand alone |
| Momentum / structure | 0.10 | Setup quality |
| Technical | 0.08 | Supporting evidence |
| Catalyst | 0.08 | Timing |
| Crowding risk | 0.07 | Invert: high crowding lowers score |
| Fundamental | 0.07 | Swing context |

**Hard rejects (score irrelevant):** failed liquidity, risk-limit breach, regime blacklist, adversarial major flaw, missing stop/invalidation.

---

## Grok bot operating model (target)

Daily chat with Grok should consume:

1. System-generated **pre-market / EOD reports** (JSON + markdown)  
2. Optional **Webull Cloud MCP** for live balances/positions  
3. Commands mapped to our API: `Analyze the market`, `Show best 3 trades`, `Why shouldn’t I take this?`, `Approve trade #1` (approval only if mode allows and all gates pass)

Grok is the **oversight + conversation layer**, not the unsupervised execution brain.

---

## Next action

Await your confirmation on section **L**. On approval of Phase 2 only, scaffold the new system (no live order placement).
