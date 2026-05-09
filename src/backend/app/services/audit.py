"""Audit-Logging fuer sicherheitsrelevante Aktionen."""
import logging
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import AuditLog, User

logger = logging.getLogger("taskpilot.audit")


async def log_audit(
    db: AsyncSession,
    user: User,
    action: str,
    resource: str,
    resource_id: str | None = None,
    request: Request | None = None,
    details: dict | None = None,
) -> None:
    entry = AuditLog(
        user_id=user.id,
        action=action,
        resource=resource,
        resource_id=resource_id,
        ip_address=request.client.host if request and request.client else None,
        user_agent=request.headers.get("user-agent") if request else None,
        details=details or {},
    )
    db.add(entry)
    logger.info(
        "AUDIT: user=%s action=%s resource=%s/%s",
        user.email, action, resource, resource_id,
    )
