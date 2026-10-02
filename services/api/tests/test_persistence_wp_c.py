from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tradeforge_shared.enums import BrokerType, OrderSide, OrderStatus, OrderType, TradingMode
from tradeforge_shared.schemas import ExecutionOrder, UserRiskSettings

from services.api.app.auth.security import verify_password
from services.api.app.core.redis_client import RedisStateManager
from services.api.app.db.models import (
    Base,
    ReadOnlyAuditLogError,
)
from services.api.app.db.repositories.audit_repo import AuditRepository
from services.api.app.db.repositories.order_repo import OrderRepository
from services.api.app.db.repositories.risk_repo import RiskRepository
from services.api.app.db.repositories.user_repo import UserRepository


@pytest_asyncio.fixture
async def persistent_db(tmp_path):
    """Provides a fresh isolated database file and async session."""
    db_file = tmp_path / "tradeforge_test.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    engine = create_async_engine(db_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session, db_url

    await engine.dispose()


@pytest.mark.asyncio
async def test_user_repository_crud_and_tokens(persistent_db):
    session, _ = persistent_db
    user_repo = UserRepository(session)

    # 1. Create User
    user = await user_repo.create_user("trader@tradeforge.io", "StrongPass@2026!", role="USER")
    assert user.id.startswith("usr_")
    assert user.email == "trader@tradeforge.io"
    assert verify_password("StrongPass@2026!", user.password_hash)

    # 2. Email Verification Token Flow (24h single use)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=24)
    token_obj = await user_repo.create_email_token(user.id, "secure_raw_token_xyz", expires_at)
    assert token_obj.token_hash != "secure_raw_token_xyz"

    # Consume token
    verified_user_id = await user_repo.verify_and_consume_email_token("secure_raw_token_xyz", now)
    assert verified_user_id == user.id

    # Verify user record updated
    refreshed_user = await user_repo.get_by_id(user.id)
    assert refreshed_user.email_verified is True

    # Replay token consumption must fail
    replay_id = await user_repo.verify_and_consume_email_token("secure_raw_token_xyz", now)
    assert replay_id is None

    # 3. Session Management
    sess = await user_repo.create_session(user.id, "refresh_token_alpha", expires_at=now + timedelta(days=7))
    assert sess.is_revoked is False
    revoked = await user_repo.revoke_session("refresh_token_alpha")
    assert revoked is True

    # 4. Broker Connection Persistence
    bconn = await user_repo.save_broker_connection(
        user_id=user.id,
        broker_name="ZERODHA",
        encrypted_key="enc_key_123",
        encrypted_secret="enc_secret_456",
        expires_at=now + timedelta(hours=8),
    )
    assert bconn.status == "CONNECTED"
    connections = await user_repo.get_broker_connections(user.id)
    assert len(connections) == 1
    assert connections[0]["broker"] == "ZERODHA"


@pytest.mark.asyncio
async def test_risk_repository_crud(persistent_db):
    session, _ = persistent_db
    user_repo = UserRepository(session)
    risk_repo = RiskRepository(session)

    user = await user_repo.create_user("risk_user@tradeforge.io", "Password@123")

    # 1. Fetch default settings
    default_settings = await risk_repo.get_by_user_id(user.id)
    assert default_settings.capital_allocated_inr == 100000.0
    assert default_settings.mode == TradingMode.PAPER

    # 2. Update settings
    custom_settings = UserRiskSettings(
        user_id=user.id,
        capital_allocated_inr=250000.0,
        max_loss_per_trade_inr=2500.0,
        max_daily_loss_inr=7500.0,
        max_open_positions=3,
        max_daily_trades=10,
        mode=TradingMode.APPROVE,
        allowed_instruments=["NIFTY", "RELIANCE"],
    )
    saved = await risk_repo.save_settings(custom_settings)
    assert saved.capital_allocated_inr == 250000.0

    # 3. Retrieve and assert persistence
    reloaded = await risk_repo.get_by_user_id(user.id)
    assert reloaded.capital_allocated_inr == 250000.0
    assert reloaded.max_loss_per_trade_inr == 2500.0
    assert reloaded.mode == TradingMode.APPROVE
    assert reloaded.allowed_instruments == ["NIFTY", "RELIANCE"]


