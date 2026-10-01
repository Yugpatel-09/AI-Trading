# TradeForge Failure Drills & Integration Tests (`tests/`)

System-level disaster recovery and fail-safe validation:
- `failure_drills/`:
  - `test_dead_market_feed.py`: Validates trading halts immediately if candle ticks stop arriving for > 5 seconds.
  - `test_broker_down.py`: Ensures orders transition to fail-safe state with exponential backoff and operator alert.
  - `test_duplicate_orders.py`: Proves idempotency tokens prevent duplicate order execution.
  - `test_server_crash_recovery.py`: Validates order state reconciliation upon process reboot.
