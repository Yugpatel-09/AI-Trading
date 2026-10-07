from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from tradeforge_shared.enums import BrokerType

from services.api.app.auth.router import get_current_user
from services.api.app.brokers.crypto_vault import token_vault
from services.api.app.core.logging import logger
from services.api.app.db.models import UserModel
from services.api.app.db.repositories.user_repo import UserRepository
from services.api.app.db.session import get_db_session
from services.execution.order_manager import order_manager

router = APIRouter(prefix="/api/v1/brokers", tags=["Broker Connection"])


class ConnectBrokerRequest(BaseModel):
    broker: BrokerType
    api_key: str = Field(..., description="Developer API Key")
    api_secret: str = Field(..., description="API Secret or Request Token")


class DisconnectBrokerRequest(BaseModel):
    broker: BrokerType


@router.post("/connect")
async def connect_broker(
    payload: ConnectBrokerRequest,
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Connect broker account using encrypted token storage in PostgreSQL/database.
    Enforces Rule 3 & 4 (Tokens encrypted at rest, never logged in plaintext).
    """
    # Encrypt credentials
    encrypted_key = token_vault.encrypt_token(payload.api_key)
    encrypted_secret = token_vault.encrypt_token(payload.api_secret)

    now = datetime.now(timezone.utc)
    # Most Indian brokers require daily morning login (expires end of trading day)
    expires_at = now.replace(hour=10, minute=0, second=0)  # 15:30 IST ~ 10:00 UTC

    repo = UserRepository(session)
    bconn = await repo.save_broker_connection(
        user_id=user.id,
        broker_name=payload.broker.value,
        encrypted_key=encrypted_key,
        encrypted_secret=encrypted_secret,
        expires_at=expires_at,
    )

    logger.info(f"Broker connected for user {user.id}: {payload.broker.value}")

    return {
        "status": "CONNECTED",
        "broker": payload.broker.value,
        "connected_at": bconn.connected_at.isoformat(),
        "expires_at": bconn.expires_at.isoformat(),
        "daily_relogin_required": True,
        "message": f"Successfully connected {payload.broker.value}. Credentials encrypted with AES-256.",
    }


@router.get("/status")
async def get_broker_connections(
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """List all connected brokers and their daily session expiry status from database."""
    repo = UserRepository(session)
    user_brokers = await repo.get_broker_connections(user.id)
    results = [
        {
            "broker": "PAPER",
            "status": "CONNECTED",
            "connected_at": "SYSTEM",
            "expires_at": "PERPETUAL",
            "is_paper": True,
        }
    ]
    results.extend(user_brokers)
    return results


@router.post("/test-connection")
async def test_broker_connection(
    broker: BrokerType,
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Test broker connection and fetch available margin/funds via OrderManager.
    Gateways are never instantiated or accessed directly.
    """
    if broker == BrokerType.PAPER:
        return await order_manager.test_broker_connection(broker)

    repo = UserRepository(session)
    bconn = await repo.get_broker_connection(user.id, broker.value)
    if not bconn:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{broker.value} is not connected for this account.",
        )

    # Test connection via OrderManager gateway facade
    return await order_manager.test_broker_connection(broker)


@router.post("/disconnect")
async def disconnect_broker(
    payload: DisconnectBrokerRequest,
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Revoke credentials and disconnect broker from database."""
    if payload.broker == BrokerType.PAPER:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot disconnect Paper Broker.")

    repo = UserRepository(session)
    await repo.delete_broker_connection(user.id, payload.broker.value)

    logger.info(f"User {user.id} disconnected broker {payload.broker.value}")
    return {"status": "DISCONNECTED", "broker": payload.broker.value}