@pytest.mark.asyncio
async def test_order_repository_lifecycle(persistent_db):
    session, _ = persistent_db
    user_repo = UserRepository(session)
    order_repo = OrderRepository(session)

    user = await user_repo.create_user("order_user@tradeforge.io", "Password@123")
    now = datetime.now(timezone.utc)

    order = ExecutionOrder(
        order_id="ord_db_101",
        idempotency_key="idemp_db_101",
        user_id=user.id,
        broker=BrokerType.PAPER,
        symbol="NIFTY",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=50,
        price=22000.0,
        stop_loss=21950.0,
        target=22100.0,
        status=OrderStatus.FILLED,
        filled_quantity=50,
        average_fill_price=22001.0,
        created_at=now,
        updated_at=now,
    )

    # 1. Save and retrieve order
    await order_repo.save_order(order)
    retrieved = await order_repo.get_by_id("ord_db_101")
    assert retrieved is not None
    assert retrieved.order_id == "ord_db_101"
    assert retrieved.filled_quantity == 50

    # 2. Retrieve by idempotency key
    by_idemp = await order_repo.get_by_idempotency_key("idemp_db_101")
    assert by_idemp is not None
    assert by_idemp.order_id == "ord_db_101"

    # 3. Record Fill
    fill = await order_repo.record_fill(
        order_id="ord_db_101",
        user_id=user.id,
        symbol="NIFTY",
        side=OrderSide.BUY,
        filled_quantity=50,
        fill_price=22001.0,
        fee_amount=15.5,
    )
    assert fill.filled_quantity == 50

    # 4. Manage Position
    pos = await order_repo.update_position(
        user_id=user.id,
        broker=BrokerType.PAPER,
        symbol="NIFTY",
        side=OrderSide.BUY,
        quantity=50,
        price=22001.0,
        stop_loss=21950.0,
        target=22100.0,
    )
    assert pos.quantity == 50
    positions = await order_repo.get_open_positions(user.id)
    assert len(positions) == 1

    # 5. Record Trade
    trade = await order_repo.record_trade(
        user_id=user.id,
        order_id="ord_db_101",
        symbol="NIFTY",
        side=OrderSide.BUY,
        quantity=50,
        entry_price=22001.0,
        exit_price=22050.0,
        gross_pnl=2450.0,
        net_pnl=2415.0,
        total_costs=35.0,
        entry_time=now,
        exit_time=now + timedelta(minutes=15),
    )
    assert trade.net_pnl == 2415.0


@pytest.mark.asyncio
async def test_audit_log_append_only_enforcement(persistent_db):
    """
    CRITICAL COMPLIANCE TEST (WP-C):
    Audit log must be append-only. Updates and deletes must fail-closed.
    """
    session, _ = persistent_db
    audit_repo = AuditRepository(session)

    log_entry = await audit_repo.log_action(
        action="USER_LOGIN_2FA",
        resource="auth/session",
        details={"ip": "127.0.0.1", "device": "chrome"},
        user_id="usr_audit_01",
        ip_address="127.0.0.1",
    )
    await session.commit()

    logs = await audit_repo.list_logs("usr_audit_01")
    assert len(logs) == 1
    log_entry = logs[0]

    # 1. Attempting an UPDATE on AuditLogRecord must trigger ReadOnlyAuditLogError
    with pytest.raises(ReadOnlyAuditLogError) as exc_info_update:
        log_entry.action = "TAMPERED_ACTION"
        await session.flush()
    assert "strictly append-only" in str(exc_info_update.value)
    await session.rollback()

    # 2. Attempting a DELETE on AuditLogRecord must trigger ReadOnlyAuditLogError
    # Re-fetch fresh log entry
    fresh_entry = (await audit_repo.list_logs("usr_audit_01"))[0]
    with pytest.raises(ReadOnlyAuditLogError) as exc_info_delete:
        await session.delete(fresh_entry)
        await session.flush()
    assert "Deletion is prohibited" in str(exc_info_delete.value)
    await session.rollback()


