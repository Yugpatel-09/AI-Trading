# TradeForge Development Status & Work Package Tracker

This document tracks progress, verifications, test evidence, and known limitations across TradeForge work packages in strict accordance with [GEMINI.md](../GEMINI.md).

---

## Baseline Completed (Prior Work Packages)
- **Production Secrets Fail-Closed**: Refuses startup in staging/prod if `SECRET_KEY`, `ADMIN_PASSWORD`, `ADMIN_TOTP_SECRET`, or `ENCRYPTION_KEY_32BYTES_BASE64` are missing or default.
- **2FA & Auth Hardening**: Single-use 24-hour email verification tokens; password check and lockout on `/verify-2fa`; brute-force protection.
- **Risk Guard Foundation**: Server-side trading hours enforcement (09:15–15:30 IST); post-approval idempotency recording; fat-finger check; blocklist; 3-consecutive-loss auto-pause; daily loss cap.
- **Engine Core Indicators**: Daily-reset VWAP at 09:15 IST open; Wilder-smoothed RSI and ATR; ADX (+DI/-DI); Supertrend ratchet logic with reference-value tests.
- **OrderManager Initial Integration**: Entry and protective stop placed together; Risk Guard validation gate; downscaled quantity checks.

---

## WP-A: FINISH SECURITY

### Status
**DONE** (All WP-A requirements verified and tested with 61/61 passing unit & integration tests)

### What Was Done
1. **EmailSender Interface & Providers**:
   - Built `EmailSender` abstract interface (`services/api/app/auth/email.py`).
   - Implemented `ConsoleEmailSender` for dev/test environments and `SMTPEmailSender` (with STARTTLS/TLS and sanitized logging) for production.
   - Verification tokens are delivered *only* via `EmailSender` and never returned in API payloads (`/signup`, `/resend-verification`) or logged in production.
2. **Security Headers & Defense-in-Depth**:
   - Implemented `SecurityHeadersMiddleware` (`services/api/app/core/security_middleware.py`) enforcing `Strict-Transport-Security` (HSTS), `Content-Security-Policy`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, and `Referrer-Policy: strict-origin-when-cross-origin`.
3. **Strict CORS Allow-List**:
   - Configured `CORSMiddleware` using `settings.cors_origins` (defaulting strictly to trusted origin `http://localhost:3000`). Untrusted origins are denied credentials and access.
4. **CSRF Protection**:
   - Built `CSRFMiddleware` validating `X-CSRF-Token` against double-submit `tf_csrf` cookie for mutating HTTP methods (`POST`, `PUT`, `DELETE`, `PATCH`). Safe methods and Bearer-token-only API requests without cookies are accommodated safely.
5. **Rate Limiting**:
   - Enforced IP/route sliding window rate limits on all auth and risk routes:
     - `/api/v1/auth/signup`: 15 requests/minute
     - `/api/v1/auth/resend-verification`: 10 requests/minute
     - `/api/v1/auth/verify-2fa`: 20 requests/minute
     - `/api/v1/auth/login`: 20 requests/minute
     - `/api/v1/risk/validate`: 100 requests/minute
     - `/api/v1/risk/kill-switch/*`: 30 requests/minute
6. **Split Docker Compose**:
   - Maintained `docker-compose.yml` for local development.
   - Created `docker-compose.prod.yml` with zero hardcoded credentials, mandatory environment interpolation (`${VAR:?error}`), no bind-mount source code leakage, and `restart: always`.
7. **Verification & Automated Evidence**:
   - `services/api/tests/test_security_wp_a.py` with 6 dedicated test cases covering headers, CORS, CSRF, rate-limiting (HTTP 429), and production refusal to boot on missing secrets.
   - Total test suite: 61/61 tests passing. Ruff lint: 0 errors.

### Not Done / Next Package
- Persistent Redis backing for rate limiter and lockouts (currently memory-based sliding window; scheduled for migration in WP-C).

