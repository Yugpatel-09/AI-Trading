import os
from datetime import datetime, timedelta, timezone

import pyotp
import pytest
from fastapi.testclient import TestClient

from services.api.app.auth.router import USERS_DB, seed_admin_user
from services.api.app.auth.security import security_service
from services.api.app.brokers.crypto_vault import BrokerTokenVault
from services.api.app.core.config import Settings, settings
from services.api.app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_test_admin_credentials():
    """Ensure test admin credentials exist for test cases."""
    settings.ADMIN_PASSWORD = settings.ADMIN_PASSWORD or "TradeForge@Admin2026!"
    settings.ADMIN_TOTP_SECRET = settings.ADMIN_TOTP_SECRET or "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"
    seed_admin_user()
    yield


def test_argon2_hashing():
    pw = "SuperSecureTradingP@ss123"
    hashed = security_service.hash_password(pw)
    assert hashed != pw
    assert security_service.verify_password(hashed, pw) is True
    assert security_service.verify_password(hashed, "WrongPassword") is False


def test_totp_generation_and_validation():
    secret = security_service.generate_totp_secret()
    assert len(secret) == 32
    totp = pyotp.TOTP(secret)
    current_token = totp.now()
    assert security_service.verify_totp(secret, current_token) is True
    assert security_service.verify_totp(secret, "000000") is False


def test_signup_email_verification_and_2fa_flow():
    email = "trader_verified_test@tradeforge.io"
    security_service.reset_failed_attempts(email)
    signup_payload = {
        "email": email,
        "password": "StrongPassword!2026",
        "consent_risk_disclosure": True,
        "consent_terms": True,
        "consent_data_use": True,
    }
    # 1. Signup: Token must NOT be returned in response (sent via email service)
    res = client.post("/api/v1/auth/signup", json=signup_payload)
    assert res.status_code == 200, res.text
    data = res.json()
    assert "email_verification_token" not in data
    assert "totp_secret" in data
    secret = data["totp_secret"]

    # Server holds token securely for dispatch
    user = USERS_DB.get(email)
    assert user is not None
    v_token = user.email_verification_token
    assert v_token is not None

    # 2. Attempt 2FA BEFORE email verification -> MUST BE REJECTED (403 Forbidden)
    totp = pyotp.TOTP(secret)
    early_2fa = client.post(
        "/api/v1/auth/verify-2fa",
        json={"email": email, "password": "StrongPassword!2026", "totp_token": totp.now()},
    )
    assert early_2fa.status_code == 403
    assert "not verified" in early_2fa.json()["detail"].lower()

    # 3. Verify with wrong token -> MUST BE REJECTED (400 Bad Request)
    bad_v = client.post(
        "/api/v1/auth/verify-email",
        json={"email": email, "token": "invalid_wrong_token_123"},
    )
    assert bad_v.status_code == 400
    assert "invalid or expired" in bad_v.json()["detail"].lower()

    # 4. Verify with valid token -> SUCCESS
    good_v = client.post(
        "/api/v1/auth/verify-email",
        json={"email": email, "token": v_token},
    )
    assert good_v.status_code == 200
    assert good_v.json()["is_email_verified"] is True

    # 5. Verify 2FA AFTER email verification with correct password -> SUCCESS
    token = totp.now()
    verify_res = client.post(
        "/api/v1/auth/verify-2fa",
        json={"email": email, "password": "StrongPassword!2026", "totp_token": token},
    )
    assert verify_res.status_code == 200
    vdata = verify_res.json()
    assert "access_token" in vdata
    assert vdata["is_email_verified"] is True
    assert vdata["is_admin"] is False

    # 6. Check /me endpoint
    jwt_token = vdata["access_token"]
    me_res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {jwt_token}"})
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["is_email_verified"] is True
    assert me_data["is_admin"] is False


