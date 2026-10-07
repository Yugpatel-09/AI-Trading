import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.auth.email import get_email_sender
from services.api.app.auth.security import security_service
from services.api.app.core.config import settings
from services.api.app.core.logging import logger
from services.api.app.core.redis_client import redis_manager
from services.api.app.db.models import UserModel
from services.api.app.db.repositories.user_repo import UserRepository
from services.api.app.db.session import get_db_session

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication & 2FA"])


def get_client_ip(request: Request) -> str:
    """Extract client IP respecting reverse proxy headers."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


async def seed_admin_user(session: AsyncSession) -> Optional[UserModel]:
    """Seed the platform administrator from environment configuration only."""
    if not settings.ADMIN_EMAIL:
        return None
    admin_email = settings.ADMIN_EMAIL.strip().lower()

    repo = UserRepository(session)
    existing = await repo.get_by_email(admin_email)
    if existing:
        return existing

    if not settings.ADMIN_PASSWORD or not settings.ADMIN_TOTP_SECRET:
        logger.info(
            "ADMIN_PASSWORD or ADMIN_TOTP_SECRET not provided in environment. Platform admin not seeded."
        )
        return None

    user = UserModel(
        id="usr_admin_platform",
        email=admin_email,
        password_hash=security_service.hash_password(settings.ADMIN_PASSWORD),
        role="ADMIN",
        totp_secret=settings.ADMIN_TOTP_SECRET,
        totp_enabled=True,
        email_verified=True,
        is_active=True,
        connected_brokers=["PAPER"],
    )
    session.add(user)
    await session.flush()
    logger.info(f"Platform admin seeded from environment: {admin_email}")
    return user


def seed_admin_user_sync() -> Optional[UserModel]:
    """Synchronous helper for testing and offline admin seeding."""
    import asyncio

    from services.api.app.db.session import AsyncSessionLocal, init_db

    async def _runner():
        await init_db()
        async with AsyncSessionLocal() as session:
            admin = await seed_admin_user(session)
            await session.commit()
            return admin

    try:
        asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, _runner()).result()
    except RuntimeError:
        return asyncio.run(_runner())


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, description="Strong password (min 8 chars)")
    consent_risk_disclosure: bool = Field(..., description="Must acknowledge SEBI risk warning")
    consent_terms: bool = Field(..., description="Must accept terms of service")
    consent_data_use: bool = Field(..., description="DPDP Act compliant data consent")


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    token: str = Field(..., description="Email verification token")


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class Verify2FARequest(BaseModel):
    email: EmailStr
    password: str = Field(..., description="Account password to verify identity")
    totp_token: str = Field(..., min_length=6, max_length=6, description="6-digit TOTP code")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    totp_token: Optional[str] = Field(None, min_length=6, max_length=6)


async def get_current_user(
    authorization: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_db_session),
) -> UserModel:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )
    token = authorization.split(" ")[1]
    payload = security_service.decode_access_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
        )
    email = payload["sub"].strip().lower()
    repo = UserRepository(session)
    user = await repo.get_by_email(email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user


async def _enforce_rate_limit_async(key: str, max_requests: int, window_seconds: int = 60):
    """Async rate limiter using Redis (with in-memory fallback)."""
    allowed = await redis_manager.check_rate_limit(key, max_requests, window_seconds)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: {max_requests} requests per {window_seconds}s.",
            headers={"Retry-After": str(window_seconds)},
        )


@router.post("/signup")
async def signup(
    payload: SignupRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
):
    """
    Register new account.
    Enforces SEBI risk disclosure consent, generates TOTP 2FA secret, and dispatches email verification.
    Security: Administrator privileges can NEVER be granted through public signup.
    Tokens are dispatched by email and NEVER returned in API responses.
    """
    await _enforce_rate_limit_async(f"auth:signup:{get_client_ip(request)}", max_requests=15, window_seconds=60)
    if not payload.consent_risk_disclosure or not payload.consent_terms or not payload.consent_data_use:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mandatory regulatory consents must be accepted.",
        )

    email_clean = payload.email.strip().lower()
    repo = UserRepository(session)
    existing = await repo.get_by_email(email_clean)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists.",
        )

    user_id = f"usr_{uuid.uuid4().hex[:12]}"
    pw_hash = security_service.hash_password(payload.password)
    totp_secret = security_service.generate_totp_secret()
    totp_uri = security_service.get_totp_uri(email_clean, totp_secret)
    verification_token = secrets.token_hex(16)

    # Security: is_admin is strictly False for any public signup
    user = UserModel(
        id=user_id,
        email=email_clean,
        password_hash=pw_hash,
        role="USER",
        totp_secret=totp_secret,
        totp_enabled=False,
        email_verified=False,
        is_active=True,
        connected_brokers=["PAPER"],
    )
    session.add(user)
    await session.flush()

    # Create email verification token in DB
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    await repo.create_email_token(user_id, verification_token, expires_at)

    get_email_sender().send_verification_email(email_clean, verification_token)

    return {
        "status": "success",
        "message": "User registered. Verification instructions sent to your email. Please verify within 24 hours.",
        "user_id": user_id,
        "email": email_clean,
        "totp_secret": totp_secret,
        "totp_uri": totp_uri,
    }


@router.post("/verify-email")
async def verify_email(
    payload: VerifyEmailRequest,
    session: AsyncSession = Depends(get_db_session),
):
    """
    Verify user's email address using registration token.
    Enforces a strict 24-hour expiration window.
    """
    email_clean = payload.email.strip().lower()
    repo = UserRepository(session)
    user = await repo.get_by_email(email_clean)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.email_verified:
        return {"status": "success", "message": "Email is already verified."}

    now = datetime.now(timezone.utc)
    user_id = await repo.verify_and_consume_email_token(payload.token.strip(), now)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired email verification token.",
        )

    logger.info(f"Email successfully verified for user: {email_clean}")

    return {
        "status": "success",
        "message": "Email successfully verified. You can now verify 2FA to activate session.",
        "email": email_clean,
        "is_email_verified": True,
    }


@router.post("/resend-verification")
async def resend_verification(
    payload: ResendVerificationRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
):
    """
    Regenerate and resend email verification token. Token is not returned in API response.
    """
    await _enforce_rate_limit_async(f"auth:resend:{get_client_ip(request)}", max_requests=10, window_seconds=60)
    email_clean = payload.email.strip().lower()
    repo = UserRepository(session)
    user = await repo.get_by_email(email_clean)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.email_verified:
        return {"status": "success", "message": "Email is already verified."}

    new_token = secrets.token_hex(16)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    await repo.create_email_token(user.id, new_token, expires_at)

    get_email_sender().send_verification_email(email_clean, new_token)

    return {
        "status": "success",
        "message": "Verification instructions resent to your email. Please verify within 24 hours.",
        "email": email_clean,
    }


@router.post("/verify-2fa")
async def verify_2fa(
    payload: Verify2FARequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
):
    """
    Verify 6-digit TOTP token to activate 2FA and receive authenticated JWT session.
    Security: Enforces account password check and brute-force lockout. Requires verified email.
    """
    await _enforce_rate_limit_async(f"auth:2fa:{get_client_ip(request)}", max_requests=20, window_seconds=60)
    email_clean = payload.email.strip().lower()

    # 1. Check lockout status (Redis-backed with memory fallback)
    is_locked = await redis_manager.is_locked_out(email_clean)
    if not is_locked:
        is_locked, _ = security_service.is_locked_out(email_clean)
    if is_locked:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Account temporarily locked due to multiple failed attempts. Try again later.",
        )

    repo = UserRepository(session)
    user = await repo.get_by_email(email_clean)
    if not user:
        await _record_failed_attempt_redis(email_clean)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # 2. Check email verified
    if not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email is not verified. Please verify your email before proceeding.",
        )

    # 3. Check password
    pw_matches = security_service.verify_password(user.password_hash, payload.password)
    if not pw_matches:
        count = await _record_failed_attempt_redis(email_clean)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid password. Attempt {count}/5 before lockout.",
        )

    # 4. Check TOTP token
    is_valid = security_service.verify_totp(user.totp_secret, payload.totp_token)
    if not is_valid:
        count = await _record_failed_attempt_redis(email_clean)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid 2FA code. Attempt {count}/5 before lockout.",
        )

    # Reset failed attempts on success
    await _reset_failed_attempts_redis(email_clean)

    # Mark 2FA as enabled in DB
    if not user.totp_enabled:
        await repo.update_totp(user.id, user.totp_secret, enabled=True)

    token = security_service.create_access_token(
        subject=user.email,
        extra_claims={"user_id": user.id, "mode": "PAPER"},
    )
    logger.info(f"User {email_clean} successfully verified 2FA.")

    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": user.id,
        "email": user.email,
        "is_2fa_enabled": True,
        "is_admin": user.role == "ADMIN",
        "is_email_verified": True,
        "trading_mode": "PAPER",
    }


@router.post("/login")
async def login(
    payload: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
):
    """
    Authenticate user using Argon2 password and mandatory TOTP 2FA.
    Enforces brute-force lockout after 5 failed attempts and requires verified email.
    """
    await _enforce_rate_limit_async(f"auth:login:{get_client_ip(request)}", max_requests=20, window_seconds=60)
    email_clean = payload.email.strip().lower()

    # 1. Check lockout status (Redis-backed with memory fallback)
    is_locked = await redis_manager.is_locked_out(email_clean)
    if not is_locked:
        is_locked, _ = security_service.is_locked_out(email_clean)
    if is_locked:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Account temporarily locked due to multiple failed attempts. Try again later.",
        )

    repo = UserRepository(session)
    user = await repo.get_by_email(email_clean)
    if not user:
        await _record_failed_attempt_redis(email_clean)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email is not verified. Please verify your email before logging in.",
        )

    # 2. Verify password with Argon2
    pw_matches = security_service.verify_password(user.password_hash, payload.password)
    if not pw_matches:
        count = await _record_failed_attempt_redis(email_clean)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid email or password. Attempt {count}/5 before lockout.",
        )

    # 3. Verify mandatory TOTP 2FA
    if not payload.totp_token:
        return {
            "status": "2FA_REQUIRED",
            "message": "Enter 6-digit authenticator code to complete login.",
            "email": user.email,
        }

    totp_valid = security_service.verify_totp(user.totp_secret, payload.totp_token)
    if not totp_valid:
        count = await _record_failed_attempt_redis(email_clean)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid 2FA code. Attempt {count}/5 before lockout.",
        )

    # Reset attempts on success
    await _reset_failed_attempts_redis(email_clean)

    token = security_service.create_access_token(
        subject=user.email,
        extra_claims={"user_id": user.id, "mode": "PAPER"},
    )
    logger.info(f"User {email_clean} successfully authenticated.")

    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": user.id,
        "email": user.email,
        "is_2fa_enabled": True,
        "is_admin": user.role == "ADMIN",
        "is_email_verified": True,
        "trading_mode": "PAPER",
    }


@router.get("/me")
async def get_me(user: UserModel = Depends(get_current_user)):
    """Fetch profile of authenticated user."""
    return {
        "user_id": user.id,
        "email": user.email,
        "is_admin": user.role == "ADMIN",
        "is_email_verified": user.email_verified,
        "is_2fa_enabled": user.totp_enabled,
        "live_trading_enabled": False,
        "connected_brokers": user.connected_brokers or ["PAPER"],
        "default_mode": "PAPER",
    }


# -------------------------------------------------------------------------
# Redis-backed brute-force tracking helpers
# -------------------------------------------------------------------------
async def _record_failed_attempt_redis(identifier: str) -> int:
    """Record a failed auth attempt in Redis and return current count. Lock out at 5."""
    count = security_service.record_failed_attempt(identifier)
    key = f"auth_fail:{identifier}"
    import time
    now = time.time()
    cutoff = now - 300

    if redis_manager._is_connected and redis_manager._redis:
        try:
            pipe = redis_manager._redis.pipeline()
            pipe.zremrangebyscore(key, 0, cutoff)
            pipe.zadd(key, {str(now): now})
            pipe.zcard(key)
            pipe.expire(key, 310)
            _, _, r_count, _ = await pipe.execute()
            count = max(count, r_count)
        except Exception:
            pass

    if count >= 5:
        await redis_manager.record_lockout(identifier, 300)

    return count


async def _reset_failed_attempts_redis(identifier: str):
    """Clear failed attempts from Redis."""
    key = f"auth_fail:{identifier}"
    if redis_manager._is_connected and redis_manager._redis:
        try:
            await redis_manager._redis.delete(key)
            await redis_manager._redis.delete(f"lockout:{identifier}")
        except Exception:
            pass
    redis_manager._mem_lockouts.pop(identifier, None)
    security_service.reset_failed_attempts(identifier)