@pytest.mark.asyncio
async def test_state_survives_process_restart(tmp_path):
    """
    STATE SURVIVAL TEST (WP-C Requirement):
    State must survive a restart.
    Writes full state, tears down engine/process, starts a fresh engine from disk,
    and proves all data is intact.
    """
    db_file = tmp_path / "restart_survival.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    # --- Phase 1: Write State Before Crash ---
    engine1 = create_async_engine(db_url, echo=False)
    async with engine1.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker1 = async_sessionmaker(bind=engine1, class_=AsyncSession, expire_on_commit=False)
    now = datetime.now(timezone.utc)

    async with session_maker1() as session1:
        u_repo = UserRepository(session1)
        r_repo = RiskRepository(session1)
        o_repo = OrderRepository(session1)
        a_repo = AuditRepository(session1)

        user = await u_repo.create_user("survivor@tradeforge.io", "Pass@12345678", email_verified=True)
        await r_repo.save_settings(UserRiskSettings(user_id=user.id, capital_allocated_inr=500000.0, mode=TradingMode.AUTO))
        await o_repo.save_order(ExecutionOrder(
            order_id="ord_survive_1",
            idempotency_key="idemp_survive_1",
            user_id=user.id,
            broker=BrokerType.PAPER,
            symbol="BANKNIFTY",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=25,
            price=48000.0,
            stop_loss=47850.0,
            target=48300.0,
            status=OrderStatus.FILLED,
            filled_quantity=25,
            average_fill_price=48002.0,
            created_at=now,
            updated_at=now,
        ))
        await a_repo.log_action("SYSTEM_CHECKPOINT", "engine/state", {"saved": True}, user_id=user.id)
        await session1.commit()

    # --- Hard Process Restart Simulation: Terminate engine & discard memory ---
    await engine1.dispose()

    # --- Phase 2: Start Fresh Process / Engine from disk ---
    engine2 = create_async_engine(db_url, echo=False)
    session_maker2 = async_sessionmaker(bind=engine2, class_=AsyncSession, expire_on_commit=False)

    async with session_maker2() as session2:
        u_repo2 = UserRepository(session2)
        r_repo2 = RiskRepository(session2)
        o_repo2 = OrderRepository(session2)
        a_repo2 = AuditRepository(session2)

        # 1. User survived
        surviving_user = await u_repo2.get_by_email("survivor@tradeforge.io")
        assert surviving_user is not None
        assert surviving_user.email_verified is True

        # 2. Risk settings survived
        surviving_risk = await r_repo2.get_by_user_id(surviving_user.id)
        assert surviving_risk.capital_allocated_inr == 500000.0
        assert surviving_risk.mode == TradingMode.AUTO

        # 3. Order survived
        surviving_order = await o_repo2.get_by_id("ord_survive_1")
        assert surviving_order is not None
        assert surviving_order.symbol == "BANKNIFTY"
        assert surviving_order.filled_quantity == 25

        # 4. Idempotency survived
        surviving_idemp = await o_repo2.get_by_idempotency_key("idemp_survive_1")
        assert surviving_idemp is not None

        # 5. Audit log survived
        surviving_logs = await a_repo2.list_logs(surviving_user.id)
        assert len(surviving_logs) == 1
        assert surviving_logs[0].action == "SYSTEM_CHECKPOINT"

    await engine2.dispose()


@pytest.mark.asyncio
async def test_redis_state_manager():
    """
    REDIS VOLATILE STATE TEST (WP-C Requirement):
    Tests rate limiting sliding window, lockouts, kill switches, and idempotency tracking.
    """
    r_mgr = RedisStateManager()
    r_mgr.reset_in_memory()

    # 1. Rate limiting sliding window
    assert await r_mgr.check_rate_limit("user:123", max_requests=2, window_seconds=10) is True
    assert await r_mgr.check_rate_limit("user:123", max_requests=2, window_seconds=10) is True
    # 3rd request in 10s window exceeds max_requests=2
    assert await r_mgr.check_rate_limit("user:123", max_requests=2, window_seconds=10) is False

    # 2. Lockout management
    assert await r_mgr.is_locked_out("ip:192.168.1.1") is False
    await r_mgr.record_lockout("ip:192.168.1.1", duration_seconds=60)
    assert await r_mgr.is_locked_out("ip:192.168.1.1") is True

    # 3. Kill Switches
    active, _ = await r_mgr.is_global_kill_switch_active()
    assert active is False
    await r_mgr.set_global_kill_switch(True, reason="Circuit breaker hit")
    active, reason = await r_mgr.is_global_kill_switch_active()
    assert active is True
    assert "Circuit breaker" in reason

    await r_mgr.set_global_kill_switch(False)
    active, _ = await r_mgr.is_global_kill_switch_active()
    assert active is False

    # Per-user kill switch
    active_u, _ = await r_mgr.is_user_kill_switch_active("usr_999")
    assert active_u is False
    await r_mgr.set_user_kill_switch("usr_999", True, reason="User Margin Breached")
    active_u, reason_u = await r_mgr.is_user_kill_switch_active("usr_999")
    assert active_u is True
    assert "Margin Breached" in reason_u

    # 4. Idempotency Key
    assert await r_mgr.check_and_record_idempotency_key("key_101", ttl_seconds=60) is True
    # Duplicate rejected
    assert await r_mgr.check_and_record_idempotency_key("key_101", ttl_seconds=60) is False