def test_email_verification_token_expires_after_24_hours():
    """Security Check: Email verification tokens older than 24 hours must be rejected."""
    email = "expired_token_user@tradeforge.io"
    security_service.reset_failed_attempts(email)
    client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "StrongPassword!2026",
            "consent_risk_disclosure": True,
            "consent_terms": True,
            "consent_data_use": True,
        },
    )
    user = USERS_DB[email]
    token = user.email_verification_token

    # Simulate token sent 25 hours ago
    user.email_verification_sent_at = datetime.now(timezone.utc) - timedelta(hours=25)

    res = client.post("/api/v1/auth/verify-email", json={"email": email, "token": token})
    assert res.status_code == 400
    assert "expired after 24 hours" in res.json()["detail"].lower()


def test_resend_verification_does_not_return_token():
    """Security Check: Resending verification token dispatches it via email and conceals from response."""
    email = "resend_token_user@tradeforge.io"
    security_service.reset_failed_attempts(email)
    client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "StrongPassword!2026",
            "consent_risk_disclosure": True,
            "consent_terms": True,
            "consent_data_use": True,
        },
    )
    user = USERS_DB[email]
    initial_token = user.email_verification_token

    res = client.post("/api/v1/auth/resend-verification", json={"email": email})
    assert res.status_code == 200
    data = res.json()
    assert "email_verification_token" not in data
    # Token was rotated in backend
    assert user.email_verification_token != initial_token


def test_verify_2fa_requires_password_and_locks_out():
    """Security Check: /verify-2fa validates password and locks out after 5 consecutive failures."""
    email = "twofa_lockout_user@tradeforge.io"
    security_service.reset_failed_attempts(email)
    s_res = client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "CorrectPassword123!",
            "consent_risk_disclosure": True,
            "consent_terms": True,
            "consent_data_use": True,
        },
    )
    secret = s_res.json()["totp_secret"]
    token = USERS_DB[email].email_verification_token
    client.post("/api/v1/auth/verify-email", json={"email": email, "token": token})

    totp = pyotp.TOTP(secret)

    # 1. Wrong password rejected
    bad_pw_res = client.post(
        "/api/v1/auth/verify-2fa",
        json={"email": email, "password": "WrongPassword!", "totp_token": totp.now()},
    )
    assert bad_pw_res.status_code == 401
    assert "invalid password" in bad_pw_res.json()["detail"].lower()

    # 2. Complete 5 consecutive failures
    for _ in range(4):
        client.post(
            "/api/v1/auth/verify-2fa",
            json={"email": email, "password": "WrongPassword!", "totp_token": totp.now()},
        )

    # 3. 6th attempt must trigger HTTP 429 Too Many Requests lockout
    lockout_res = client.post(
        "/api/v1/auth/verify-2fa",
        json={"email": email, "password": "CorrectPassword123!", "totp_token": totp.now()},
    )
    assert lockout_res.status_code == 429
    assert "locked" in lockout_res.json()["detail"].lower()


def test_admin_seeded_from_env_only():
    """Verify administrator is seeded from environment only and can authenticate."""
    seed_admin_user()
    totp = pyotp.TOTP(settings.ADMIN_TOTP_SECRET)

    login_res = client.post(
        "/api/v1/auth/login",
        json={
            "email": settings.ADMIN_EMAIL,
            "password": settings.ADMIN_PASSWORD,
            "totp_token": totp.now(),
        },
    )
    assert login_res.status_code == 200, login_res.text
    data = login_res.json()
    assert data["is_admin"] is True
    assert data["is_email_verified"] is True

    me_res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {data['access_token']}"})
    assert me_res.status_code == 200
    assert me_res.json()["is_admin"] is True


