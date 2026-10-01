from datetime import datetime, timezone

import pytest
from tradeforge_shared.enums import MarketRegime, OrderSide, StrategyType, TradingMode
from tradeforge_shared.schemas import OrderProposal, Signal, UserRiskSettings

from services.risk_guard.guard import RiskGuard


@pytest.fixture
def risk_guard():
    rg = RiskGuard()
    rg.watchdog.record_heartbeat("RELIANCE")
    rg.watchdog.record_heartbeat("NIFTY")
    rg.watchdog.record_heartbeat("SUZLON")
    return rg

@pytest.fixture
def default_user_settings():
    return UserRiskSettings(
        user_id="usr_test_123",
        capital_allocated_inr=100000.0,
        max_loss_per_trade_inr=1000.0,
        max_daily_loss_inr=3000.0,
        max_open_positions=2,
        max_daily_trades=3,
        mode=TradingMode.PAPER,
        auto_stop_after_consecutive_losses=3,
        allowed_instruments=["NIFTY", "RELIANCE", "TCS"],
        trading_start_time_ist="09:20:00",
        trading_end_time_ist="15:00:00",
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

def test_risk_guard_enforces_daily_trade_cap(risk_guard, default_user_settings, sample_signal):
    user_id = default_user_settings.user_id
    # Default settings max_daily_trades is 3
    risk_guard.record_trade_execution(user_id)
    risk_guard.record_trade_execution(user_id)
    risk_guard.record_trade_execution(user_id)

    proposal = OrderProposal(
        idempotency_key="idem_trade_cap",
        user_id=user_id,
        signal=sample_signal,
        requested_quantity=10,
        mode=TradingMode.PAPER,
    )
    result = risk_guard.validate_proposal(proposal, default_user_settings, current_ltp=2500.0)
    assert result.approved is False
    assert any("Daily trade limit reached" in v for v in result.violations)

def test_risk_guard_rejects_stale_or_missing_feed(default_user_settings, sample_signal):
    # Risk guard with an empty watchdog (no ticks registered for RELIANCE)
    empty_guard = RiskGuard()
    proposal = OrderProposal(
        idempotency_key="idem_no_feed",
        user_id="usr_test_123",
        signal=sample_signal,
        requested_quantity=10,
        mode=TradingMode.PAPER,
    )
    result = empty_guard.validate_proposal(proposal, default_user_settings, current_ltp=2500.0)
    assert result.approved is False
    assert any("Market data feed is stale or unavailable" in v for v in result.violations)

def test_risk_guard_rejects_after_15_15_ist(risk_guard, default_user_settings, sample_signal):
    from datetime import timedelta
    ist = timezone(timedelta(hours=5, minutes=30))
    # Mock time at 15:20 IST (post square-off cutoff)
    post_cutoff_time = datetime(2026, 10, 1, 15, 20, 0, tzinfo=ist)

    proposal = OrderProposal(
        idempotency_key="idem_late_entry",
        user_id="usr_test_123",
        signal=sample_signal,
        requested_quantity=10,
        mode=TradingMode.PAPER,
    )
    result = risk_guard.validate_proposal(
        proposal,
        default_user_settings,
        current_ltp=2500.0,
        current_time=post_cutoff_time,
        enforce_trading_hours=True,
    )
    assert result.approved is False
    assert any("15:15:00 IST" in v for v in result.violations)

def test_risk_guard_rejects_before_market_window(risk_guard, default_user_settings, sample_signal):
    from datetime import timedelta
    ist = timezone(timedelta(hours=5, minutes=30))
    # Mock time at 09:10 IST (before start window 09:20 IST)
    early_time = datetime(2026, 10, 1, 9, 10, 0, tzinfo=ist)

    proposal = OrderProposal(
        idempotency_key="idem_early_entry",
        user_id="usr_test_123",
        signal=sample_signal,
        requested_quantity=10,
        mode=TradingMode.PAPER,
    )
    result = risk_guard.validate_proposal(
        proposal,
        default_user_settings,
        current_ltp=2500.0,
        current_time=early_time,
        enforce_trading_hours=True,
    )
    assert result.approved is False
    assert any("before strategy start window" in v for v in result.violations)
