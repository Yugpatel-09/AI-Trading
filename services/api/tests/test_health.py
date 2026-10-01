
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
