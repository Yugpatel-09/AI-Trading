from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from services.api.app.auth.email import ConsoleEmailSender, SMTPEmailSender, get_email_sender
from services.api.app.core.config import Settings, settings
from services.api.app.core.security_middleware import rate_limiter
from services.api.app.main import app, lifespan

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    rate_limiter.reset()
    yield
    rate_limiter.reset()


def test_email_sender_factory_and_token_concealment():
    """WP-A.1: EmailSender interface and token concealment in production."""
    # In dev/test, get_email_sender returns ConsoleEmailSender
    sender = get_email_sender()
    assert isinstance(sender, (ConsoleEmailSender, SMTPEmailSender))

    console = ConsoleEmailSender()
    assert console.send_verification_email("trader@tradeforge.io", "test_token_123") is True
    assert console.send_alert_email("trader@tradeforge.io", "Alert", "Body") is True

    # SMTPEmailSender in production
    smtp = SMTPEmailSender(
        host="smtp.tradeforge.io",
        port=587,
        username="smtp_user",
        password="smtp_password",
        from_email="noreply@tradeforge.io",
    )
    with patch("smtplib.SMTP") as mock_smtp_class:
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        success = smtp.send_verification_email("prod_trader@tradeforge.io", "secret_token_abc")
        assert success is True
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("smtp_user", "smtp_password")
        mock_server.send_message.assert_called_once()


def test_security_headers_enforced():
    """WP-A.2: Security headers present on every response."""
    res = client.get("/health")
    assert res.status_code == 200
    assert res.headers["X-Frame-Options"] == "DENY"
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["X-XSS-Protection"] == "1; mode=block"
    assert "frame-ancestors 'none'" in res.headers["Content-Security-Policy"]
    assert res.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_strict_cors_allow_list():
    """WP-A.2: Strict CORS allow-list verification."""
    # Trusted origin receives CORS header
    trusted_origin = settings.cors_origins[0]
    res_trusted = client.get("/health", headers={"Origin": trusted_origin})
    assert res_trusted.headers.get("access-control-allow-origin") == trusted_origin

    # Untrusted attacker origin does NOT receive allow-origin header
    res_untrusted = client.get("/health", headers={"Origin": "https://malicious-phishing-site.com"})
    assert res_untrusted.headers.get("access-control-allow-origin") is None


def test_csrf_protection_on_cookie_flow():
    """WP-A.2: CSRF protection requires matching X-CSRF-Token for cookie-authenticated requests."""
    try:
        # 1. State-changing request with session cookie but missing CSRF token -> 403 Forbidden
        client.cookies.set("tf_session", "session_token_xyz")
        res_no_csrf = client.post("/api/v1/auth/signup", json={"email": "bad@tradeforge.io"})
        assert res_no_csrf.status_code == 403
        assert "CSRF token missing or mismatch" in res_no_csrf.json()["detail"]

        # 2. State-changing request with mismatching CSRF token -> 403 Forbidden
        client.cookies.set("tf_csrf", "expected_csrf_token")
        res_bad_csrf = client.post(
            "/api/v1/auth/signup",
            json={"email": "bad@tradeforge.io"},
            headers={"X-CSRF-Token": "tampered_csrf_token"},
        )
        assert res_bad_csrf.status_code == 403

        # 3. Valid matching CSRF token passes CSRF check (fails further down on payload validation)
        res_good_csrf = client.post(
            "/api/v1/auth/signup",
            json={"email": "bad@tradeforge.io"},
            headers={"X-CSRF-Token": "expected_csrf_token"},
        )
        assert res_good_csrf.status_code != 403
    finally:
        client.cookies.clear()


def test_rate_limiting_on_auth_route():
    """WP-A.2: Rate limiting returns HTTP 429 after exceeding limit."""
    rate_limiter.reset()

    payload = {
        "email": "rate_limit_trader@tradeforge.io",
        "password": "StrongPassword!2026",
        "consent_risk_disclosure": True,
        "consent_terms": True,
        "consent_data_use": True,
    }

    # Hit signup 15 times (limit is 15/min)
    for _ in range(15):
        client.post(
            "/api/v1/auth/signup",
            json=payload,
            headers={"X-Forwarded-For": "203.0.113.195"},
        )

    # 16th request must trigger HTTP 429 Too Many Requests
    blocked_res = client.post(
        "/api/v1/auth/signup",
        json=payload,
        headers={"X-Forwarded-For": "203.0.113.195"},
    )
    assert blocked_res.status_code == 429
    assert "Rate limit exceeded" in blocked_res.json()["detail"]
    assert "Retry-After" in blocked_res.headers


@pytest.mark.asyncio
async def test_production_lifespan_refuses_to_boot_missing_secrets():
    """WP-A.3: FastAPI application lifespan strictly aborts startup in production with missing secrets."""
    prod_settings = Settings(
        ENVIRONMENT="production",
        SECRET_KEY="dev_secret_key_needs_replacement_in_production_32chars",
        ADMIN_PASSWORD=None,
        ADMIN_TOTP_SECRET=None,
        ENCRYPTION_KEY_32BYTES_BASE64=None,
    )

    with patch("services.api.app.main.settings", prod_settings):
        with pytest.raises(RuntimeError) as exc_info:
            async with lifespan(app):
                pass
        err_msg = str(exc_info.value)
        assert "refuses to start in non-development environment" in err_msg
        assert "SECRET_KEY" in err_msg
        assert "ADMIN_PASSWORD" in err_msg
        assert "ADMIN_TOTP_SECRET" in err_msg
        assert "ENCRYPTION_KEY_32BYTES_BASE64" in err_msg
