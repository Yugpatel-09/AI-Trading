"""
Unit Tests for SessionManager and Risk Guard Session Enforcement.
Verifies:
1. No-entry window before 09:20:00 IST.
2. No-entry cutoff after 15:00:00 IST.
3. 15:15:00 IST square-off enforcement and position flattening order generation.
4. Daily trade cap ceiling.
5. 3 consecutive loss auto-stop and recovery on win.
"""

from datetime import datetime

import pytest
from tradeforge_shared.enums import OrderSide, TradingMode
from tradeforge_shared.schemas import UserRiskSettings

from services.risk_guard.guard import RiskGuard
from services.risk_guard.session_manager import IST, SessionManager


@pytest.fixture
def session_mgr():
    return SessionManager()


@pytest.fixture
def user_settings():
    return UserRiskSettings(
        user_id="usr_session_test",
        capital_allocated_inr=100000.0,
        max_loss_per_trade_inr=1000.0,
        max_daily_loss_inr=3000.0,
        max_daily_trades=5,
        auto_stop_after_consecutive_losses=3,
        mode=TradingMode.PAPER,
    )


def test_session_manager_blocks_before_0920_ist(session_mgr, user_settings):
    """Test rule 1: No entries allowed before 09:20 IST."""
    early_time = datetime(2026, 10, 5, 9, 16, 0, tzinfo=IST)
    allowed, violation = session_mgr.check_entry_allowed("usr_session_test", user_settings, current_time=early_time)
    assert allowed is False
    assert "09:20:00 IST" in violation


def test_session_manager_allows_during_regular_hours(session_mgr, user_settings):
    """Test regular entries allowed between 09:20 and 15:00 IST."""
    midday_time = datetime(2026, 10, 5, 11, 30, 0, tzinfo=IST)
    allowed, violation = session_mgr.check_entry_allowed("usr_session_test", user_settings, current_time=midday_time)
    assert allowed is True
    assert violation is None


def test_session_manager_blocks_after_1500_ist(session_mgr, user_settings):
    """Test rule 2: No new entries allowed after 15:00 IST."""
    late_entry_time = datetime(2026, 10, 5, 15, 5, 0, tzinfo=IST)
    allowed, violation = session_mgr.check_entry_allowed("usr_session_test", user_settings, current_time=late_entry_time)
    assert allowed is False
    assert "15:00:00 IST" in violation


def test_session_manager_square_off_at_1515_ist(session_mgr, user_settings):
    """Test rule 3: Square-off active at or after 15:15 IST."""
    sqoff_time = datetime(2026, 10, 5, 15, 15, 0, tzinfo=IST)
    assert session_mgr.is_square_off_time(sqoff_time) is True

    allowed, violation = session_mgr.check_entry_allowed("usr_session_test", user_settings, current_time=sqoff_time)
    assert allowed is False
    assert "15:15:00 IST" in violation


def test_session_manager_generates_square_off_flattening_orders(session_mgr):
    """Verify SessionManager generates correct market exit orders to flatten open positions."""
    sqoff_time = datetime(2026, 10, 5, 15, 15, 30, tzinfo=IST)
    open_positions = [
        {"symbol": "RELIANCE", "quantity": 50, "side": OrderSide.BUY, "current_price": 2510.0},
        {"symbol": "INFY", "quantity": 100, "side": OrderSide.SELL, "current_price": 1495.0},
    ]

    orders = session_mgr.generate_square_off_proposals(
        user_id="usr_session_test",
        open_positions=open_positions,
        current_time=sqoff_time,
    )

    assert len(orders) == 2

    # Long RELIANCE position -> Must generate SELL order
    rel_order = next(o for o in orders if o.signal.symbol == "RELIANCE")
    assert rel_order.signal.side == OrderSide.SELL
    assert rel_order.requested_quantity == 50
    assert rel_order.signal.entry_price == 2510.0
    assert "square-off" in rel_order.signal.reason

    # Short INFY position -> Must generate BUY order
    infy_order = next(o for o in orders if o.signal.symbol == "INFY")
    assert infy_order.signal.side == OrderSide.BUY
    assert infy_order.requested_quantity == 100
    assert infy_order.signal.entry_price == 1495.0


def test_session_manager_enforces_daily_trade_cap(session_mgr, user_settings):
    """Test rule 4: Daily trade cap halts trading."""
    midday = datetime(2026, 10, 5, 11, 0, 0, tzinfo=IST)
    # user_settings.max_daily_trades is 5
    for _ in range(5):
        session_mgr.record_trade("usr_session_test")

    allowed, violation = session_mgr.check_entry_allowed("usr_session_test", user_settings, current_time=midday)
    assert allowed is False
    assert "Daily trade limit reached" in violation


def test_session_manager_consecutive_losses_and_recovery(session_mgr, user_settings):
    """Test rule 5: 3 consecutive losses pause trading; reset on winning trade."""
    midday = datetime(2026, 10, 5, 11, 0, 0, tzinfo=IST)

    # Loss 1
    session_mgr.record_trade_result("usr_session_test", -500.0)
    allowed, _ = session_mgr.check_entry_allowed("usr_session_test", user_settings, current_time=midday)
    assert allowed is True

    # Loss 2
    session_mgr.record_trade_result("usr_session_test", -400.0)
    allowed, _ = session_mgr.check_entry_allowed("usr_session_test", user_settings, current_time=midday)
    assert allowed is True

    # Loss 3 -> Auto-stop triggered!
    session_mgr.record_trade_result("usr_session_test", -300.0)
    allowed, violation = session_mgr.check_entry_allowed("usr_session_test", user_settings, current_time=midday)
    assert allowed is False
    assert "Auto-stop triggered" in violation

    # Recovery: winning trade resets consecutive loss counter
    session_mgr.record_trade_result("usr_session_test", +800.0)
    assert session_mgr.get_consecutive_losses("usr_session_test") == 0


def test_risk_guard_integrates_square_off_orders():
    """Verify RiskGuard exposes generate_square_off_orders properly."""
    rg = RiskGuard()
    open_positions = [
        {"symbol": "TCS", "quantity": 25, "side": OrderSide.BUY, "current_price": 3500.0}
    ]
    orders = rg.generate_square_off_orders("usr_rg_test", open_positions)
    assert len(orders) == 1
    assert orders[0].signal.symbol == "TCS"
    assert orders[0].signal.side == OrderSide.SELL
