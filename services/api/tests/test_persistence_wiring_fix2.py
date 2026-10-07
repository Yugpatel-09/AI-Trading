import os
from pathlib import Path

import pytest

from services.api.app.core.redis_client import redis_manager
from services.api.app.db.models import Base
from services.api.app.db.repositories.risk_repo import RiskRepository
from services.api.app.db.repositories.user_repo import UserRepository
from services.api.app.db.session import AsyncSession, async_sessionmaker, create_async_engine
from services.risk_guard.guard import RiskGuard


def test_no_in_memory_stores_in_api_routes():
    """
    FIX-2 Verification & Standing Instruction:
    Fails if any route or service module under services/api/app still uses
    deprecated in-memory stores: USERS_DB, USER_RISK_SETTINGS_STORE, BROKER_CONNECTIONS.
    """
    app_dir = Path(__file__).resolve().parent.parent / "app"
    forbidden_tokens = ["USERS_DB", "USER_RISK_SETTINGS_STORE", "BROKER_CONNECTIONS"]

    violations = []
    for py_file in app_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            if token in content:
                violations.append(f"{py_file.name} contains forbidden in-memory store: {token}")

    assert len(violations) == 0, f"Found forbidden in-memory stores in API app: {violations}"


def test_routes_use_database_session_dependencies():
    """
    Verify that auth, risk, and broker router files actually depend on get_db_session.
    """
    app_dir = Path(__file__).resolve().parent.parent / "app"
    routers = [
        app_dir / "auth" / "router.py",
        app_dir / "risk" / "router.py",
        app_dir / "brokers" / "router.py",
    ]

    for r_file in routers:
        content = r_file.read_text(encoding="utf-8")
        assert "get_db_session" in content, f"{r_file.name} does not import or use get_db_session"
        assert "AsyncSession" in content, f"{r_file.name} does not use AsyncSession"


@pytest.mark.asyncio
async def test_app_restart_survival_users_settings_brokers_killswitch(tmp_path):
    """
    FIX-2 Survival Drill:
    1. Populate user, settings, broker connections, and kill-switch state.
    2. Completely dispose the database engine and simulate application restart.
    3. Assert all entities (user, risk settings, broker connections, kill-switch) survive.
    """
    db_file = tmp_path / "restart_survival.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    # --- Phase 1: Boot Process 1 ---
    engine1 = create_async_engine(db_url, echo=False)
    async with engine1.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker1 = async_sessionmaker(bind=engine1, class_=AsyncSession, expire_on_commit=False)

    async with session_maker1() as session1:
        u_repo1 = UserRepository(session1)
        r_repo1 = RiskRepository(session1)

        # 1. Create User & verify email
        user = await u_repo1.create_user("restart_trader@tradeforge.io", "StrongP@ss2026!", email_verified=True)
        await u_repo1.update_totp(user.id, "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP", enabled=True)

        # 2. Risk settings
        from tradeforge_shared.enums import TradingMode
        from tradeforge_shared.schemas import UserRiskSettings
        settings_payload = UserRiskSettings(
            user_id=user.id,
            capital_allocated_inr=250000.0,
            max_loss_per_trade_inr=2500.0,
            max_daily_loss_inr=7500.0,
            mode=TradingMode.AUTO,
        )
        await r_repo1.save_settings(settings_payload)

        # 3. Broker Connection
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        await u_repo1.save_broker_connection(
            user_id=user.id,
            broker_name="ZERODHA",
            encrypted_key="vault_enc_key_zerodha",
            encrypted_secret="vault_enc_secret_zerodha",
            expires_at=now + timedelta(hours=8),
        )

        # 4. Kill Switch (volatile Redis state manager)
        await redis_manager.set_global_kill_switch(True, reason="Restart Drill Test Halt")
        await redis_manager.set_user_kill_switch(user.id, True, reason="User Risk Halt")

        await session1.commit()

    # --- SIMULATE FULL PROCESS TERMINATION / RESTART ---
    await engine1.dispose()

    # --- Phase 2: Boot Fresh Process 2 from persisted disk ---
    engine2 = create_async_engine(db_url, echo=False)
    session_maker2 = async_sessionmaker(bind=engine2, class_=AsyncSession, expire_on_commit=False)

    async with session_maker2() as session2:
        u_repo2 = UserRepository(session2)
        r_repo2 = RiskRepository(session2)

        # Verify User survived
        restarted_user = await u_repo2.get_by_email("restart_trader@tradeforge.io")
        assert restarted_user is not None
        assert restarted_user.id == user.id
        assert restarted_user.email_verified is True
        assert restarted_user.totp_enabled is True
        assert "ZERODHA" in restarted_user.connected_brokers

        # Verify Risk settings survived
        restarted_risk = await r_repo2.get_by_user_id(restarted_user.id)
        assert restarted_risk is not None
        assert restarted_risk.capital_allocated_inr == 250000.0
        assert restarted_risk.max_loss_per_trade_inr == 2500.0
        assert restarted_risk.mode == TradingMode.AUTO

        # Verify Broker connection survived
        bconn = await u_repo2.get_broker_connection(restarted_user.id, "ZERODHA")
        assert bconn is not None
        assert bconn.encrypted_api_key == "vault_enc_key_zerodha"
        assert bconn.status == "CONNECTED"

        brokers_list = await u_repo2.get_broker_connections(restarted_user.id)
        assert len(brokers_list) == 1
        assert brokers_list[0]["broker"] == "ZERODHA"

        # Verify Kill switch survived in Redis volatile state manager
        global_active, g_reason = await redis_manager.is_global_kill_switch_active()
        assert global_active is True
        assert "Restart Drill" in g_reason

        user_active, u_reason = await redis_manager.is_user_kill_switch_active(restarted_user.id)
        assert user_active is True
        assert "User Risk Halt" in u_reason

    await engine2.dispose()


def test_risk_guard_refuses_without_signing_key_outside_tests():
    """
    FIX-3 Verification:
    RiskGuard must refuse to initialize/sign approvals without an explicit signing key outside tests.
    No default key anywhere.
    """
    old_env = os.environ.get("ENVIRONMENT")
    old_key = os.environ.get("SECRET_KEY")

    try:
        os.environ["ENVIRONMENT"] = "production"
        os.environ.pop("SECRET_KEY", None)

        # 1. Without signing_secret and without SECRET_KEY in prod -> MUST RAISE
        with pytest.raises(RuntimeError) as exc_info:
            RiskGuard(signing_secret=None)
        assert "RiskGuard refuses to initialize without an explicit" in str(exc_info.value)

        # 2. With default/placeholder key in prod -> MUST RAISE
        with pytest.raises(RuntimeError) as exc_info:
            RiskGuard(signing_secret="dev_secret_key_needs_replacement_in_production_32chars")
        assert "RiskGuard refuses to initialize without an explicit" in str(exc_info.value)

        # 3. With explicit secure key in prod -> SUCCEEDS
        rg = RiskGuard(signing_secret="super_secure_production_hmac_key_32bytes_min!")
        assert rg.signing_secret == "super_secure_production_hmac_key_32bytes_min!"

    finally:
        if old_env is not None:
            os.environ["ENVIRONMENT"] = old_env
        else:
            os.environ.pop("ENVIRONMENT", None)
        if old_key is not None:
            os.environ["SECRET_KEY"] = old_key
