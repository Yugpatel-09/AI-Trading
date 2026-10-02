from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.db.models import AuditLogRecord


class AuditRepository:
    """
    Immutable Audit Log Repository.
    Non-Negotiable Rule: Audit logs are strictly append-only.
    Updates and deletes are prohibited and blocked at model event listener level.
    """
    def __init__(self, session: AsyncSession):
        self.session = session

    async def log_action(
        self,
        action: str,
        resource: str,
        details: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> AuditLogRecord:
        record = AuditLogRecord(
            user_id=user_id,
            action=action,
            resource=resource,
            details_json=details or {},
            ip_address=ip_address,
            timestamp=datetime.now(timezone.utc),
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def list_logs(
        self,
        user_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[AuditLogRecord]:
        stmt = select(AuditLogRecord).order_by(AuditLogRecord.timestamp.desc()).limit(limit)
        if user_id:
            stmt = stmt.where(AuditLogRecord.user_id == user_id)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())
