import pyotp
from fastapi.testclient import TestClient

from services.api.app.auth.router import router
from services.api.app.auth.security import security_service
from services.api.app.main import app

client = TestClient(app)

# Ensure auth router is included on main app
if not any(r.path.startswith("/api/v1/auth") for r in app.routes):
    app.include_router(router)

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

def test_signup_and_2fa_verification_flow():
    email = "trader_test@tradeforge.io"
    signup_payload = {
        "email": email,
        "password": "StrongPassword!2026",
        "consent_risk_disclosure": True,
        "consent_terms": True,
        "consent_data_use": True,
    }
    # 1. Signup
    res = client.post("/api/v1/auth/signup", json=signup_payload)
    assert res.status_code == 200
    data = res.json()
    assert "totp_secret" in data
    assert "totp_uri" in data
    secret = data["totp_secret"]

    # 2. Generate matching TOTP code and verify
    totp = pyotp.TOTP(secret)
    token = totp.now()
    verify_res = client.post("/api/v1/auth/verify-2fa", json={"email": email, "totp_token": token})
    assert verify_res.status_code == 200
    vdata = verify_res.json()
    assert "access_token" in vdata
    assert vdata["trading_mode"] == "PAPER"

def test_brute_force_lockout():
    email = "locked_user@tradeforge.io"
    security_service.reset_failed_attempts(email)

    # Register user first
    signup_payload = {
        "email": email,
        "password": "CorrectPassword123!",
        "consent_risk_disclosure": True,
        "consent_terms": True,
        "consent_data_use": True,
    }
    client.post("/api/v1/auth/signup", json=signup_payload)

    # Submit 5 wrong passwords
    for i in range(5):
        resp = client.post("/api/v1/auth/login", json={"email": email, "password": "BadPassword"})
        assert resp.status_code == 401

    # 6th attempt must be locked out with HTTP 429 Too Many Requests
    lockout_resp = client.post("/api/v1/auth/login", json={"email": email, "password": "BadPassword"})
    assert lockout_resp.status_code == 429
    assert "locked" in lockout_resp.json()["detail"].lower()
