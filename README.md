# TradeForge (NSE AI Intraday Trading Platform)

![TradeForge](https://img.shields.io/badge/Platform-TradeForge-0D9488?style=flat-square)
![License](https://img.shields.io/badge/License-Proprietary-navy?style=flat-square)
![Market](https://img.shields.io/badge/Exchange-NSE%20India-blue?style=flat-square)
![Architecture](https://img.shields.io/badge/Architecture-8--Layer%20Microservices-0a6e5c?style=flat-square)

> **Important Regulatory & Risk Notice**: TradeForge is an educational and execution-disciplining technological blueprint. No algorithm or AI model can guarantee profit. Trading intraday equities and derivatives on the National Stock Exchange of India (NSE) carries significant capital risk. TradeForge enforces strict stop-losses, daily risk limits, and paper-trading verification to protect capital from emotional mistakes and catastrophic loss.

---

## 🏛️ Platform Architecture (8 Floors)

```text
[1] EXPERIENCE   ── Next.js 14 (App Router) + TradingView Lightweight Charts + Tailwind CSS
[2] GATEWAY      ── FastAPI + Argon2 Password Hash + Mandatory TOTP 2FA + Rate Limiting
[3] PRODUCT      ── Charting, Backtesting Engine, Strategy Marketplace, Tax Reports
[4] INTELLIGENCE ── Feature Engineering, Regime Classifier (Trending/Chop/Wild), Signal Models
[5] RISK GUARD   ── Standalone Pre-Trade Risk Verification, Kill Switch, Watchdog (Safety First)
[6] EXECUTION    ── BrokerGateway (PaperBroker, Zerodha Kite Connect, Upstox, Angel One)
[7] DATA         ── 1m/5m/10m Real-time Candles, TimescaleDB, Redis Streams, Model Registry
[8] PLATFORM     ── Docker Compose, Kubernetes, Prometheus Metrics, Grafana Audits
```

---

## 📁 Monorepo Structure

```text
tradeforge/
├── apps/
│   └── web/                   # Next.js web application (Landing, Dashboard, Charts, Risk Settings)
├── services/
│   ├── api/                   # Public FastAPI backend (Auth, Broker Connect, WebSocket feeds)
│   ├── engine/                # Core AI Engine (Data feed, Features, Regime Detection, Scalpers)
│   ├── risk_guard/            # Standalone Risk Guard (Rules, Limits, Kill Switch, Watchdog)
│   ├── execution/             # Order routing, BrokerGateway interface, PaperBroker adapter
│   ├── backtester/            # Historical backtester sharing exact strategy and cost code
│   └── workers/               # Celery / Redis background workers
├── packages/
│   └── shared/                # Universal contracts (Python Pydantic schemas, Enums, TS types)
├── ml/                        # Walk-forward model training, registry, drift monitoring
├── infra/                     # Dockerfiles, compose, terraform, Prometheus & Grafana configs
├── scripts/                   # Market data seeders, health monitors, failure drills
├── tests/                     # Failure drill suites (dead feed, broker outage, duplicate orders)
└── docs/                      # Architectural Decision Records (ADRs), Compliance, Runbooks
```

---

## ⚡ Non-Negotiable Operational Principles

1. **Safety before features**: Every single order must pass through `RiskGuard`. There is no direct code path from strategy to broker.
2. **Paper mode by default**: All new users and strategies start in simulated paper mode. Live trading requires explicit activation with 2FA.
3. **Identical logic across backtest and live**: The exact same `on_candle(context)` strategy code executes in the backtester, paper mode, and live execution.
4. **Mandatory Cost Accounting**: Brokerage (flat ₹20/order or 0.03%), STT (0.025% on sell), NSE Exchange turnover fees (0.00345%), GST (18%), Stamp duty (0.003% on buy), SEBI fees (₹10/crore), and realistic slippage are deducted from every projected setup.
5. **Protective Stops sent with Entry**: An entry order is never dispatched without its protective bracket stop-loss.
6. **No Fake Profit Claims**: Marketing copy and UI adhere to SEBI transparency principles: honest win-rate, net-after-costs, and max drawdown reporting.

---

## 🚀 Quickstart Development

```bash
# 1. Copy environment variables
cp .env.example .env

# 2. Start database and cache dependencies
make docker-up

# 3. Run test suite
make test

# 4. Run linters
make lint
```
