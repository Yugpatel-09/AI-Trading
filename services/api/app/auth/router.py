import secrets
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from services.api.app.auth.security import security_service
from services.api.app.core.config import settings
from services.api.app.core.logging import logger

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication & 2FA"])


# In-memory user store for development (isolated per user)
class UserRecord:
    def __init__(
        self,
        user_id: str,
        email: str,
        password_hash: str,
        totp_secret: str,
        is_2fa_enabled: bool = False,
        is_admin: bool = False,
        is_email_verified: bool = False,
    ):
        self.user_id = user_id
        self.email = email
        self.password_hash = password_hash
        self.totp_secret = totp_secret
        self.is_2fa_enabled = is_2fa_enabled
        self.is_admin = is_admin
        self.is_email_verified = is_email_verified
        self.email_verification_token: Optional[str] = None
        self.email_verification_sent_at: Optional[datetime] = None
        self.live_trading_enabled: bool = False
        self.connected_brokers: list[str] = ["PAPER"]


USERS_DB: Dict[str, UserRecord] = {}


def seed_admin_user() -> UserRecord:
    """Seed the platform administrator from environment configuration only."""
    admin_email = settings.ADMIN_EMAIL.strip().lower()
    if admin_email in USERS_DB:
        return USERS_DB[admin_email]

    pw_hash = security_service.hash_password(settings.ADMIN_PASSWORD)
    user = UserRecord(
        user_id="usr_admin_platform",
        email=admin_email,
        password_hash=pw_hash,
        totp_secret=settings.ADMIN_TOTP_SECRET,
        is_2fa_enabled=True,
        is_admin=True,
        is_email_verified=True,
    )
    USERS_DB[admin_email] = user
    logger.info(f"Platform admin seeded from environment: {admin_email}")
    return user


# Seed platform admin on module load
seed_admin_user()


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
    totp_token: str = Field(..., min_length=6, max_length=6, description="6-digit TOTP code")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    totp_token: Optional[str] = Field(None, min_length=6, max_length=6)


def get_current_user(authorization: Optional[str] = Header(None)) -> UserRecord:
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
    user = USERS_DB.get(email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user


@router.post("/signup")
async def signup(payload: SignupRequest):
    """
    Register new account.
    Enforces SEBI risk disclosure consent, generates TOTP 2FA secret, and dispatches email verification.
    Security: Administrator privileges can NEVER be granted through public signup.
    """
    if not payload.consent_risk_disclosure or not payload.consent_terms or not payload.consent_data_use:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mandatory regulatory consents must be accepted.",
        )

    email_clean = payload.email.strip().lower()
    if email_clean in USERS_DB:
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
    user = UserRecord(
        user_id=user_id,
        email=email_clean,
        password_hash=pw_hash,
        totp_secret=totp_secret,
        is_2fa_enabled=False,
        is_admin=False,
        is_email_verified=False,
    )
    user.email_verification_token = verification_token
    user.email_verification_sent_at = datetime.now(timezone.utc)
    USERS_DB[email_clean] = user
    logger.info(f"New user registered: {email_clean} (ID: {user_id}, Admin: False, Email Verified: False)")

    return {
        "status": "success",
        "message": "User registered. Please verify your email before 2FA activation.",
        "user_id": user_id,
        "email": email_clean,
        "email_verification_token": verification_token,
        "totp_secret": totp_secret,
        "totp_uri": totp_uri,
    }


@router.post("/verify-email")
async def verify_email(payload: VerifyEmailRequest):
    """
    Verify user's email address using registration token.
    """
    email_clean = payload.email.strip().lower()
    user = USERS_DB.get(email_clean)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.is_email_verified:
        return {"status": "success", "message": "Email is already verified."}

    if not user.email_verification_token or user.email_verification_token != payload.token.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired email verification token.",
        )

    user.is_email_verified = True
    user.email_verification_token = None
    logger.info(f"Email successfully verified for user: {email_clean}")

    return {
        "status": "success",
        "message": "Email successfully verified. You can now verify 2FA to activate session.",
        "email": email_clean,
        "is_email_verified": True,
    }


@router.post("/resend-verification")
async def resend_verification(payload: ResendVerificationRequest):
    """
    Regenerate and resend email verification token.
    """
    email_clean = payload.email.strip().lower()
    user = USERS_DB.get(email_clean)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.is_email_verified:
        return {"status": "success", "message": "Email is already verified."}

    user.email_verification_token = secrets.token_hex(16)
    user.email_verification_sent_at = datetime.now(timezone.utc)
    logger.info(f"Verification token regenerated for user: {email_clean}")

    return {
        "status": "success",
        "message": "Verification token regenerated.",
        "email": email_clean,
        "email_verification_token": user.email_verification_token,
    }


@router.post("/verify-2fa")
async def verify_2fa(payload: Verify2FARequest):
    """
    Verify 6-digit TOTP token to activate 2FA and receive authenticated JWT session.
    Requires verified email address.
    """
    email_clean = payload.email.strip().lower()
    user = USERS_DB.get(email_clean)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if not user.is_email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email is not verified. Please verify your email before proceeding.",
        )

    is_valid = security_service.verify_totp(user.totp_secret, payload.totp_token)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid 6-digit TOTP code. Ensure your device clock is synchronized.",
        )

    user.is_2fa_enabled = True
    token = security_service.create_access_token(
        subject=user.email,
        extra_claims={"user_id": user.user_id, "mode": "PAPER"},
    )
    logger.info(f"User {email_clean} successfully verified 2FA.")

    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": user.user_id,
        "email": user.email,
        "is_2fa_enabled": True,
        "is_admin": user.is_admin,
        "is_email_verified": True,
        "trading_mode": "PAPER",
    }


@router.post("/login")
async def login(payload: LoginRequest):
    """
    Authenticate user using Argon2 password and mandatory TOTP 2FA.
    Enforces brute-force lockout after 5 failed attempts and requires verified email.
    """
    email_clean = payload.email.strip().lower()

    # 1. Check lockout status
    locked, remaining = security_service.is_locked_out(email_clean)
    if locked:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Account temporarily locked due to multiple failed attempts. Try again in {remaining} seconds.",
        )

    user = USERS_DB.get(email_clean)
    if not user:
        security_service.record_failed_attempt(email_clean)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email is not verified. Please verify your email before logging in.",
        )

    # 2. Verify password with Argon2
    pw_matches = security_service.verify_password(user.password_hash, payload.password)
    if not pw_matches:
        count = security_service.record_failed_attempt(email_clean)
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
        count = security_service.record_failed_attempt(email_clean)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid 2FA code. Attempt {count}/5 before lockout.",
        )

    # Reset attempts on success
    security_service.reset_failed_attempts(email_clean)

    token = security_service.create_access_token(
        subject=user.email,
        extra_claims={"user_id": user.user_id, "mode": "PAPER"},
    )
    logger.info(f"User {email_clean} successfully authenticated.")

    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": user.user_id,
        "email": user.email,
        "is_2fa_enabled": True,
        "is_admin": user.is_admin,
        "is_email_verified": True,
        "trading_mode": "PAPER",
    }


@router.get("/me")
async def get_me(user: UserRecord = Depends(get_current_user)):
    """Fetch profile of authenticated user."""
    return {
        "user_id": user.user_id,
        "email": user.email,
        "is_admin": user.is_admin,
        "is_email_verified": user.is_email_verified,
        "is_2fa_enabled": user.is_2fa_enabled,
        "live_trading_enabled": user.live_trading_enabled,
        "connected_brokers": user.connected_brokers,
        "default_mode": "PAPER",
    }

