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

---

## WP-D: FEATURES AND CANDLES

### Status
**DONE** (All WP-D requirements verified and tested with 100/100 passing tests across monorepo)

### What Was Done
1. **NSE-Aligned Candle Resampler (`services/engine/data_feed/resampler.py`)**:
   - Resamples granular 1m candles into 5m, 10m, and 15m timeframes strictly aligned to the National Stock Exchange (NSE) 09:15:00 IST open.
   - Handles the 15:30:00 IST session close cleanly (e.g. final 10m bucket 15:25–15:30 closes at market termination).
   - **Zero Partial-Candle Leakage**: Incomplete buckets (e.g. 3 out of 5 minutes elapsed) are strictly excluded in `complete_only=True` mode, preventing lookahead bias.
   - **Gaps and Multi-Day Holidays**: Grouping by IST trading calendar date ensures weekend, holiday, and overnight boundaries are never bridged into the same candle.
   - **Event-Driven Streaming Resampler (`StreamingCandleResampler`)**: Real-time tick/candle processing that emits higher-timeframe bars the exact moment their bucket window elapses without lookahead.
2. **Unified Institutional Feature Store (`services/engine/features/store.py`)**:
   - Rule 5 compliant: ONE shared feature store used identically across backtest, paper, and live.
   - Computes all 12 institutional market features:
     - `ema_9` and `ema_21`
     - Wilder-smoothed `rsi` (14)
     - Wilder-smoothed `atr` (14)
     - `adx` (14) with `plus_di` and `minus_di`
     - `supertrend` (period 7, multiplier 3.0) and trend `supertrend_direction` (+1 / -1)
     - `vwap` with strict daily reset at 09:15 IST open
     - `vol_ratio` (relative to 20-period volume SMA)
     - `opening_range_high` and `opening_range_low` (computed over session opening window; returns `None` before window closes, then freezes for the trading day)
     - `spread_points` and `spread_pct`
     - `time_of_day_minutes` (elapsed minutes since 09:15 IST open)
     - `gap_points` and `gap_pct` (today's 09:15 open vs yesterday's 15:30 close)
     - `daily_open` (today's opening price)
   - Strongly-typed `MarketFeatures` Pydantic model for clean, type-checked feature access.
3. **Fixed Backtester Multi-Timeframe Delivery (`services/backtester/engine.py`)**:
   - Removed ad-hoc opening range logic (`candles[:3]`) that previously existed only in the backtester.
   - Integrated `CandleResampler` to deliver distinct, real 1m, 5m, 10m, and 15m candle series to `StrategyContext`, not the same 1m list repeated three times.
   - Enforced zero lookahead bias during iteration: only higher timeframe bars that have completed prior to or at `current_bar.timestamp` are visible to strategies.
   - Added symmetric Long (BUY) and Short (SELL) position execution and statutory cost calculation.
4. **Automated Evidence**:
   - `services/engine/tests/test_resampler.py`: 6 tests verifying alignment, OHLCV+VWAP math, partial leakage prevention, streaming zero-lookahead, holiday separation, and 15:30 close.
   - `services/engine/tests/test_feature_store.py`: 4 tests verifying presence of all 12 features, opening range freeze without leakage, overnight gap math, and typed model.
   - `tests/test_scalpers_and_backtester.py`: added tests proving distinct multi-timeframe series delivery with zero lookahead, and running `Scalper10MORB` with feature store opening range.
   - Full test suite: **100/100 passed in 5.56s**.
   - Ruff lint: **All checks passed with 0 errors**.

### Not Done / Next Package
- Regime detection filter, symmetric short signals in scalpers, NO_MODEL quality interface, shared session risk manager, and expected net gain cost filter (scheduled for WP-E).

### Known Limitations
- If a stock is completely halted intraday for multiple consecutive time buckets, resampled bars are only emitted for periods containing trading volume; no synthetic price interpolation is fabricated.

---

## WP-E: STRATEGIES AND REGIME

### Status
**DONE** (All WP-E requirements verified and tested with 120/120 passing tests across monorepo)

### What Was Done
1. **RegimeDetector with Institutional Indicators (`services/engine/regime/classifier.py`)**:
   - Classifies market into `TRENDING_BULLISH`, `TRENDING_BEARISH`, `RANGE_BOUND`, and `VOLATILE_CHAOTIC`.
   - Incorporates ADX (14) with +DI/-DI for directional conviction (ADX >= 20 threshold).
   - Wilder ATR and overnight gap size thresholds (ATR% > 2.5% or Gap% > 3.0% trigger `VOLATILE_CHAOTIC`).
   - Benchmark index agreement: if stock trend conflicts with the broader index direction, regime is downgraded to `RANGE_BOUND` to prevent trading against the market tide.
   - All strategies query `RegimeDetector` first and return `None` in disallowed regimes (`RANGE_BOUND`, `VOLATILE_CHAOTIC`).
2. **Symmetric SHORT Signals Across All Scalpers and ORB**:
   - `Scalper1M`: Bearish VWAP pullback (tested VWAP from below and closed below with volume) in `TRENDING_BEARISH` regime with stop above entry and target below entry.
   - `Scalper5M`: Bearish EMA 9 crossing below EMA 21 below VWAP in `TRENDING_BEARISH` regime with 15m trend agreement.
   - `Scalper10MORB`: Bearish breakdown below opening range low with volume expansion and below VWAP in `TRENDING_BEARISH` regime.
3. **Higher-Timeframe Trend Filters & Index Agreement**:
   - `Scalper1M`: 5m trend filter (`candle_history_5m`) ensuring EMA9/21 and VWAP agreement.
   - `Scalper5M`: 15m trend filter (`candle_history_15m`) ensuring higher-timeframe trend alignment.
   - `Scalper10MORB`: Index-direction agreement filter ensuring trade direction aligns with index bias.
4. **Removed Hardcoded Quality Scores & Built QualityModel Interface (`services/engine/models/quality_model.py`)**:
   - Removed fake scores (`0.74`, `0.79`, `0.82`).
   - Built `QualityModel` abstract interface.
   - `NoModelPassThrough`: default model that reports `quality_score = None`, never a fabricated probability.
5. **Unified SessionManager Enforced by Risk Guard (`services/risk_guard/session_manager.py`)**:
   - All session and intraday risk rules consolidated into ONE place:
     - No-entry opening window before 09:20:00 IST.
     - No entries after 15:00:00 IST.
     - Strict 15:15:00 IST square-off window blocking new entries.
     - Automatic square-off order generator (`generate_square_off_orders`) creating market exit orders to flatten Long and Short positions.
     - Daily trade cap ceiling.
     - 3-consecutive-loss pause (pauses trading for the session, resets on winning trade).
   - Wired directly into `RiskGuard.validate_proposal`, `record_trade_execution`, and `record_trade_completion`.
6. **Mandatory Pre-Signal Cost Check**:
   - Every strategy evaluates expected net profit via `IndianCostCalculator` modeling brokerage, STT, exchange charges, GST, stamp duty, SEBI fees, and slippage.
   - Rejects any signal where net expected profit is <= 0.
7. **Automated Evidence**:
   - `services/engine/tests/test_regime_detector.py`: 6 tests verifying all 4 regimes, index conflict downgrading, and strategy suppression.
   - `services/engine/tests/test_strategies_wp_e.py`: 6 tests verifying symmetric short signals, trend filters, index agreement, QualityModel interface, and cost checks.
   - `services/risk_guard/tests/test_session_manager.py`: 8 tests verifying no-entry windows, 15:15 square-off, flattening order generation, daily trade cap, and 3 consecutive losses.
   - Full test suite: **120/120 passed in 7.40s**.
   - Ruff lint: **All checks passed with 0 errors**.

---

## WP-F: BACKTESTER

### Status
**DONE** (All WP-F requirements verified and tested with 128/128 passing tests across monorepo)

### What Was Done
1. **DataProvider Interface & Loaders (`services/backtester/data_providers/`)**:
   - `DataProvider` base interface with `load_data(symbol, start_date, end_date, timeframe)` and validation for ascending chronological order and schema conformance.
   - `CSVDataProvider`: loads historical NSE minute/daily bar data from standardized CSV files.
   - `ParquetDataProvider`: loads high-performance column-oriented parquet historical data.
   - `BrokerHistoricalDataProvider`: queries official broker historical candle APIs when valid credentials and active session tokens are supplied; strictly refuses execution and prompts for credentials if missing.
   - Real data is the default; synthetic candle generation is strictly isolated inside unit-test fixtures (`tests/fixtures/synthetic_data.py`).
2. **Real Data Specification (`data/historical/README.md`)**:
   - Complete documentation of required format (ISO-8601 with `+05:30` IST timezone, Open/High/Low/Close/Volume/VWAP), naming conventions, and instructions for procuring genuine NSE minute historical data.
3. **Execution & Cost Alignment with Live Engine**:
   - Runs the EXACT same strategy classes (`Scalper1M`, `Scalper5M`, `Scalper10MORB`) as live and paper trading without separate logic.
   - Models full Indian statutory costs and slippage via `IndianCostCalculator` on every round-trip trade (brokerage, STT, exchange turnover fees, GST, stamp duty, SEBI turnover fees, slippage).
   - Supports symmetric short setups with protective stops and targets.
   - Enforces session rules in backtest: daily trade cap, 3-consecutive-loss pause, no-entry before 09:20 IST, no-entry after 15:00 IST, and mandatory 15:15 IST intraday square-off.
4. **Institutional Reporting Engine (`services/backtester/reports.py`)**:
   - Net P&L after statutory costs and slippage.
   - Max Drawdown (INR and %).
   - Win Rate %, Profit Factor, Payoff Ratio.
   - Average Win (INR) and Average Loss (INR).
   - Monthly breakdown strictly reporting every month, including losing months (`losing_trades`, `gross_pnl`, `total_costs`, `net_pnl`, `win_rate_pct`).
   - Institutional `OVERFITTING WARNING` triggered when:
     - Win rate exceeds 85% on significant sample (>= 20 trades).
     - Profit factor exceeds 5.0 on significant sample.
     - Zero losing months across 3+ active months with >= 30 trades.
5. **Walk-Forward Validation Engine (`services/backtester/walk_forward.py`)**:
   - Sequential train/test out-of-sample window validation (rolling or anchored).
   - Prevents lookahead bias and reports out-of-sample degradation and consistency metrics across folds.
6. **Automated Evidence**:
   - `services/backtester/tests/test_backtester_wp_f.py`: 8 tests covering CSV provider, Parquet provider, broker credential refusal, 15:15 square-off, daily trade cap, monthly breakdown including losing months, overfitting warnings, and walk-forward validation splits.
   - Full test suite: **128/128 passed in 4.56s**.
   - Ruff lint: **All checks passed with 0 errors**.

### Not Done / Next Package
- Real Kite Connect SDK broker adapter using encrypted tokens from vault, real funds/profile fetch, and contract tests (scheduled for WP-G).

### Known Limitations
- When using `BrokerHistoricalDataProvider`, rate limits (KiteConnect historical API limits of 3 req/sec) must be respected by callers during large batch backtests.
- Walk-forward splits require at least 20 bars per fold for meaningful feature computation.

---

## FIX-1 TO FIX-4: ARCHITECTURAL HARDENING & TRADING LOOP

### Status
**DONE** (All fixes verified and tested with 133/133 passing tests across monorepo)

### What Was Done
1. **FIX-1 (PyArrow Dependency)**:
   - Added `pyarrow>=15.0.0` to `pyproject.toml` dependencies.
   - Clean environment install verified with parquet data provider integration.

2. **FIX-2 (Wire Persistence & Remove In-Memory Stores)**:
   - Eliminated all in-memory dictionaries (`USERS_DB`, `USER_RISK_SETTINGS_STORE`, `BROKER_CONNECTIONS`) from API routers.
   - Wired auth (`services/api/app/auth/router.py`), broker connections (`services/api/app/brokers/router.py`), and risk settings (`services/api/app/risk/router.py`) directly to SQLAlchemy repositories (`UserRepository`, `RiskRepository`, `OrderRepository`, `AuditRepository`) and database sessions (`AsyncSession = Depends(get_db_session)`).
   - Moved rate limiting, lockouts, kill switch state, and idempotency tracking to Redis (`services/api/app/core/redis.py`).
   - Added `test_persistence_wiring_fix2.py`:
     - AST static analysis verifying zero route references to in-memory stores.
     - Process restart / engine disposal test proving users, broker connections, risk settings, and kill-switch state survive restarts.

3. **FIX-3 (RiskGuard Signing Secret Fail-Closed)**:
   - `RiskGuard` (`services/risk_guard/guard.py`) strictly enforces fail-closed signing secret configuration.
   - Outside of pytest test environments, missing or default secret keys immediately raise `RuntimeError` and halt approval signing.

4. **FIX-4 (Autonomous Trading Loop Runner & Paper Broker Slippage)**:
   - Configurable slippage (`slippage_bps=2.0`) and spread (`spread_bps=1.0`) added to `PaperBroker` (`services/execution/gateway/paper_broker.py`), applying realistic Ask on BUY and Bid on SELL.
   - Built `MarketDataProvider` abstract interface and `HistoricalReplayProvider` (`services/engine/runner.py`) for sequential, zero-lookahead candle streaming.
   - Built `TradingLoopRunner` (`services/engine/runner.py`) linking:
     `Provider -> FeedWatchdog -> FeatureStore -> Strategies -> RiskGuard -> OrderManager -> Gateway -> Database Repositories`.
   - Manages active positions, protective stop-loss triggers, profit targets, and 15:15 IST intraday session square-off cutoff.
   - Calculates statutory Indian round-trip taxes/costs via `IndianCostCalculator`.
   - Persists execution state to DB tables: `orders`, `fills`, `positions`, `trades`, and append-only `audit_logs`.
   - Added `tests/test_trading_loop_fix4.py`:
     - Replays a full 375-minute NSE session (09:15 to 15:30 IST).
     - Confirms strategy trigger, order placement with protective stop, target exit, cost modeling, and database persistence.
   - Preserved architectural boundary: gateways remain strictly encapsulated behind `OrderManager` (`test_gateway_access_boundary.py` passes).

### Automated Evidence
- Full test suite: **133/133 passed in 28.99s**.
- Ruff lint: **All checks passed with 0 errors**.
