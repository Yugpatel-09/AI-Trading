"""
FIX-7 Failure Drill: Mid-Session Engine Crash & Recovery.

Drill Scenario:
1. Mid-session: Trader places an order, position is established in DB and Redis,
   daily trade count incremented, and emergency kill switch is activated.
2. Engine process crashes mid-session (all in-memory state purged).
3. Engine restarts in a fresh process connected to shared Redis and SQLite DB.
4. Verify on restart:
   - Intraday risk state (daily trade count, daily P&L, consecutive losses) is intact.
   - Open positions are intact in both DB repository and Redis.
   - Kill switch state survives and blocks any new orders.
   - Nothing is double-ordered: re-submitting the pre-crash order proposal
     (same idempotency key) is strictly blocked by Redis idempotency check.
   - Position can be safely reconciled and flattened upon session recovery.
"""

from datetime import datetime, timedelta
from pathlib import Path

import fakeredis
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tradeforge_shared.enums import (
    BrokerType,
    MarketRegime,
    OrderSide,
    OrderStatus,
    StrategyType,
    TradingMode,
)
from tradeforge_shared.schemas import OrderProposal, Signal, UserRiskSettings

from services.api.app.core.config import settings
from services.api.app.core.redis_client import RedisStateManager
from services.api.app.db.models import Base
from services.api.app.db.repositories.order_repo import OrderRepository
from services.api.app.db.repositories.user_repo import UserRepository
from services.engine.data_feed.resampler import IST
from services.execution.gateway.paper_broker import PaperBroker
from services.execution.order_manager import OrderManager, RiskGuardViolationError
from services.risk_guard.guard import RiskGuard


