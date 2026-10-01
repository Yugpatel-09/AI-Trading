from datetime import datetime, timezone

import pytest
from tradeforge_shared.enums import MarketRegime, OrderSide, StrategyType, TradingMode
from tradeforge_shared.schemas import OrderProposal, Signal, UserRiskSettings

from services.risk_guard.guard import RiskGuard


@pytest.fixture
def risk_guard():
    return RiskGuard()

@pytest.fixture
def default_user_settings():
    return UserRiskSettings(
        user_id="usr_test_123",
        capital_allocated_inr=100000.0,
        max_loss_per_trade_inr=1000.0,
        max_daily_loss_inr=3000.0,
        max_open_positions=2,
        mode=TradingMode.PAPER,
        auto_stop_after_consecutive_losses=3,
        allowed_instruments=["NIFTY", "RELIANCE", "TCS"],
    )

@pytest.fixture
def sample_signal():
    return Signal(
        id="sig_rel_1m",
        strategy_type=StrategyType.SCALPER_1M,
        symbol="RELIANCE",
        side=OrderSide.BUY,
        timeframe="1m",
        timestamp=datetime.now(timezone.utc),
        entry_price=2500.0,
        stop_loss=2490.0, # 10 Rs stop distance
        target=2520.0,
        regime=MarketRegime.TRENDING_BULLISH,
        quality_score=0.75,
        expected_net_gain_pct=0.4,
        reason="VWAP bounce in strong 5m trend",
    )

def test_risk_guard_approves_valid_proposal(risk_guard, default_user_settings, sample_signal):
    proposal = OrderProposal(
        idempotency_key="idem_001",
        user_id="usr_test_123",
        signal=sample_signal,
        requested_quantity=50, # Risk = 50 * 10 = Rs. 500 <= 1000 limit
        mode=TradingMode.PAPER,
    )
    result = risk_guard.validate_proposal(proposal, default_user_settings, current_ltp=2500.0)
    assert result.approved is True
    assert result.adjusted_quantity == 50
    assert result.calculated_risk_inr == 500.0

def test_risk_guard_kill_switch_halts_trading(risk_guard, default_user_settings, sample_signal):
    risk_guard.kill_switch.activate_global("Emergency NSE Market Crash")
    proposal = OrderProposal(
        idempotency_key="idem_002",
        user_id="usr_test_123",
        signal=sample_signal,
        requested_quantity=50,
        mode=TradingMode.PAPER,
    )
    result = risk_guard.validate_proposal(proposal, default_user_settings, current_ltp=2500.0)
    assert result.approved is False
    assert any("Kill switch" in v for v in result.violations)

def test_risk_guard_rejects_duplicate_idempotency_key(risk_guard, default_user_settings, sample_signal):
    proposal = OrderProposal(
        idempotency_key="idem_duplicate",
        user_id="usr_test_123",
        signal=sample_signal,
        requested_quantity=50,
        mode=TradingMode.PAPER,
    )
    res1 = risk_guard.validate_proposal(proposal, default_user_settings, current_ltp=2500.0)
    assert res1.approved is True

    # Same submission must be rejected
    res2 = risk_guard.validate_proposal(proposal, default_user_settings, current_ltp=2500.0)
    assert res2.approved is False
    assert any("Duplicate order" in v for v in res2.violations)

def test_risk_guard_downscales_quantity_to_honor_max_risk(risk_guard, default_user_settings, sample_signal):
    # User asks for 200 shares. Risk = 200 * 10 = Rs. 2000, which exceeds max_loss_per_trade of 1000
    proposal = OrderProposal(
        idempotency_key="idem_oversize",
        user_id="usr_test_123",
        signal=sample_signal,
        requested_quantity=200,
        mode=TradingMode.PAPER,
    )
    result = risk_guard.validate_proposal(proposal, default_user_settings, current_ltp=2500.0)
    assert result.approved is True
    # Quantity downsized to 100 shares (100 * 10 = Rs. 1000)
    assert result.adjusted_quantity == 100
    assert result.calculated_risk_inr == 1000.0

def test_risk_guard_rejects_blocked_illiquid_stock(risk_guard, default_user_settings):
    blocked_sig = Signal(
        id="sig_blocked",
        strategy_type=StrategyType.SCALPER_1M,
        symbol="SUZLON",
        side=OrderSide.BUY,
        timeframe="1m",
        timestamp=datetime.now(timezone.utc),
        entry_price=45.0,
        stop_loss=44.0,
        target=47.0,
        regime=MarketRegime.RANGE_BOUND,
        quality_score=0.6,
        expected_net_gain_pct=0.5,
        reason="Penny stock breakout",
    )
    proposal = OrderProposal(
        idempotency_key="idem_blocked",
        user_id="usr_test_123",
        signal=blocked_sig,
        requested_quantity=100,
        mode=TradingMode.PAPER,
    )
    result = risk_guard.validate_proposal(proposal, default_user_settings, current_ltp=45.0)
    assert result.approved is False
    assert any("blocklist" in v for v in result.violations)

def test_risk_guard_auto_stops_after_3_consecutive_losses(risk_guard, default_user_settings, sample_signal):
    user_id = default_user_settings.user_id
    risk_guard.record_trade_completion(user_id, -500.0)
    risk_guard.record_trade_completion(user_id, -400.0)
    risk_guard.record_trade_completion(user_id, -300.0) # 3 consecutive losses

    proposal = OrderProposal(
        idempotency_key="idem_after_losses",
        user_id=user_id,
        signal=sample_signal,
        requested_quantity=50,
        mode=TradingMode.PAPER,
    )
    result = risk_guard.validate_proposal(proposal, default_user_settings, current_ltp=2500.0)
    assert result.approved is False
    assert any("consecutive losses" in v for v in result.violations)
