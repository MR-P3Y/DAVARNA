from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.admin_guard import AdminIdentity, require_admin_any
from app.core.db import get_db
from app.models.admin_audit import AdminAuditLog
from app.schemas.admin_audit import AdminAuditLogOut

router = APIRouter(prefix="/admin/audit", tags=["admin-audit"])


@router.get("/logs", response_model=list[AdminAuditLogOut])
def list_admin_audit_logs(
    actor_user_id: int | None = None,
    action: str | None = None,
    target_type: str | None = None,
    target_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    admin: AdminIdentity = Depends(require_admin_any),
):
    if not admin.has_any_role("ADMIN", "SUPER_ADMIN"):
        raise HTTPException(status_code=403, detail="admin role required")
    stmt = select(AdminAuditLog)

    if actor_user_id is not None:
        stmt = stmt.where(AdminAuditLog.actor_user_id == actor_user_id)
    if action:
        stmt = stmt.where(AdminAuditLog.action == action)
    if target_type:
        stmt = stmt.where(AdminAuditLog.target_type == target_type)
    if target_id is not None:
        stmt = stmt.where(AdminAuditLog.target_id == target_id)

    stmt = stmt.order_by(AdminAuditLog.id.desc()).limit(limit)
    return list(db.execute(stmt).scalars().all())
