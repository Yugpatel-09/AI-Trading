import pyotp
from fastapi.testclient import TestClient

from services.api.app.auth.router import seed_admin_user
from services.api.app.auth.security import security_service
from services.api.app.core.config import settings
from services.api.app.main import app

client = TestClient(app)


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
    signup_payload = {
        "email": email,
        "password": "StrongPassword!2026",
        "consent_risk_disclosure": True,
        "consent_terms": True,
        "consent_data_use": True,
    }
    # 1. Signup
    res = client.post("/api/v1/auth/signup", json=signup_payload)
    assert res.status_code == 200, res.text
    data = res.json()
    assert "email_verification_token" in data
    assert "totp_secret" in data
    v_token = data["email_verification_token"]
    secret = data["totp_secret"]

    # 2. Attempt 2FA BEFORE email verification -> MUST BE REJECTED (403 Forbidden)
    totp = pyotp.TOTP(secret)
    early_2fa = client.post(
        "/api/v1/auth/verify-2fa",
        json={"email": email, "totp_token": totp.now()},
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

    # 5. Verify 2FA AFTER email verification -> SUCCESS
    token = totp.now()
    verify_res = client.post(
        "/api/v1/auth/verify-2fa",
        json={"email": email, "totp_token": token},
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

    # Verify email
    client.post(
        "/api/v1/auth/verify-email",
        json={"email": "normal_trader_not_admin@tradeforge.io", "token": data["email_verification_token"]},
    )
    # Verify 2FA
    totp = pyotp.TOTP(data["totp_secret"])
    v_res = client.post(
        "/api/v1/auth/verify-2fa",
        json={"email": "normal_trader_not_admin@tradeforge.io", "totp_token": totp.now()},
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
    token = s_res.json()["email_verification_token"]
    client.post("/api/v1/auth/verify-email", json={"email": email, "token": token})

    # 2. Submit 5 wrong passwords
    for _ in range(5):
        resp = client.post("/api/v1/auth/login", json={"email": email, "password": "BadPassword"})
        assert resp.status_code == 401

    # 3. 6th attempt must be locked out with HTTP 429 Too Many Requests
    lockout_resp = client.post("/api/v1/auth/login", json={"email": email, "password": "BadPassword"})
    assert lockout_resp.status_code == 429
    assert "locked" in lockout_resp.json()["detail"].lower()
