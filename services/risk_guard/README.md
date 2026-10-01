# TradeForge Standalone Risk Guard (`services/risk_guard`)

The most critical and heavily tested service in TradeForge. **Safety before features.**

## Golden Rule
No order may ever be dispatched to a broker or simulated paper account without explicit validation and cryptographic signature from `RiskGuard`.

## Enforced Limits
1. **User-Configured Limits**:
   - Capital allocated to intraday trading.
   - Maximum loss per single trade (₹).
   - Maximum daily loss limit (₹) — trading halted immediately if breached.
   - Maximum open concurrent positions (e.g., 3).
   - Maximum trades per day.
   - Permitted trading window (e.g., 09:20 IST to 15:00 IST).
   - Mandatory pause after N consecutive losing trades (default: 3).

2. **Platform-Level Safeguards (Cannot be overridden)**:
   - Illiquid symbol blacklist and circuit band checks.
   - Fat-finger price validation (orders > 2% away from LTP rejected).
   - Mandatory bracket stop-loss verification (orders without stops are blocked).
   - Idempotency token check (duplicate order submissions prevented).
   - Auto square-off trigger at 15:15 IST.
   - Global emergency kill switch (flattens active positions and revokes order authority).
   - Watchdog: Halts trading if data feed latency exceeds 5,000ms.
