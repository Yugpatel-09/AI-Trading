import os

import pytest

from services.api.app.core.config import settings

# Configure explicit test environment before any application modules are imported
os.environ["ENVIRONMENT"] = "test"
os.environ.setdefault("ADMIN_EMAIL", "admin@tradeforge.io")
os.environ.setdefault("ADMIN_PASSWORD", "TradeForge@Admin2026!")
os.environ.setdefault("ADMIN_TOTP_SECRET", "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP")
os.environ.setdefault("SECRET_KEY", "test_secret_key_needs_32chars_length_min_for_testing")
os.environ.setdefault("ENCRYPTION_KEY_32BYTES_BASE64", "MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE=")

settings.ENVIRONMENT = "test"
settings.ADMIN_EMAIL = "admin@tradeforge.io"
settings.ADMIN_PASSWORD = "TradeForge@Admin2026!"
settings.ADMIN_TOTP_SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"
settings.SECRET_KEY = "test_secret_key_needs_32chars_length_min_for_testing"
settings.ENCRYPTION_KEY_32BYTES_BASE64 = "MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE="


@pytest.fixture(autouse=True)
def auto_reset_rate_limiter():
    """Ensure rate limit buckets are fresh for every unit test."""
    from services.api.app.core.security_middleware import rate_limiter
    rate_limiter.reset()
    yield
    rate_limiter.reset()
