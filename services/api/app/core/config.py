import base64
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Platform configuration loaded from environment."""
    # Production is the secure default: only explicit development/test relaxes secrets check
    ENVIRONMENT: str = Field(default="production")
    DEBUG: bool = Field(default=False)
    LOG_LEVEL: str = Field(default="INFO")

    # API
    API_HOST: str = Field(default="0.0.0.0")
    API_PORT: int = Field(default=8000)
    ALLOWED_ORIGINS: str = Field(default="http://localhost:3000,http://127.0.0.1:3000")

    # Security
    # In development, a placeholder is permitted. In non-dev environments, validate_production_secrets enforces a secure key.
    SECRET_KEY: str = Field(default="dev_secret_key_needs_replacement_in_production_32chars")
    JWT_ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60)
    ADMIN_EMAIL: str = Field(default="admin@tradeforge.io")
    # Security Rule: No hardcoded admin credentials. Must be supplied via env only.
    ADMIN_PASSWORD: Optional[str] = Field(default=None)
    ADMIN_TOTP_SECRET: Optional[str] = Field(default=None)
    ENCRYPTION_KEY_32BYTES_BASE64: Optional[str] = Field(default=None)

    # Database & Redis
    DATABASE_URL: str = Field(default="sqlite+aiosqlite:///./tradeforge_dev.db")
    REDIS_URL: str = Field(default="redis://localhost:6379/0")

    # Email & Notifications
    EMAIL_PROVIDER: str = Field(default="console")  # "console", "smtp"
    SMTP_HOST: Optional[str] = Field(default=None)
    SMTP_PORT: int = Field(default=587)
    SMTP_USER: Optional[str] = Field(default=None)
    SMTP_PASSWORD: Optional[str] = Field(default=None)
    SMTP_FROM: str = Field(default="noreply@tradeforge.io")
    SMTP_USE_TLS: bool = Field(default=True)

    @property
    def is_dev(self) -> bool:
        return self.ENVIRONMENT.lower() in ["development", "dev", "test", "testing"]

    @property
    def cors_origins(self) -> List[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

    def validate_production_secrets(self):
        """
        Enforce Non-Negotiable Rule 3 (Never hardcode secrets).
        In any non-dev environment, refuse to start if SECRET_KEY, vault key,
        ADMIN_PASSWORD, or ADMIN_TOTP_SECRET are missing or insecure.
        """
        if self.is_dev:
            return

        missing = []
        # 1. SECRET_KEY
        if (
            not self.SECRET_KEY
            or self.SECRET_KEY in [
                "dev_secret_key_needs_replacement_in_production_32chars",
                "change-me-to-a-secure-random-secret-key-at-least-32-chars",
            ]
            or len(self.SECRET_KEY) < 32
        ):
            missing.append("SECRET_KEY (must be set to a secure random string of at least 32 characters)")

        # 2. Vault key
        vault_key = self.ENCRYPTION_KEY_32BYTES_BASE64
        if not vault_key:
            missing.append("ENCRYPTION_KEY_32BYTES_BASE64 (32-byte AES-256 base64-encoded key is missing)")
        else:
            try:
                decoded = base64.b64decode(vault_key)
                if len(decoded) < 32:
                    missing.append("ENCRYPTION_KEY_32BYTES_BASE64 (decoded key must be at least 32 bytes)")
            except Exception:
                missing.append("ENCRYPTION_KEY_32BYTES_BASE64 (invalid base64 encoding)")

        # 3. ADMIN_PASSWORD
        if not self.ADMIN_PASSWORD or len(self.ADMIN_PASSWORD) < 8:
            missing.append("ADMIN_PASSWORD (must be provided via env with at least 8 characters)")

        # 4. ADMIN_TOTP_SECRET
        if not self.ADMIN_TOTP_SECRET or len(self.ADMIN_TOTP_SECRET) < 16:
            missing.append("ADMIN_TOTP_SECRET (must be provided via env with Base32 TOTP secret)")

        if missing:
            err_msg = (
                f"FATAL: Application refuses to start in non-development environment '{self.ENVIRONMENT}'.\n"
                f"The following required production secrets are missing or insecure:\n"
                + "\n".join(f"  - {m}" for m in missing)
            )
            raise RuntimeError(err_msg)


settings = Settings()

