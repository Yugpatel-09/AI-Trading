from datetime import datetime, timezone

from fastapi.testclient import TestClient

from services.api.app.main import app

client = TestClient(app)

def test_health_check_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "tradeforge-api"

def test_system_status_endpoint():
    response = client.get("/api/v1/system/status")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "data_feed_delay_ms" in data
    assert "kill_switch_active" in data

def test_costs_calculate_endpoint():
    payload = {
        "buy_price": 500.0,
        "sell_price": 502.0,
        "quantity": 100,
        "slippage_bps": 5.0
    }
    response = client.post("/api/v1/costs/calculate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["gross_pnl"] == 200.0
    assert data["total_costs"] > 0
    assert data["net_pnl"] < data["gross_pnl"]

def test_risk_validate_endpoint():
    payload = {
        "proposal": {
            "idempotency_key": "api_test_idem_001",
            "user_id": "usr_api_1",
            "signal": {
                "id": "sig_api_001",
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
                "reason": "Test VWAP entry"
            },
            "requested_quantity": 40,
            "mode": "PAPER",
            "broker": "PAPER"
        },
        "user_settings": {
            "user_id": "usr_api_1",
            "capital_allocated_inr": 100000.0,
            "max_loss_per_trade_inr": 1000.0,
            "max_daily_loss_inr": 3000.0,
            "max_open_positions": 2,
            "max_daily_trades": 8,
            "mode": "PAPER",
            "auto_stop_after_consecutive_losses": 3,
            "allowed_instruments": ["RELIANCE", "NIFTY"]
        },
        "current_ltp": 2500.0
    }
    response = client.post("/api/v1/risk/validate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["approved"] is True
    assert data["adjusted_quantity"] == 40
