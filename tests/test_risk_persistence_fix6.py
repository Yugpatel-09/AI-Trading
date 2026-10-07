"""
FIX-6 Verification Test: Per-User Risk State Persistence.
Verifies that RiskGuard and SessionManager per-user state:
- Daily P&L
- Consecutive losses
- Daily trade count
- Open positions
- Session pause flags
are persisted in Redis keyed by user and trading date, and that fresh RiskGuard instances
built after process restarts still enforce the 3-loss pause, daily loss cap, and trade limits.
"""

from datetime import datetime, timezone

import fakeredis
import fakeredis.aioredis
import pytest
from tradeforge_shared.enums import BrokerType, MarketRegime, OrderSide, StrategyType, TradingMode
from tradeforge_shared.schemas import OrderProposal, Signal, UserRiskSettings

from services.api.app.core.config import settings
from services.api.app.core.redis_client import RedisStateManager
from services.risk_guard.guard import RiskGuard
from services.risk_guard.session_manager import IST


@pytest.fixture
def shared_redis_managers():
    """Create two independent RedisStateManager instances backed by the same shared Redis state."""
    server = fakeredis.FakeServer()
    async_r1 = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
    sync_r1 = fakeredis.FakeRedis(server=server, decode_responses=True)
    mgr1 = RedisStateManager(redis_client=async_r1, sync_redis_client=sync_r1)

    async_r2 = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
    sync_r2 = fakeredis.FakeRedis(server=server, decode_responses=True)
    mgr2 = RedisStateManager(redis_client=async_r2, sync_redis_client=sync_r2)

    return mgr1, mgr2


def make_test_proposal(user_id: str, symbol: str = "NIFTY", price: float = 22000.0) -> OrderProposal:
    sig = Signal(
        id="sig_test_risk_p_01",
        strategy_type=StrategyType.SCALPER_1M,
        symbol=symbol,
        side=OrderSide.BUY,
        timeframe="1m",
        timestamp=datetime(2026, 10, 5, 9, 30, 0, tzinfo=IST),
        entry_price=price,
        stop_loss=price - 50.0,
        target=price + 100.0,
        regime=MarketRegime.TRENDING_BULLISH,
        expected_net_gain_pct=0.85,
        reason="Test scalp entry with risk verification",
    )
    return OrderProposal(
        user_id=user_id,
        broker=BrokerType.PAPER,
        mode=TradingMode.PAPER,
        signal=sig,
        requested_quantity=25,
        idempotency_key=f"prop_{user_id}_{datetime.now(timezone.utc).timestamp()}",
    )


