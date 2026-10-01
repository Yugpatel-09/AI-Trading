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
