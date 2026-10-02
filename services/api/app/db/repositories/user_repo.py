import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.auth.security import hash_password
from services.api.app.db.models import (
    BrokerConnectionModel,
    EmailTokenModel,
    SessionTokenModel,
    UserModel,
)


class UserRepository:
    """Repository managing User records, sessions, email tokens, and broker credentials."""
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, user_id: str) -> Optional[UserModel]:
        stmt = select(UserModel).where(UserModel.id == user_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[UserModel]:
        stmt = select(UserModel).where(UserModel.email == email.lower().strip())
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def create_user(
        self,
        email: str,
        password: str,
        role: str = "USER",
        email_verified: bool = False,
    ) -> UserModel:
        user = UserModel(
            email=email.lower().strip(),
            password_hash=hash_password(password),
            role=role,
            email_verified=email_verified,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def update_totp(self, user_id: str, secret: str, enabled: bool = True) -> None:
        stmt = (
            update(UserModel)
            .where(UserModel.id == user_id)
            .values(totp_secret=secret, totp_enabled=enabled, updated_at=datetime.now(timezone.utc))
        )
        await self.session.execute(stmt)

    async def set_email_verified(self, user_id: str) -> None:
        stmt = (
            update(UserModel)
            .where(UserModel.id == user_id)
            .values(email_verified=True, updated_at=datetime.now(timezone.utc))
        )
        await self.session.execute(stmt)

    # -------------------------------------------------------------------------
    # Email Tokens
    # -------------------------------------------------------------------------
    async def create_email_token(self, user_id: str, token_plaintext: str, expires_at: datetime) -> EmailTokenModel:
        token_hash = hashlib.sha256(token_plaintext.encode("utf-8")).hexdigest()
        tok = EmailTokenModel(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self.session.add(tok)
        await self.session.flush()
        return tok

    async def verify_and_consume_email_token(self, token_plaintext: str, now: datetime) -> Optional[str]:
        """Verify token hash and single-use 24-hour validity. Returns user_id if valid, None otherwise."""
        token_hash = hashlib.sha256(token_plaintext.encode("utf-8")).hexdigest()
        stmt = (
            select(EmailTokenModel)
            .where(EmailTokenModel.token_hash == token_hash)
            .where(EmailTokenModel.used_at.is_(None))
        )
        res = await self.session.execute(stmt)
        record = res.scalar_one_or_none()
        if not record or now > record.expires_at:
            return None

        record.used_at = now
        await self.set_email_verified(record.user_id)
        return record.user_id

    # -------------------------------------------------------------------------
    # Sessions
    # -------------------------------------------------------------------------
    async def create_session(self, user_id: str, refresh_token: str, expires_at: datetime) -> SessionTokenModel:
        token_hash = hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()
        sess = SessionTokenModel(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self.session.add(sess)
        await self.session.flush()
        return sess

    async def revoke_session(self, refresh_token: str) -> bool:
        token_hash = hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()
        stmt = (
            update(SessionTokenModel)
            .where(SessionTokenModel.token_hash == token_hash)
            .values(is_revoked=True)
        )
        res = await self.session.execute(stmt)
        return res.rowcount > 0

    # -------------------------------------------------------------------------
    # Broker Connections
    # -------------------------------------------------------------------------
    async def save_broker_connection(
        self,
        user_id: str,
        broker_name: str,
        encrypted_key: str,
        encrypted_secret: str,
        expires_at: datetime,
    ) -> BrokerConnectionModel:
        stmt = (
            select(BrokerConnectionModel)
            .where(BrokerConnectionModel.user_id == user_id)
            .where(BrokerConnectionModel.broker_name == broker_name)
        )
        res = await self.session.execute(stmt)
        existing = res.scalar_one_or_none()

        now = datetime.now(timezone.utc)
        if existing:
            existing.encrypted_api_key = encrypted_key
            existing.encrypted_api_secret = encrypted_secret
            existing.status = "CONNECTED"
            existing.connected_at = now
            existing.expires_at = expires_at
            bconn = existing
        else:
            bconn = BrokerConnectionModel(
                user_id=user_id,
                broker_name=broker_name,
                encrypted_api_key=encrypted_key,
                encrypted_api_secret=encrypted_secret,
                status="CONNECTED",
                connected_at=now,
                expires_at=expires_at,
            )
            self.session.add(bconn)

        # Update user's connected_brokers list
        user = await self.get_by_id(user_id)
        if user and broker_name not in user.connected_brokers:
            user.connected_brokers = list(user.connected_brokers) + [broker_name]

        await self.session.flush()
        return bconn

    async def get_broker_connections(self, user_id: str) -> List[Dict[str, Any]]:
        stmt = select(BrokerConnectionModel).where(BrokerConnectionModel.user_id == user_id)
        res = await self.session.execute(stmt)
        return [
            {
                "broker": b.broker_name,
                "status": b.status,
                "connected_at": b.connected_at.isoformat(),
                "expires_at": b.expires_at.isoformat(),
                "is_paper": False,
            }
            for b in res.scalars().all()
        ]
