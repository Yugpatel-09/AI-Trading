from datetime import datetime, timezone

import pyotp
import pytest
from fastapi.testclient import TestClient

from services.api.app.auth.router import seed_admin_user
from services.api.app.auth.security import security_service
from services.api.app.core.config import settings
from services.api.app.main import app
from services.api.app.risk.service import global_kill_switch, global_watchdog

client = TestClient(app)


def register_and_login_user(email: str, password: str = "SecurePass123!", is_admin: bool = False):
    """Helper to create and authenticate a test user with verified email and 2FA."""
    # Ensure any previous attempts are cleared
    security_service.reset_failed_attempts(email)

    signup_res = client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": password,
            "consent_risk_disclosure": True,
            "consent_terms": True,
            "consent_data_use": True,
        },
    )
    assert signup_res.status_code == 200, signup_res.text
    signup_data = signup_res.json()
    secret = signup_data["totp_secret"]
    user_id = signup_data["user_id"]
    email_token = signup_data["email_verification_token"]

    # 1. Verify email
    v_res = client.post(
        "/api/v1/auth/verify-email",
        json={"email": email, "token": email_token},
    )
    assert v_res.status_code == 200, v_res.text

    # 2. Verify 2FA to activate session
    totp = pyotp.TOTP(secret)
    token = totp.now()
    verify_res = client.post(
        "/api/v1/auth/verify-2fa",
        json={"email": email, "totp_token": token},
    )
    assert verify_res.status_code == 200
    access_token = verify_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}
    return user_id, headers


