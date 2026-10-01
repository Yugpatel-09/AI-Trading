# ADR 0001: Monorepo Architecture and Standalone Risk Guard

## Status
Accepted

## Context
TradeForge is an AI-assisted intraday trading platform designed for Indian National Stock Exchange (NSE) markets. Algorithms interact directly with financial capital. Errors such as infinite loops, bad sizing, duplicate submissions, or lack of protective stops can cause catastrophic financial losses.

Furthermore, discrepancies between backtesting logic and live execution logic are the single biggest cause of algorithmic trading strategy failures.

## Decision
1. **Monorepo Structure**: Keep the frontend (`apps/web`), API (`services/api`), AI Engine (`services/engine`), Execution (`services/execution`), Risk Guard (`services/risk_guard`), and shared contracts (`packages/shared`) in a single monorepo. This guarantees atomic updates to schemas, contracts, and formulas.
2. **Standalone Risk Guard**: Isolate risk verification into an autonomous component (`services/risk_guard`). No order may reach any broker adapter without passing through this gate.
3. **Unified Strategy Engine**: The strategy implementation (`on_candle(context)`) and transaction cost calculator (`IndianCostCalculator`) are shared directly between the backtester and live execution engine.
4. **Paper Trading Default**: All new user registrations and newly assigned strategies default strictly to simulated execution with real-time live prices. Live trading requires explicit 2FA opt-in and strict risk limit confirmation.

## Consequences
- Single version control source ensures zero schema drift between Python services and Next.js frontend.
- Pre-trade risk controls cannot be bypassed by bugs in strategy code.
- Realistic transaction fees (brokerage, STT, turnover charges, GST, stamp duty, SEBI fees, slippage) prevent overfitting to unprofitable scalping frequencies.
