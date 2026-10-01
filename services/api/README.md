# TradeForge Public API Gateway (`services/api`)

FastAPI microservice exposing REST and WebSocket endpoints for frontend clients, user management, broker connections, and trade auditing.

## Key Modules
- `app/core/`: Configuration, Pydantic settings, rate limiting, and password/token redacting loggers.
- `app/auth/`: Argon2 password hashing, TOTP 2FA verification, JWT tokens, session lifecycle.
- `app/brokers/`: Broker credential encryption (AES-256-GCM), connection validation, daily token expiry reminders.
- `app/ws/`: Real-time WebSocket multiplexer for candle broadcasts, order status updates, and AI signals.
- `app/db/`: SQLAlchemy 2 async models and Alembic migrations.