def login_admin():
    """Authenticate platform administrator seeded from environment."""
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
    token = login_res.json()["access_token"]
    return "usr_admin_platform", {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def reset_system_state():
    """Ensure kill switch is reset and heartbeats are recorded before every test."""
    global_kill_switch.deactivate_global()
    global_kill_switch._user_switches.clear()
    for sym in ["RELIANCE", "NIFTY", "TCS", "HDFCBANK"]:
        global_watchdog.record_heartbeat(sym)
    yield
    global_kill_switch.deactivate_global()
    global_kill_switch._user_switches.clear()


def test_unauthenticated_requests_rejected():
    """Security Check: Unauthenticated access to risk and kill-switch endpoints returns 401."""
    endpoints = [
        ("GET", "/api/v1/risk/settings", None),
        ("PUT", "/api/v1/risk/settings", {}),
        ("POST", "/api/v1/risk/validate", {}),
        ("POST", "/api/v1/risk/kill-switch/activate", {}),
        ("POST", "/api/v1/risk/kill-switch/deactivate", {}),
        ("GET", "/api/v1/risk/kill-switch/status", None),
    ]

    for method, path, body in endpoints:
        if method == "GET":
            res = client.get(path)
        elif method == "POST":
            res = client.post(path, json=body)
        elif method == "PUT":
            res = client.put(path, json=body)
        assert res.status_code == 401, f"{method} {path} should be 401 Unauthorized without auth token"


def test_authenticated_order_validation_uses_server_limits():
    """Security Check: Proposal is validated using server-stored limits without client limit injection."""
    user_id, headers = register_and_login_user("trader_safe_1@tradeforge.io")

    payload = {
        "proposal": {
            "idempotency_key": "sec_test_idem_001",
            "user_id": user_id,
            "signal": {
                "id": "sig_sec_001",
                "strategy_type": "SCALPER_1M",
                "symbol": "RELIANCE",
                "side": "BUY",
                "timeframe": "1m",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "entry_price": 2500.0,
                "stop_loss": 2490.0,  # 10 Rs stop distance
                "target": 2520.0,
                "regime": "TRENDING_BULLISH",
                "quality_score": 0.82,
                "expected_net_gain_pct": 0.45,
                "reason": "Test server limits entry",
            },
            # User requests 200 shares -> Risk = 200 * 10 = ₹2,000.
            # Default server limit for max_loss_per_trade_inr is ₹1,000.
            "requested_quantity": 200,
            "mode": "PAPER",
            "broker": "PAPER",
        },
        "current_ltp": 2500.0,
    }

    res = client.post("/api/v1/risk/validate", json=payload, headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["approved"] is True
    # Server downscales quantity to 100 to enforce the ₹1,000 limit stored on server!
    assert data["adjusted_quantity"] == 100
    assert data["calculated_risk_inr"] == 1000.0


def test_cannot_validate_order_for_different_user():
    """Security Check: User cannot submit an order proposal masquerading as another user."""
    user_a_id, headers_a = register_and_login_user("user_a@tradeforge.io")
    user_b_id, _ = register_and_login_user("user_b@tradeforge.io")

    payload = {
        "proposal": {
            "idempotency_key": "sec_test_idem_cross",
            "user_id": user_b_id,  # User A trying to validate User B's order
            "signal": {
                "id": "sig_sec_002",
                "strategy_type": "SCALPER_1M",
                "symbol": "RELIANCE",
                "side": "BUY",
                "timeframe": "1m",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "entry_price": 2500.0,
                "stop_loss": 2490.0,
                "target": 2520.0,
                "regime": "TRENDING_BULLISH",
                "quality_score": 0.8,
                "expected_net_gain_pct": 0.4,
                "reason": "Cross-user spoof attempt",
            },
            "requested_quantity": 10,
            "mode": "PAPER",
            "broker": "PAPER",
        },
        "current_ltp": 2500.0,
    }

    res = client.post("/api/v1/risk/validate", json=payload, headers=headers_a)
    assert res.status_code == 403
    assert "another user account" in res.json()["detail"].lower()


def test_regular_user_cannot_activate_or_deactivate_global_kill_switch():
    """Security Check: Non-admin users cannot activate or deactivate the platform global kill switch."""
    _, headers = register_and_login_user("regular_trader@tradeforge.io")

    # Attempt to activate global kill switch
    res_activate = client.post(
        "/api/v1/risk/kill-switch/activate",
        json={"reason": "Malicious halt attempt", "scope": "GLOBAL"},
        headers=headers,
    )
    assert res_activate.status_code == 403
    assert "administrators" in res_activate.json()["detail"].lower()

    # Attempt to deactivate global kill switch
    res_deactivate = client.post(
        "/api/v1/risk/kill-switch/deactivate",
        json={"scope": "GLOBAL"},
        headers=headers,
    )
    assert res_deactivate.status_code == 403
    assert "administrators" in res_deactivate.json()["detail"].lower()


def test_admin_can_activate_and_deactivate_global_kill_switch():
    """Security Check: Admin user (admin@tradeforge.io) can control the global kill switch."""
    admin_id, admin_headers = login_admin()
    user_id, user_headers = register_and_login_user("user_under_halt@tradeforge.io")

    # Admin activates global kill switch
    res_act = client.post(
        "/api/v1/risk/kill-switch/activate",
        json={"reason": "NSE Regulatory Halt", "scope": "GLOBAL"},
        headers=admin_headers,
    )
    assert res_act.status_code == 200
    assert res_act.json()["global_active"] is True

    # Regular user's order must now be halted
    payload = {
        "proposal": {
            "idempotency_key": "idem_during_global_halt",
            "user_id": user_id,
            "signal": {
                "id": "sig_halt_01",
                "strategy_type": "SCALPER_1M",
                "symbol": "RELIANCE",
                "side": "BUY",
                "timeframe": "1m",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "entry_price": 2500.0,
                "stop_loss": 2490.0,
                "target": 2520.0,
                "regime": "TRENDING_BULLISH",
                "quality_score": 0.8,
                "expected_net_gain_pct": 0.4,
                "reason": "Test during halt",
            },
            "requested_quantity": 10,
            "mode": "PAPER",
            "broker": "PAPER",
        },
        "current_ltp": 2500.0,
    }
    res_order = client.post("/api/v1/risk/validate", json=payload, headers=user_headers)
    assert res_order.status_code == 200
    assert res_order.json()["approved"] is False
    assert any("kill switch" in v.lower() for v in res_order.json()["violations"])

    # Admin deactivates global kill switch
    res_deact = client.post(
        "/api/v1/risk/kill-switch/deactivate",
        json={"scope": "GLOBAL"},
        headers=admin_headers,
    )
    assert res_deact.status_code == 200
    assert res_deact.json()["global_active"] is False


def test_user_can_halt_own_account_without_affecting_others():
    """Security Check: User emergency stop halts only their own account."""
    user1_id, headers1 = register_and_login_user("trader_1_halt@tradeforge.io")
    user2_id, headers2 = register_and_login_user("trader_2_active@tradeforge.io")

    # User 1 activates kill switch for their own account
    res_halt = client.post(
        "/api/v1/risk/kill-switch/activate",
        json={"reason": "Feeling anxious, stopping for the day", "scope": "USER"},
        headers=headers1,
    )
    assert res_halt.status_code == 200
    assert res_halt.json()["user_active"] is True
    assert res_halt.json()["global_active"] is False

    # User 1's order is rejected
    sig = {
        "id": "sig_own_halt",
        "strategy_type": "SCALPER_1M",
        "symbol": "RELIANCE",
        "side": "BUY",
        "timeframe": "1m",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "entry_price": 2500.0,
        "stop_loss": 2490.0,
        "target": 2520.0,
        "regime": "TRENDING_BULLISH",
        "quality_score": 0.8,
        "expected_net_gain_pct": 0.4,
        "reason": "Test own halt",
    }
    order1 = client.post(
        "/api/v1/risk/validate",
        json={
            "proposal": {
                "idempotency_key": "idem_u1_halt",
                "user_id": user1_id,
                "signal": sig,
                "requested_quantity": 10,
                "mode": "PAPER",
                "broker": "PAPER",
            },
            "current_ltp": 2500.0,
        },
        headers=headers1,
    )
    assert order1.status_code == 200
    assert order1.json()["approved"] is False
    assert any("kill switch" in v.lower() for v in order1.json()["violations"])

    # User 2's order is APPROVED (unaffected by User 1's halt)
    order2 = client.post(
        "/api/v1/risk/validate",
        json={
            "proposal": {
                "idempotency_key": "idem_u2_ok",
                "user_id": user2_id,
                "signal": sig,
                "requested_quantity": 10,
                "mode": "PAPER",
                "broker": "PAPER",
            },
            "current_ltp": 2500.0,
        },
        headers=headers2,
    )
    assert order2.status_code == 200
    assert order2.json()["approved"] is True

    # User 1 unhalts their account
    res_unhalt = client.post(
        "/api/v1/risk/kill-switch/deactivate",
        json={"scope": "USER"},
        headers=headers1,
    )
    assert res_unhalt.status_code == 200
    assert res_unhalt.json()["user_active"] is False


def test_user_risk_settings_guardrails():
    """Security Check: Server enforces platform risk ceilings on settings updates."""
    user_id, headers = register_and_login_user("risk_settings_trader@tradeforge.io")

    # Fetch initial default settings
    res_get = client.get("/api/v1/risk/settings", headers=headers)
    assert res_get.status_code == 200
    settings = res_get.json()
    assert settings["user_id"] == user_id
    assert settings["max_daily_loss_inr"] == 3000.0

    # 1. Attempt to set daily loss > ₹50,000 platform ceiling
    settings["max_daily_loss_inr"] = 100000.0
    bad_res1 = client.put("/api/v1/risk/settings", json=settings, headers=headers)
    assert bad_res1.status_code == 400
    assert "platform ceiling" in bad_res1.json()["detail"].lower()

    # 2. Attempt to add a platform blocked symbol (SUZLON)
    settings["max_daily_loss_inr"] = 5000.0
    settings["allowed_instruments"].append("SUZLON")
    bad_res2 = client.put("/api/v1/risk/settings", json=settings, headers=headers)
    assert bad_res2.status_code == 400
    assert "blocklist" in bad_res2.json()["detail"].lower()

    # 3. Valid update
    settings["allowed_instruments"] = ["RELIANCE", "NIFTY"]
    settings["max_daily_loss_inr"] = 5000.0
    settings["max_loss_per_trade_inr"] = 1500.0
    good_res = client.put("/api/v1/risk/settings", json=settings, headers=headers)
    assert good_res.status_code == 200
    assert good_res.json()["max_daily_loss_inr"] == 5000.0
    assert good_res.json()["max_loss_per_trade_inr"] == 1500.0