def test_cannot_signup_as_admin():
    """Security Check: Administrator privileges cannot be acquired via public signup."""
    # 1. Attempting to sign up with the admin email must be rejected
    res_admin = client.post(
        "/api/v1/auth/signup",
        json={
            "email": settings.ADMIN_EMAIL,
            "password": "SomeHackerPassword123!",
            "consent_risk_disclosure": True,
            "consent_terms": True,
            "consent_data_use": True,
        },
    )
    assert res_admin.status_code == 400
    assert "already exists" in res_admin.json()["detail"].lower()

    # 2. Signing up with another email can NEVER yield is_admin=True
    res_other = client.post(
        "/api/v1/auth/signup",
        json={
            "email": "normal_trader_not_admin@tradeforge.io",
            "password": "ValidPassword!2026",
            "consent_risk_disclosure": True,
            "consent_terms": True,
            "consent_data_use": True,
        },
    )
    assert res_other.status_code == 200
    data = res_other.json()

    # Verify email via server token
    user = USERS_DB["normal_trader_not_admin@tradeforge.io"]
    client.post(
        "/api/v1/auth/verify-email",
        json={"email": "normal_trader_not_admin@tradeforge.io", "token": user.email_verification_token},
    )
    # Verify 2FA
    totp = pyotp.TOTP(data["totp_secret"])
    v_res = client.post(
        "/api/v1/auth/verify-2fa",
        json={"email": "normal_trader_not_admin@tradeforge.io", "password": "ValidPassword!2026", "totp_token": totp.now()},
    )
    assert v_res.status_code == 200
    assert v_res.json()["is_admin"] is False


def test_brute_force_lockout():
    email = "locked_user@tradeforge.io"
    security_service.reset_failed_attempts(email)

    # 1. Register user and verify email
    signup_payload = {
        "email": email,
        "password": "CorrectPassword123!",
        "consent_risk_disclosure": True,
        "consent_terms": True,
        "consent_data_use": True,
    }
    s_res = client.post("/api/v1/auth/signup", json=signup_payload)
    assert s_res.status_code == 200
    user = USERS_DB[email]
    token = user.email_verification_token
    client.post("/api/v1/auth/verify-email", json={"email": email, "token": token})

    # 2. Submit 5 wrong passwords
    for _ in range(5):
        resp = client.post("/api/v1/auth/login", json={"email": email, "password": "BadPassword"})
        assert resp.status_code == 401

    # 3. 6th attempt must be locked out with HTTP 429 Too Many Requests
    lockout_resp = client.post("/api/v1/auth/login", json={"email": email, "password": "BadPassword"})
    assert lockout_resp.status_code == 429
    assert "locked" in lockout_resp.json()["detail"].lower()


def test_non_dev_environment_refuses_to_start_missing_secrets():
    """Rule 3 Enforcement: Non-development environments refuse to start without real secrets."""
    # Create production settings object with missing or default secrets
    prod_settings = Settings(
        ENVIRONMENT="production",
        SECRET_KEY="dev_secret_key_needs_replacement_in_production_32chars", # default placeholder
        ADMIN_PASSWORD=None,
        ADMIN_TOTP_SECRET=None,
        ENCRYPTION_KEY_32BYTES_BASE64=None,
    )
    with pytest.raises(RuntimeError) as exc_info:
        prod_settings.validate_production_secrets()

    err_text = str(exc_info.value)
    assert "refuses to start in non-development environment" in err_text
    assert "SECRET_KEY" in err_text
    assert "ADMIN_PASSWORD" in err_text
    assert "ADMIN_TOTP_SECRET" in err_text
    assert "ENCRYPTION_KEY_32BYTES_BASE64" in err_text


def test_token_vault_refuses_to_start_in_non_dev_without_key():
    """Rule 3 Enforcement: Token vault refuses to start with ephemeral key in non-dev environments."""
    old_env = os.environ.get("ENVIRONMENT")
    old_key = os.environ.get("ENCRYPTION_KEY_32BYTES_BASE64")
    try:
        os.environ["ENVIRONMENT"] = "production"
        if "ENCRYPTION_KEY_32BYTES_BASE64" in os.environ:
            del os.environ["ENCRYPTION_KEY_32BYTES_BASE64"]

        with pytest.raises(RuntimeError) as exc_info:
            BrokerTokenVault()
        assert "ENCRYPTION_KEY_32BYTES_BASE64 is missing in non-dev environment" in str(exc_info.value)
    finally:
        if old_env is not None:
            os.environ["ENVIRONMENT"] = old_env
        else:
            os.environ.pop("ENVIRONMENT", None)
        if old_key is not None:
            os.environ["ENCRYPTION_KEY_32BYTES_BASE64"] = old_key
