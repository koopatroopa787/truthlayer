# TruthLayer — Composable Research & Verification Agents on CAP

> 5 AI agents wired to the CROO Agent Protocol. They accept on-chain orders, do real work, and settle in USDC on Base L2 — no humans required.

## What's Inside

| Agent | Service | Price | SLA |
|---|---|---|---|
| `research_report` | Deep web research with cited sources | $2.00 USDC | 30 min |
| `fact_check` | Claim verification with confidence score | $0.50 USDC | 5 min |
| `marketplace_monitor` | Alert when agents matching your criteria go online | $0.30 USDC | Async |
| `agent_trust_score` | Reputation scoring for any CROO agent | $0.25 USDC | 5 min |
| `cross_agent_arbitrage` | Best-value agent finder across the marketplace | $0.15 USDC | 2 min |

## A2A Composability

The `orchestrated_research` service hires **Argus** and **Themis** as sub-agents via CAP, pays them USDC, collects their outputs, and synthesizes a unified report — all within one order flow. TruthLayer is simultaneously a CAP provider and a CAP requester.

`agent_scout` scans the live CROO marketplace and recommends which agents to hire, so any caller can use TruthLayer as an intelligent hiring layer.

## Architecture

```
truthlayer/
├── main.py              # 5-provider async loop via asyncio.gather
├── workers/
│   ├── research.py      # Tavily search → GPT-4o-mini synthesis → citations
│   ├── verify.py        # Claim → evidence search → verdict + confidence
│   ├── agent_scout.py   # Marketplace scan → GPT ranking → hire recommendations
│   ├── orchestrate.py   # Hires sub-agents (Argus + Themis) → synthesizes
│   ├── trust_score.py   # Agent profile → GPT trust grade A–F
│   ├── arbitrage.py     # Marketplace filter → best-value recommendations
│   ├── monitor.py       # Async poll → deferred delivery when agents appear
│   └── discovery.py     # Cached marketplace fetcher (600s TTL)
├── Dockerfile
├── railway.toml         # Deploy to Railway with restartPolicyType = "always"
├── keep_alive.ps1       # Local fallback: auto-restart on crash
└── requirements.txt
```

## CAP Integration

**Full 4-phase order lifecycle:**
```
order_negotiation_created → accept_negotiation
order_created             → store (service_id + requirements)
order_paid                → dispatch to worker → deliver_order
order_completed           → USDC released from CAPVault
```

**SDK methods used:**
- `AgentClient(config, sdk_key)` — one client per agent
- `client.connect_websocket()` → `EventStream`
- `stream.on(EventType.*, handler)`
- `client.get_negotiation(id)` / `client.accept_negotiation(id)`
- `client.deliver_order(id, DeliverOrderRequest(deliverable_type, deliverable_schema))`
- `client.list_negotiations()` / `client.list_orders(ListOptions(role="buyer"))`
- `client.create_negotiation()` / `client.pay_order()` — requester side (orchestrate)

## Setup

```bash
git clone https://github.com/<you>/truthlayer
cd truthlayer

python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac

pip install -r requirements.txt

cp .env.example .env
# fill in your keys
python main.py
```

## Environment Variables

```bash
# .env
CROO_API_URL=https://api.croo.network
CROO_WS_URL=wss://api.croo.network

# One SDK key per agent (from agent.croo.network)
SERVICE_RESEARCH_ID=croo_sk_...
SERVICE_VERIFY_ID=croo_sk_...
MONITOR_SVC_ID=croo_sk_...
TRUST_SVC_ID=croo_sk_...
ARBITRAGE_SVC_ID=croo_sk_...

# Service UUIDs (from agent.croo.network → your agent → Services)
RESEARCH_SVC_ID=
SCOUT_SVC_ID=
ORCHESTRATE_SVC_ID=
VERIFY_SVC_ID=

OPENAI_API_KEY=sk-...
TAVILY_API_KEY=tvly-...
```

## Deploy (Railway — always online)

```bash
railway login
railway init
railway variables set CROO_API_URL=https://api.croo.network ...  # set all vars
railway up
```

`railway.toml` sets `restartPolicyType = "always"` so all 5 agents stay online 24/7.

## Tech Stack

- Python 3.11 · `croo-sdk==0.2.1`
- OpenAI `gpt-4o-mini`
- Tavily web search
- Base L2 · USDC payments via CAPVault

## License

MIT
