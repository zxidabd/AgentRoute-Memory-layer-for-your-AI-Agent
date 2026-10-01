"""Security audit logger for authentication, API keys, and workspace events."""

import json
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from fastapi import Request
from sqlalchemy.orm import Session

from agent_memory.models.db_models import SecurityAuditLog


def log_security_event(
    db: Session,
    event_type: str,
    user_id: Optional[str] = None,
    org_id: Optional[str] = None,
    user_email: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    request: Optional[Request] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None
) -> SecurityAuditLog:
    """Records an immutable security audit event."""
    ip = ip_address or (request.client.host if (request and request.client) else None)
    ua = user_agent or (request.headers.get("user-agent", "")[:512] if request else None)
    details_str = json.dumps(details) if details else None

    log_entry = SecurityAuditLog(
        id=f"sec_{secrets.token_hex(8)}",
        user_id=user_id,
        org_id=org_id,
        user_email=user_email,
        event_type=event_type,
        ip_address=ip,
        user_agent=ua,
        details=details_str,
        created_at=datetime.now(timezone.utc)
    )
    db.add(log_entry)
    try:
        db.commit()
    except Exception:
        db.rollback()
    return log_entry
