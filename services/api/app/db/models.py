import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from services.api.app.db.session import Base


class ReadOnlyAuditLogError(Exception):
    """Raised when an attempt is made to update or delete an immutable audit log record."""
    pass


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"usr_{uuid.uuid4().hex[:12]}")
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="USER", nullable=False)
    totp_secret: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    connected_brokers: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    risk_settings: Mapped[Optional["UserRiskSettingsModel"]] = relationship("UserRiskSettingsModel", back_populates="user", uselist=False, cascade="all, delete-orphan")
    sessions: Mapped[List["SessionTokenModel"]] = relationship("SessionTokenModel", back_populates="user", cascade="all, delete-orphan")
    broker_connections: Mapped[List["BrokerConnectionModel"]] = relationship("BrokerConnectionModel", back_populates="user", cascade="all, delete-orphan")

    @property
    def user_id(self) -> str:
        return self.id

    @property
    def is_admin(self) -> bool:
        return self.role == "ADMIN"

    @property
    def is_email_verified(self) -> bool:
        return self.email_verified

    @property
    def is_2fa_enabled(self) -> bool:
        return self.totp_enabled

    @property
    def live_trading_enabled(self) -> bool:
        return False


class UserRiskSettingsModel(Base):
    __tablename__ = "user_risk_settings"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"risk_{uuid.uuid4().hex[:12]}")
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False)
    capital_allocated_inr: Mapped[float] = mapped_column(Float, default=100000.0, nullable=False)
    max_loss_per_trade_inr: Mapped[float] = mapped_column(Float, default=1000.0, nullable=False)
    max_daily_loss_inr: Mapped[float] = mapped_column(Float, default=3000.0, nullable=False)
    max_open_positions: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    max_daily_trades: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    mode: Mapped[str] = mapped_column(String(32), default="PAPER", nullable=False)
    auto_stop_after_consecutive_losses: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    allowed_instruments: Mapped[List[str]] = mapped_column(JSON, default=lambda: ["NIFTY", "BANKNIFTY", "RELIANCE", "TCS", "HDFCBANK", "INFY"], nullable=False)
    trading_start_time_ist: Mapped[str] = mapped_column(String(16), default="09:20:00", nullable=False)
    trading_end_time_ist: Mapped[str] = mapped_column(String(16), default="15:00:00", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    user: Mapped["UserModel"] = relationship("UserModel", back_populates="risk_settings")


class SessionTokenModel(Base):
    __tablename__ = "session_tokens"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"sess_{uuid.uuid4().hex[:12]}")
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    user: Mapped["UserModel"] = relationship("UserModel", back_populates="sessions")


class EmailTokenModel(Base):
    __tablename__ = "email_tokens"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"emtok_{uuid.uuid4().hex[:12]}")
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


class BrokerConnectionModel(Base):
    __tablename__ = "broker_connections"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"bconn_{uuid.uuid4().hex[:12]}")
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    broker_name: Mapped[str] = mapped_column(String(32), nullable=False)
    encrypted_api_key: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_api_secret: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="CONNECTED", nullable=False)
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped["UserModel"] = relationship("UserModel", back_populates="broker_connections")


class ExecutionOrderModel(Base):
    __tablename__ = "orders"

    order_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    broker: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(16), nullable=False)
    order_type: Mapped[str] = mapped_column(String(32), default="MARKET", nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    stop_loss: Mapped[float] = mapped_column(Float, nullable=False)
    target: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    filled_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    average_fill_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    fills: Mapped[List["FillModel"]] = relationship("FillModel", back_populates="order", cascade="all, delete-orphan")


class FillModel(Base):
    __tablename__ = "fills"

    fill_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"fill_{uuid.uuid4().hex[:12]}")
    order_id: Mapped[str] = mapped_column(String(64), ForeignKey("orders.order_id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(16), nullable=False)
    filled_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    fill_price: Mapped[float] = mapped_column(Float, nullable=False)
    fee_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    order: Mapped["ExecutionOrderModel"] = relationship("ExecutionOrderModel", back_populates="fills")


class PositionModel(Base):
    __tablename__ = "positions"

    position_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"pos_{uuid.uuid4().hex[:12]}")
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    broker: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    side: Mapped[str] = mapped_column(String(16), nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    stop_loss: Mapped[float] = mapped_column(Float, nullable=False)
    target: Mapped[float] = mapped_column(Float, nullable=False)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class TradeModel(Base):
    __tablename__ = "trades"

    trade_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"trd_{uuid.uuid4().hex[:12]}")
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    order_id: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    exit_price: Mapped[float] = mapped_column(Float, nullable=False)
    gross_pnl: Mapped[float] = mapped_column(Float, nullable=False)
    net_pnl: Mapped[float] = mapped_column(Float, nullable=False)
    total_costs: Mapped[float] = mapped_column(Float, nullable=False)
    entry_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    exit_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuditLogRecord(Base):
    """
    Immutable, Append-Only Compliance & Security Audit Log.
    Enforces Non-Negotiable Rule: Updates and deletes are strictly prohibited.
    """
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"aud_{uuid.uuid4().hex[:12]}")
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource: Mapped[str] = mapped_column(String(64), nullable=False)
    details_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


# Enforce append-only invariants on AuditLogRecord
@event.listens_for(AuditLogRecord, "before_update")
def receive_audit_log_before_update(mapper, connection, target):
    raise ReadOnlyAuditLogError(
        "CRITICAL COMPLIANCE VIOLATION: Audit log records are strictly append-only. Modification is prohibited."
    )


@event.listens_for(AuditLogRecord, "before_delete")
def receive_audit_log_before_delete(mapper, connection, target):
    raise ReadOnlyAuditLogError(
        "CRITICAL COMPLIANCE VIOLATION: Audit log records are strictly append-only. Deletion is prohibited."
    )
