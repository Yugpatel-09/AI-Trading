import pytest
from datetime import datetime, timedelta, timezone
from tradeforge_shared.enums import TradingMode, OrderSide, StrategyType, MarketRegime
from tradeforge_shared.schemas import Signal, OrderProposal, UserRiskSettings
from services.risk_guard.guard import RiskGuard
from services.risk_guard.kill_switch import KillSwitch
from services.risk_guard.watchdog import FeedWatchdog

@pytest.fixture
def test_setup():
    ks = KillSwitch()
    wd = FeedWatchdog(max_staleness_ms=5000)
    guard = RiskGuard(kill_switch=ks, watchdog=wd)
    user_settings = UserRiskSettings(
        user_id="drill_user_1",
        capital_allocated_inr=100000.0,
        max_loss_per_trade_inr=1000.0,
        max_daily_loss_inr=3000.0,
        max_open_positions=2,
        mode=TradingMode.PAPER,
        allowed_instruments=["NIFTY", "RELIANCE"],
    )
    sig = Signal(
        id="sig_drill_01",
        strategy_type=StrategyType.SCALPER_1M,
        symbol="NIFTY",
        side=OrderSide.BUY,
        timeframe="1m",
        timestamp=datetime.now(timezone.utc),
        entry_price=22000.0,
        stop_loss=21950.0,
        target=22080.0,
        regime=MarketRegime.TRENDING_BULLISH,
        quality_score=0.8,
        expected_net_gain_pct=0.35,
        reason="Drill signal",
    )
    return guard, ks, wd, user_settings, sig

def test_dead_feed_triggers_halt(test_setup):
    """Failure Drill 1: Stale market feed (> 5000ms) halts trading."""
    guard, ks, wd, user_settings, sig = test_setup
    
    # Tick arrived 8 seconds ago
    old_time = datetime.now(timezone.utc) - timedelta(seconds=8)
    wd.record_heartbeat("NIFTY", timestamp=old_time)

    is_fresh, delay = wd.is_feed_fresh("NIFTY")
    assert is_fresh is False
    assert delay >= 5000

def test_duplicate_orders_blocked_by_idempotency(test_setup):
    """Failure Drill 2: Network retry with same idempotency token is rejected."""
    guard, ks, wd, user_settings, sig = test_setup
    proposal = OrderProposal(
        idempotency_key="idemp_drill_retry_101",
        user_id=user_settings.user_id,
        signal=sig,
        requested_quantity=20,
        mode=TradingMode.PAPER,
    )
    res1 = guard.validate_proposal(proposal, user_settings, current_ltp=22000.0)
    assert res1.approved is True

    # Immediate duplicate re-submission
    res2 = guard.validate_proposal(proposal, user_settings, current_ltp=22000.0)
    assert res2.approved is False
    assert any("duplicate" in v.lower() for v in res2.violations)

def test_kill_switch_emergency_halt(test_setup):
    """Failure Drill 3: Global emergency kill switch halts all incoming orders."""
    guard, ks, wd, user_settings, sig = test_setup
    ks.activate_global("NSE Connectivity Dropout")

    proposal = OrderProposal(
        idempotency_key="idemp_ks_test",
        user_id=user_settings.user_id,
        signal=sig,
        requested_quantity=20,
        mode=TradingMode.PAPER,
    )
    res = guard.validate_proposal(proposal, user_settings, current_ltp=22000.0)
    assert res.approved is False
    assert any("kill switch" in v.lower() for v in res.violations)

def test_fat_finger_circuit_rejection(test_setup):
    """Failure Drill 4: Fat finger price deviation > 2.5% from LTP rejected."""
    guard, ks, wd, user_settings, sig = test_setup
    
    # Signal proposes buying at 22,700 when current LTP is 22,000 (> 3.1% deviation)
    bad_sig = Signal(
        id="sig_fat_finger",
        strategy_type=StrategyType.SCALPER_1M,
        symbol="NIFTY",
        side=OrderSide.BUY,
        timeframe="1m",
        timestamp=datetime.now(timezone.utc),
        entry_price=22700.0,
        stop_loss=22600.0,
        target=22850.0,
        regime=MarketRegime.TRENDING_BULLISH,
        quality_score=0.75,
        expected_net_gain_pct=0.4,
        reason="Bad quote tick",
    )
    proposal = OrderProposal(
        idempotency_key="idemp_fat_finger",
        user_id=user_settings.user_id,
        signal=bad_sig,
        requested_quantity=20,
        mode=TradingMode.PAPER,
    )
    res = guard.validate_proposal(proposal, user_settings, current_ltp=22000.0)
    assert res.approved is False
    assert any("fat-finger" in v.lower() for v in res.violations)