@pytest.mark.asyncio
async def test_engine_mid_session_crash_and_restart_recovery_drill(tmp_path: Path):
    """
    FIX-7 Verification Drill:
    Engine crashes mid-session after executing a position and tripping kill switch.
    A fresh engine process restarts, confirms state, open positions, and kill switch are intact,
    and proves that duplicate orders cannot be placed.
    """
    user_id = "trader_crash_drill_99"
    symbol = "NIFTY"
    session_time = datetime(2026, 10, 5, 10, 15, 0, tzinfo=IST)

    # Persistent SQLite database across simulated processes
    db_file = tmp_path / "tradeforge_crash_drill.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    # Shared Redis daemon simulated across separate process instances
    fake_redis_server = fakeredis.FakeServer()

    # =========================================================================
    # PROCESS 1: Pre-Crash Engine Session
    # =========================================================================
    engine_p1 = create_async_engine(db_url, echo=False)
    session_maker_p1 = async_sessionmaker(bind=engine_p1, class_=AsyncSession, expire_on_commit=False)

    async with engine_p1.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed User in Process 1
    async with session_maker_p1() as session:
        u_repo = UserRepository(session)
        user_record = await u_repo.create_user(
            email="crash_trader@tradeforge.io",
            password="test_secure_password_123",
        )
        user_id = user_record.id
        await session.commit()

    redis_p1 = RedisStateManager(
        redis_client=fakeredis.aioredis.FakeRedis(server=fake_redis_server, decode_responses=True),
        sync_redis_client=fakeredis.FakeRedis(server=fake_redis_server, decode_responses=True),
    )

    risk_guard_p1 = RiskGuard(
        signing_secret=settings.SECRET_KEY,
        redis_manager=redis_p1,
    )
    risk_guard_p1.watchdog.record_heartbeat(symbol, current_time=session_time)

    broker_p1 = PaperBroker(
        initial_capital=500000.0,
        signing_secret=risk_guard_p1.signing_secret,
    )

    order_mgr_p1 = OrderManager(
        risk_guard=risk_guard_p1,
        gateways={BrokerType.PAPER: broker_p1},
    )

    user_settings = UserRiskSettings(
        user_id=user_id,
        capital_allocated_inr=500000.0,
        max_loss_per_trade_inr=5000.0,
        max_daily_loss_inr=20000.0,
        max_open_positions=2,
        max_daily_trades=5,
        mode=TradingMode.PAPER,
        allowed_instruments=[symbol],
        trading_start_time_ist="09:20:00",
        trading_end_time_ist="15:00:00",
    )

    # Trader executes Order 1 mid-session
    sig1 = Signal(
        id="sig_pre_crash_01",
        strategy_type=StrategyType.SCALPER_1M,
        symbol=symbol,
        side=OrderSide.BUY,
        timeframe="1m",
        timestamp=session_time,
        entry_price=22000.0,
        stop_loss=21950.0,
        target=22100.0,
        regime=MarketRegime.TRENDING_BULLISH,
        quality_score=0.88,
        expected_net_gain_pct=0.45,
        reason="Scalp bounce before crash",
    )
    idempotency_key_1 = "idemp_crash_drill_order_001"
    proposal_1 = OrderProposal(
        user_id=user_id,
        broker=BrokerType.PAPER,
        mode=TradingMode.PAPER,
        signal=sig1,
        requested_quantity=25,
        idempotency_key=idempotency_key_1,
    )

    # 1. Submit and fill Order 1
    order_1 = await order_mgr_p1.submit_order(
        proposal=proposal_1,
        user_settings=user_settings,
        current_ltp=22000.0,
        current_time=session_time,
        enforce_trading_hours=True,
    )
    assert order_1.status == OrderStatus.FILLED
    assert order_1.filled_quantity == 25

    # 2. Persist order, fill, and position to DB repository
    async with session_maker_p1() as session:
        o_repo = OrderRepository(session)
        await o_repo.save_order(order_1)
        await o_repo.record_fill(
            order_id=order_1.order_id,
            user_id=user_id,
            symbol=symbol,
            side=order_1.side,
            filled_quantity=order_1.filled_quantity,
            fill_price=order_1.average_fill_price,
            fee_amount=15.0,
        )
        await o_repo.update_position(
            user_id=user_id,
            broker=BrokerType.PAPER,
            symbol=symbol,
            side=order_1.side,
            quantity=order_1.filled_quantity,
            price=order_1.average_fill_price,
            stop_loss=order_1.stop_loss,
            target=order_1.target,
        )
        await session.commit()

    # 3. Update RiskGuard intraday open position in Redis
    risk_guard_p1.update_open_positions(user_id, 1, current_time=session_time)

    # 4. Emergency mid-session event: Global kill switch activated
    risk_guard_p1.kill_switch.activate_global("Emergency NSE Market Halt Drill")

    # Verify pre-crash state in Process 1
    assert risk_guard_p1.get_open_positions(user_id, current_time=session_time) == 1
    assert risk_guard_p1.session_manager.get_trade_count(user_id, current_time=session_time) == 1
    assert risk_guard_p1.kill_switch.is_global_active is True

    # =========================================================================
    # SIMULATE SUDDEN PROCESS CRASH (SIGKILL)
    # Purge all process memory, close P1 database engine, delete references.
    # =========================================================================
    await engine_p1.dispose()
    del order_mgr_p1
    del broker_p1
    del risk_guard_p1
    del redis_p1
    del session_maker_p1
    del engine_p1

    # =========================================================================
    # PROCESS 2: Engine Restart and State Recovery Drill
    # Fresh process boots with brand new instances connecting to shared Redis & DB
    # =========================================================================
    engine_p2 = create_async_engine(db_url, echo=False)
    session_maker_p2 = async_sessionmaker(bind=engine_p2, class_=AsyncSession, expire_on_commit=False)

    redis_p2 = RedisStateManager(
        redis_client=fakeredis.aioredis.FakeRedis(server=fake_redis_server, decode_responses=True),
        sync_redis_client=fakeredis.FakeRedis(server=fake_redis_server, decode_responses=True),
    )

    # Verify that in-memory buffers in Process 2 are completely empty
    assert len(redis_p2._mem_idempotency_keys) == 0
    assert redis_p2._mem_kill_switch_global == (False, "")
    assert len(redis_p2._mem_risk_open_positions) == 0

    risk_guard_p2 = RiskGuard(
        signing_secret=settings.SECRET_KEY,
        redis_manager=redis_p2,
    )
    restart_time = session_time + timedelta(minutes=5)
    risk_guard_p2.watchdog.record_heartbeat(symbol, current_time=restart_time)

    broker_p2 = PaperBroker(
        initial_capital=500000.0,
        signing_secret=risk_guard_p2.signing_secret,
    )

    order_mgr_p2 = OrderManager(
        risk_guard=risk_guard_p2,
        gateways={BrokerType.PAPER: broker_p2},
    )

    # -------------------------------------------------------------------------
    # DRILL VERIFICATION 1: Risk State Intact Across Restart
    # -------------------------------------------------------------------------
    trade_count_recovered = risk_guard_p2.session_manager.get_trade_count(user_id, current_time=restart_time)
    assert trade_count_recovered == 1, "Daily trade count must survive engine crash via Redis"

    daily_pnl_recovered = risk_guard_p2.session_manager.get_daily_pnl(user_id, current_time=restart_time)
    assert daily_pnl_recovered == 0.0, "Daily PnL ledger must survive engine crash"

    # -------------------------------------------------------------------------
    # DRILL VERIFICATION 2: Open Positions Intact in Redis and DB
    # -------------------------------------------------------------------------
    open_pos_redis = risk_guard_p2.get_open_positions(user_id, current_time=restart_time)
    assert open_pos_redis == 1, "Open position count must survive engine crash in Redis"

    async with session_maker_p2() as session:
        o_repo_p2 = OrderRepository(session)
        positions = await o_repo_p2.get_open_positions(user_id)
        assert len(positions) == 1, "Position must survive in database repository"
        pos = positions[0]
        assert pos["symbol"] == symbol
        assert pos["quantity"] == 25
        assert pos["side"] == OrderSide.BUY.value

    # -------------------------------------------------------------------------
    # DRILL VERIFICATION 3: Kill Switch Intact Across Restart
    # -------------------------------------------------------------------------
    assert risk_guard_p2.kill_switch.is_global_active is True, "Global kill switch must survive engine process crash"
    status_p2 = risk_guard_p2.kill_switch.status()
    assert "Emergency NSE Market Halt Drill" in (status_p2.get("reason") or "")

    # Attempting to submit ANY new order while kill switch is active MUST FAIL
    proposal_new = OrderProposal(
        user_id=user_id,
        broker=BrokerType.PAPER,
        mode=TradingMode.PAPER,
        signal=sig1,
        requested_quantity=25,
        idempotency_key="idemp_new_after_crash_002",
    )
    with pytest.raises(RiskGuardViolationError) as exc_ks:
        await order_mgr_p2.submit_order(
            proposal=proposal_new,
            user_settings=user_settings,
            current_ltp=22000.0,
            current_time=restart_time,
            enforce_trading_hours=True,
        )
    assert "kill switch" in str(exc_ks.value).lower()
    assert len(broker_p2.orders) == 0, "Broker must NEVER be touched when kill switch is tripped"

    # -------------------------------------------------------------------------
    # DRILL VERIFICATION 4: Nothing Is Double-Ordered (Idempotency Key Survives)
    # -------------------------------------------------------------------------
    # Even if kill switch is deactivated, the pre-crash order proposal MUST NOT execute again!
    risk_guard_p2.kill_switch.deactivate_global()
    assert risk_guard_p2.kill_switch.is_global_active is False

    # Re-submit the exact same proposal_1 (same idempotency_key_1)
    with pytest.raises(RiskGuardViolationError) as exc_dup:
        await order_mgr_p2.submit_order(
            proposal=proposal_1,
            user_settings=user_settings,
            current_ltp=22000.0,
            current_time=restart_time,
            enforce_trading_hours=True,
        )

    # Violation must explicitly state duplicate idempotency key
    assert "duplicate order" in str(exc_dup.value).lower()
    assert idempotency_key_1 in str(exc_dup.value)

    # Verify Process 2 broker gateway was NEVER called: zero orders placed in P2
    assert len(broker_p2.orders) == 0, "No duplicate order may be routed to broker"

    # Verify database still has exactly 1 order for this key
    async with session_maker_p2() as session:
        o_repo_p2 = OrderRepository(session)
        orders = await o_repo_p2.list_orders(user_id)
        assert len(orders) == 1, "Database must strictly contain only the single original order"
        assert orders[0].idempotency_key == idempotency_key_1

    # -------------------------------------------------------------------------
    # DRILL VERIFICATION 5: Position Reconciliation & Safe Exit
    # -------------------------------------------------------------------------
    # Recovered session squares off the open position at market close
    async with session_maker_p2() as session:
        o_repo_p2 = OrderRepository(session)
        await o_repo_p2.update_position(
            user_id=user_id,
            broker=BrokerType.PAPER,
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=0,
            price=22050.0,
            stop_loss=0.0,
            target=0.0,
        )
        await session.commit()

    # Update RiskGuard position count to 0 in Redis
    risk_guard_p2.update_open_positions(user_id, 0, current_time=restart_time)
    assert risk_guard_p2.get_open_positions(user_id, current_time=restart_time) == 0

    await engine_p2.dispose()
