import asyncio
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
def clean_test_environment():
    """Ensure database tables, rate limits, volatile redis state, and email tokens are clean for every test."""
    from services.api.app.auth.email import ConsoleEmailSender
    from services.api.app.auth.router import seed_admin_user_sync
    from services.api.app.core.redis_client import redis_manager
    from services.api.app.core.security_middleware import rate_limiter
    from services.api.app.db.session import init_db

    rate_limiter.reset()
    redis_manager.reset_in_memory()
    ConsoleEmailSender.sent_verification_tokens.clear()

    try:
        asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            pool.submit(asyncio.run, init_db(drop_all=True)).result()
    except RuntimeError:
        try:
            asyncio.run(init_db(drop_all=True))
        except Exception:
            pass

    seed_admin_user_sync()

    yield

    rate_limiter.reset()
    redis_manager.reset_in_memory()
    ConsoleEmailSender.sent_verification_tokens.clear()