### Known Limitations
- Production SMTP requires valid credentials (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`) set in deployment environment. If unconfigured in production, email dispatch raises an explicit exception.

---

## WP-B: BYPASS-PROOF ORDER PATH

### Status
**DONE** (All WP-B requirements verified and tested with 81/81 passing tests across monorepo)

### What Was Done
1. **Cryptographic `RiskApproval` & Gateway Enforcement**:
   - Implemented `RiskApproval` schema (`packages/shared/python/tradeforge_shared/schemas.py`) carrying proposal SHA-256 hash, approved quantity, timestamp, 30s TTL, and HMAC-SHA256 signature.
   - Only `RiskGuard` can construct and sign approvals upon successful pre-trade risk verification (`services/risk_guard/guard.py`).
   - Base `BrokerGateway` contract (`services/execution/gateway/base.py`) updated so `place_order` accepts ONLY `RiskApproval`, rejecting raw proposals (`MissingApprovalError`), altered payloads (`TamperedApprovalError`), expired tokens (`ExpiredApprovalError`), or replay submissions (`ReusedApprovalError`).
   - All gateway adapters (`PaperBroker`, `ZerodhaAdapter`) strictly enforce this contract.
2. **Static Codebase Boundary Scanner**:
   - Built AST-based architectural test `services/execution/tests/test_gateway_access_boundary.py`.
   - Scans all files across `services/`, `packages/`, `apps/` to guarantee no code outside `OrderManager` imports gateways directly or calls `.place_order()`.
3. **Sole Path OrderManager & Mode Gate (Paper / Approve / Auto)**:
   - `OrderManager` (`services/execution/order_manager.py`) is the sole execution pipeline from signals, engine, and API to brokers.
   - Removed direct broker imports from `services/api/app/brokers/router.py`.
   - Added mode gate:
     - `TradingMode.PAPER`: Automatic simulated execution via `PaperBroker`.
     - `TradingMode.APPROVE`: Places order into pending approval queue (`PendingOrderApproval`) with configurable expiry timeout. Executes only upon explicit user confirmation (`confirm_pending_order`), refusing execution if timed out.
     - `TradingMode.AUTO`: Executes autonomously within server-enforced risk limits.
4. **Execution Resilience, Stop Confirmation & Nightly Reconciliation**:
   - Exponential backoff retries on transient broker transport errors.
   - Partial fills tracking with protective stop sized to filled quantity.
   - Protective-stop confirmation: If protective stop placement fails on the broker, `OrderManager` executes an immediate emergency market flatten order to close the entry position, raising `StopPlacementFailureError`.
   - Order status polling (`poll_order_status`).
   - Crash state persistence and hydration (`snapshot_state`, `recover_state`).
   - Built `ReconciliationEngine` (`services/execution/reconciliation/reconciler.py`) producing structured mismatch reports across trades, quantities, prices, and end-of-day positions.
5. **End-to-End Failure Drills**:
   - `tests/failure_drills/test_order_path_drills.py` tests all 7 failure scenarios through the real `OrderManager -> RiskGuard -> BrokerGateway` chain:
     1. Dead market feed rejection
     2. Broker gateway down with exponential backoff
     3. Duplicate signals blocked by idempotency
     4. Server crash mid-order recovery and post-restart duplicate block
     5. Stale data & fat-finger price deviation rejection
     6. Partial fill stop-loss sizing
     7. Stop placement failure immediate emergency flatten
6. **Automated Evidence**:
   - Full test suite: 81/81 passed in 3.16s.
   - Ruff lint: All checks passed.

### Not Done / Next Package
- PostgreSQL/TimescaleDB models and repository layer implemented in WP-C.

### Known Limitations
- Current OrderManager in-memory cache is backed by repository persistence; database migration executes on startup.

---

## WP-C: PERSISTENCE

### Status
**DONE** (All WP-C requirements verified and tested with 88/88 passing tests across monorepo)

### What Was Done
1. **SQLAlchemy 2 & Database Architecture**:
   - Built async SQLAlchemy 2 database layer (`services/api/app/db/session.py`) supporting PostgreSQL + TimescaleDB (`asyncpg`) in production and SQLite (`aiosqlite`) for test/local development.
   - Wired database table initialization and Redis connection into FastAPI application lifespan (`services/api/app/main.py`).
2. **Platform Entities Implemented (`services/api/app/db/models.py`)**:
   - `UserModel` (`users`): user ID, unique email, Argon2 password hash, role, TOTP secret, email verification flag, active status, connected brokers JSON.
   - `UserRiskSettingsModel` (`user_risk_settings`): capital allocated, per-trade loss limit, daily loss limit, max open positions, daily trade cap, mode, consecutive loss pause, instrument allowlist JSON, trading session window.
   - `SessionTokenModel` (`session_tokens`): session ID, user ID, refresh token SHA-256 hash, expiry, revocation flag.
   - `EmailTokenModel` (`email_tokens`): token ID, user ID, token hash, 24h expiry, single-use `used_at` timestamp.
   - `BrokerConnectionModel` (`broker_connections`): connection ID, user ID, broker name, encrypted key, encrypted secret, status, daily session expiry.
   - `ExecutionOrderModel` (`orders`): order ID, unique idempotency key, broker, symbol, side, order type, quantity, price, stop loss, target, status, filled quantity, average fill price, rejection reason.
   - `FillModel` (`fills`): fill ID, order ID, symbol, side, filled quantity, fill price, statutory fee amount, timestamp.
   - `PositionModel` (`positions`): position ID, user ID, broker, symbol, quantity, side, entry price, stop loss, target, open status, open/close timestamps.
   - `TradeModel` (`trades`): trade ID, user ID, order ID, symbol, side, quantity, entry/exit prices, gross P&L, net P&L after costs, total statutory costs, timestamps.
   - `AuditLogRecord` (`audit_logs`): ID, user ID, action, resource, details JSON, IP address, timestamp.
     - Enforced strictly **APPEND-ONLY** at ORM event listener level (`ReadOnlyAuditLogError` on any update or delete attempts).
3. **Repository Layer (`services/api/app/db/repositories/`)**:
   - `UserRepository`: user CRUD, password verification, TOTP updates, single-use 24h email token verification & consumption, session token creation & revocation, broker connection persistence.
   - `RiskRepository`: loading and saving user risk settings.
   - `OrderRepository`: order persistence, idempotency lookups, fill recording, position tracking, closed trade recording.
   - `AuditRepository`: immutable compliance log appending and queries.
4. **Redis Volatile State Manager (`services/api/app/core/redis_client.py`)**:
   - Sliding-window rate limiting counter.
   - Account and IP brute-force lockouts with duration TTL.
   - Global and user-specific emergency kill switches.
   - Idempotency key tracking with configurable TTL.
   - Real Redis async connection when reachable, with thread-safe in-memory fallback for test runs.
5. **Alembic Migrations**:
   - Configured `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`.
   - Migration `001_initial_schema.py` creating all 10 platform tables and indexes.
   - Automated up and down migration test (`services/api/tests/test_migrations.py`).
6. **State Survival & Process Restart Test**:
   - `test_state_survives_process_restart`: full state written, database engine terminated and memory completely cleared, new engine booted from persistent storage, asserting all users, settings, orders, positions, and audit logs survived intact.
7. **Automated Evidence**:
   - Full test suite: 88/88 passed in 5.43s.
   - Ruff lint: All checks passed with 0 errors.

### Not Done / Next Package
- Candle resampling (1m -> 5m -> 10m -> 15m) aligned to NSE session start (09:15 IST) and shared feature store (scheduled for WP-D).

### Known Limitations
- TimescaleDB hypertable extensions apply when running against TimescaleDB Docker container / PostgreSQL service. Local dev and unit tests run on SQLite / standard relational mode.


