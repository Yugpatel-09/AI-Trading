import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple

import jwt
import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from services.api.app.core.config import settings

ph = PasswordHasher()

class SecurityService:
    """
    Security service enforcing:
    1. Argon2 password hashing (Section 11)
    2. Mandatory TOTP 2FA (Section 11)
    3. Brute force rate limiting and account lockout
    4. JWT sessions
    """
    def __init__(self):
        # in-memory failed attempt tracking (keyed by email/IP)
        # Format: {identifier: [timestamp1, timestamp2, ...]}
        self._failed_attempts: Dict[str, list[float]] = {}
        self.max_attempts: int = 5
        self.lockout_seconds: int = 300 # 5 minutes lockout

    def hash_password(self, password: str) -> str:
        """Hash password using modern Argon2 algorithm."""
        return ph.hash(password)

    def verify_password(self, hashed: str, password: str) -> bool:
        """Verify plain password against Argon2 hash."""
        try:
            return ph.verify(hashed, password)
        except VerifyMismatchError:
            return False
        except Exception:
            return False

    def generate_totp_secret(self) -> str:
        """Generate a cryptographically secure Base32 TOTP secret."""
        return pyotp.random_base32()

    def get_totp_uri(self, email: str, secret: str, issuer: str = "TradeForge") -> str:
        """Generate otpauth:// URI for authenticator QR codes."""
        totp = pyotp.TOTP(secret)
        return totp.provisioning_uri(name=email, issuer_name=issuer)

    def verify_totp(self, secret: str, token: str) -> bool:
        """Verify 6-digit time-based one-time password with valid time drift window."""
        if not secret or not token:
            return False
        totp = pyotp.TOTP(secret)
        return totp.verify(token.strip(), valid_window=1)

    def record_failed_attempt(self, identifier: str) -> int:
        """Record a failed login attempt and return count within window."""
        now = time.time()
        attempts = self._failed_attempts.get(identifier, [])
        # Prune older than lockout period
        attempts = [t for t in attempts if now - t < self.lockout_seconds]
        attempts.append(now)
        self._failed_attempts[identifier] = attempts
        return len(attempts)

    def is_locked_out(self, identifier: str) -> Tuple[bool, int]:
        """Check if identifier is locked out. Returns (locked: bool, remaining_seconds: int)."""
        now = time.time()
        attempts = self._failed_attempts.get(identifier, [])
        attempts = [t for t in attempts if now - t < self.lockout_seconds]
        self._failed_attempts[identifier] = attempts
        if len(attempts) >= self.max_attempts:
            earliest = attempts[0]
            remaining = int(self.lockout_seconds - (now - earliest))
            return True, max(1, remaining)
        return False, 0

    def reset_failed_attempts(self, identifier: str):
        self._failed_attempts.pop(identifier, None)

    def create_access_token(self, subject: str, extra_claims: Optional[dict] = None) -> str:
        """Issue signed JWT session token."""
        now = datetime.now(timezone.utc)
        expires = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        payload = {
            "sub": subject,
            "iat": int(now.timestamp()),
            "exp": int(expires.timestamp()),
        }
        if extra_claims:
            payload.update(extra_claims)
        return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    def decode_access_token(self, token: str) -> Optional[dict]:
        """Decode and validate JWT access token."""
        try:
            return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        except jwt.PyJWTError:
            return None


security_service = SecurityService()


def hash_password(password: str) -> str:
    return security_service.hash_password(password)


def verify_password(plain_or_hash_1: str, plain_or_hash_2: str) -> bool:
    # Handle both verify_password(plain, hashed) and verify_password(hashed, plain)
    if plain_or_hash_1.startswith("$argon2"):
        return security_service.verify_password(plain_or_hash_1, plain_or_hash_2)
    return security_service.verify_password(plain_or_hash_2, plain_or_hash_1)