def test_consecutive_losses_and_daily_loss_cap_survive_fresh_risk_guard(shared_redis_managers):
    """
    FIX-6 Requirement:
    Take losses, build a fresh RiskGuard, and show the daily cap and 3-loss pause still apply.
    """
    mgr1, mgr2 = shared_redis_managers
    user_id = "trader_risk_drill_001"
    session_time = datetime(2026, 10, 5, 10, 15, 0, tzinfo=IST)

    user_settings = UserRiskSettings(
        user_id=user_id,
        capital_allocated_inr=500000.0,
        max_loss_per_trade_inr=5000.0,
        max_daily_loss_inr=10000.0,
        auto_stop_after_consecutive_losses=3,
        max_daily_trades=10,
        max_open_positions=2,
        mode=TradingMode.PAPER,
        trading_start_time_ist="09:20:00",
        trading_end_time_ist="15:00:00",
    )

    # 1. Process 1: RiskGuard 1 executes 3 consecutive losing trades
    guard1 = RiskGuard(signing_secret=settings.SECRET_KEY, redis_manager=mgr1)
    guard1.watchdog.record_heartbeat("NIFTY", current_time=session_time)

    # First losing trade
    guard1.record_trade_execution(user_id, current_time=session_time)
    guard1.record_trade_completion(user_id, -1500.0, current_time=session_time)

    # Second losing trade
    guard1.record_trade_execution(user_id, current_time=session_time)
    guard1.record_trade_completion(user_id, -2000.0, current_time=session_time)

    # Third losing trade (hits 3 consecutive losses auto-stop)
    guard1.record_trade_execution(user_id, current_time=session_time)
    guard1.record_trade_completion(user_id, -1800.0, current_time=session_time)

    assert guard1.session_manager.get_consecutive_losses(user_id, current_time=session_time) == 3
    assert guard1.session_manager.get_daily_pnl(user_id, current_time=session_time) == -5300.0
    assert guard1.session_manager.get_trade_count(user_id, current_time=session_time) == 3

    # --- SIMULATE PROCESS RESTART / ENGINE REBOOT ---
    del guard1  # Process 1 terminates

    # 2. Process 2: Fresh RiskGuard instance with empty in-memory structures backed by shared Redis
    fresh_guard = RiskGuard(signing_secret=settings.SECRET_KEY, redis_manager=mgr2)
    fresh_guard.watchdog.record_heartbeat("NIFTY", current_time=session_time)

    # In-memory dicts on fresh_guard are completely empty
    assert len(fresh_guard._user_daily_pnl) == 0
    assert len(fresh_guard._user_consecutive_losses) == 0
    assert len(fresh_guard._user_daily_trade_count) == 0

    # Yet Redis state is immediately read and active
    assert fresh_guard.session_manager.get_consecutive_losses(user_id, current_time=session_time) == 3
    assert fresh_guard.session_manager.get_daily_pnl(user_id, current_time=session_time) == -5300.0
    assert fresh_guard.session_manager.get_trade_count(user_id, current_time=session_time) == 3

    # Attempt new trade entry through fresh_guard: MUST BE REJECTED by 3-loss pause!
    proposal = make_test_proposal(user_id, symbol="NIFTY", price=22000.0)
    result = fresh_guard.validate_proposal(
        proposal=proposal,
        user_settings=user_settings,
        current_ltp=22000.0,
        current_time=session_time,
        enforce_trading_hours=True,
    )
    assert result.approved is False
    assert any("Auto-stop triggered: 3 consecutive losses" in v for v in result.violations)

    # 3. Test Daily Loss Limit Breach
    # Record another loss taking cumulative loss to -10,300 (exceeding ₹10,000 max_daily_loss)
    fresh_guard.record_trade_execution(user_id, current_time=session_time)
    fresh_guard.record_trade_completion(user_id, -5000.0, current_time=session_time)

    assert fresh_guard.session_manager.get_daily_pnl(user_id, current_time=session_time) == -10300.0

    # Reboot again to Fresh Guard 3
    fresh_guard_3 = RiskGuard(signing_secret=settings.SECRET_KEY, redis_manager=mgr2)
    fresh_guard_3.watchdog.record_heartbeat("NIFTY", current_time=session_time)

    proposal_2 = make_test_proposal(user_id, symbol="NIFTY", price=22000.0)
    result_2 = fresh_guard_3.validate_proposal(
        proposal=proposal_2,
        user_settings=user_settings,
        current_ltp=22000.0,
        current_time=session_time,
        enforce_trading_hours=True,
    )
    assert result_2.approved is False
    assert any("Daily loss limit" in v for v in result_2.violations)


def test_open_positions_and_daily_trades_survive_fresh_risk_guard(shared_redis_managers):
    """
    FIX-6 Verification:
    Open position count and daily trade cap persist across RiskGuard instances.
    """
    mgr1, mgr2 = shared_redis_managers
    user_id = "trader_risk_drill_002"
    session_time = datetime(2026, 10, 5, 11, 0, 0, tzinfo=IST)

    user_settings = UserRiskSettings(
        user_id=user_id,
        capital_allocated_inr=500000.0,
        max_loss_per_trade_inr=5000.0,
        max_daily_loss_inr=20000.0,
        max_open_positions=1,  # Max 1 open position
        max_daily_trades=2,    # Max 2 daily trades
        mode=TradingMode.PAPER,
        trading_start_time_ist="09:20:00",
        trading_end_time_ist="15:00:00",
    )

    # 1. Process 1 updates open positions to 1
    guard1 = RiskGuard(signing_secret=settings.SECRET_KEY, redis_manager=mgr1)
    guard1.update_open_positions(user_id, 1, current_time=session_time)
    guard1.record_trade_execution(user_id, current_time=session_time)
    guard1.record_trade_execution(user_id, current_time=session_time)

    del guard1

    # 2. Process 2: Fresh instance
    guard2 = RiskGuard(signing_secret=settings.SECRET_KEY, redis_manager=mgr2)
    guard2.watchdog.record_heartbeat("NIFTY", current_time=session_time)

    assert guard2.get_open_positions(user_id, current_time=session_time) == 1
    assert guard2.session_manager.get_trade_count(user_id, current_time=session_time) == 2

    # Validation must reject due to both open positions limit and daily trade limit
    proposal = make_test_proposal(user_id, symbol="NIFTY", price=22000.0)
    result = guard2.validate_proposal(
        proposal=proposal,
        user_settings=user_settings,
        current_ltp=22000.0,
        current_time=session_time,
        enforce_trading_hours=True,
    )
    assert result.approved is False
    assert any("Daily trade limit reached" in v for v in result.violations)
    assert any("Max open positions limit" in v for v in result.violations)
