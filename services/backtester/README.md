# TradeForge Backtester (`services/backtester`)

High-precision historical simulation engine. 

## Golden Rule: Same Code for Backtest and Live
The backtester executes the exact same `on_candle(context)` method implemented in `services/engine/strategies/` without any modification or parallel logic.

## Real Indian Cost Simulation
Incorporates exact statutory rates:
- Brokerage: flat ₹20/order or 0.03%
- STT: 0.025% on sell side
- Exchange Turnover Fees: 0.00345%
- GST: 18% on (Brokerage + Exchange Fees)
- SEBI Charges: ₹10 per crore
- Stamp Duty: 0.003% on buy side
- Dynamic slippage based on bid-ask spread and order size
