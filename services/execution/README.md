# TradeForge Execution Layer (`services/execution`)

Responsible for order lifecycle management, broker routing, fill tracking, and nightly statement reconciliation.

## Components
- `gateway/base.py`: Abstract `BrokerGateway` contract.
- `gateway/paper_broker.py`: High-fidelity simulated execution broker with slippage modeling and order latency emulation.
- `gateway/zerodha_adapter.py`: Zerodha Kite Connect v3 adapter.
- `order_manager/`: Idempotency tracking, exponential backoff retries, partial fill handlers, and child order (bracket stop-loss) tracking.
- `reconciliation/`: Nightly ledger auditing comparing internal order state with broker tradebooks.
