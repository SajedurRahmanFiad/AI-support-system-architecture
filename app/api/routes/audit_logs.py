from fastapi import APIRouter, Depends
from sqlalchemy import select

from app import models
from app.api.deps import DbSession, require_platform_access
from app.api.schemas.audit import AuditLogOut

router = APIRouter(prefix="/audit-logs", dependencies=[Depends(require_platform_access)])


@router.get("", response_model=list[AuditLogOut])
def list_audit_logs(
    db: DbSession,
    brand_id: int | None = None,
    conversation_id: int | None = None,
    event_type: str | None = None,
    limit: int = 100,
) -> list[models.AuditLog]:
    statement = select(models.AuditLog).order_by(models.AuditLog.created_at.desc()).limit(max(1, min(limit, 500)))
    if brand_id is not None:
        statement = statement.where(models.AuditLog.brand_id == brand_id)
    if conversation_id is not None:
        statement = statement.where(models.AuditLog.conversation_id == conversation_id)
    if event_type:
        statement = statement.where(models.AuditLog.event_type == event_type)
    return list(db.scalars(statement))
