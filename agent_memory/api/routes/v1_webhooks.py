"""Outbound webhook subscription and HMAC-SHA256 signed delivery."""

import hmac
import hashlib
import time
import uuid
from typing import Dict, Any, List
from pydantic import BaseModel, HttpUrl, Field
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ...models.db_models import Webhook
from ...database import get_db_session
from ..auth import get_current_tenant

router = APIRouter(prefix="/v1/webhooks", tags=["Webhooks (v1)"])


class WebhookCreatePayload(BaseModel):
    url: str = Field(..., description="Destination HTTPS URL for receiving memory event webhooks")
    events: List[str] = Field(
        default=["memory.created", "memory.superseded", "user.deleted"],
        description="Subscribed event types"
    )


def generate_webhook_signature(secret: str, payload_str: str, timestamp: int) -> str:
    """Generates an HMAC-SHA256 signature string formatted as 't=timestamp,v1=hash'."""
    signed_payload = f"t={timestamp}.{payload_str}".encode("utf-8")
    sig_hash = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={sig_hash}"


@router.post(
    "",
    summary="Register outbound webhook endpoint",
    description="Registers an endpoint to receive real-time updates when memories are created or superseded."
)
def register_webhook(
    payload: WebhookCreatePayload,
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    secret_key = f"whsec_{uuid.uuid4().hex}"
    webhook = Webhook(
        id=f"whk_{uuid.uuid4().hex[:10]}",
        org_id=tenant_id,
        url=payload.url,
        secret_key=secret_key,
        events_json=str(payload.events),
        is_active=True
    )
    db.add(webhook)
    db.commit()

    return {
        "webhook_id": webhook.id,
        "url": webhook.url,
        "secret_key": secret_key,
        "message": "Store your webhook secret_key securely. It is used to verify HMAC-SHA256 signatures."
    }


@router.post(
    "/{webhook_id}/test",
    summary="Dispatch test ping event",
    description="Generates an HMAC-SHA256 signed test payload to verify signature verification on the client."
)
def test_webhook(
    webhook_id: str,
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    webhook = db.query(Webhook).filter(Webhook.id == webhook_id, Webhook.org_id == tenant_id).first()
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found.")

    test_payload = '{"event": "ping", "data": {"test": true}}'
    now_ts = int(time.time())
    sig_header = generate_webhook_signature(webhook.secret_key, test_payload, now_ts)

    return {
        "status": "simulated_delivery",
        "url": webhook.url,
        "payload": test_payload,
        "headers": {
            "Content-Type": "application/json",
            "X-MemoryBrain-Signature": sig_header
        }
    }


@router.get(
    "",
    summary="List active webhooks",
    description="Lists all webhook URLs and active status for this organization."
)
def list_webhooks(
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db_session)
) -> List[Dict[str, Any]]:
    webhooks = db.query(Webhook).filter(Webhook.org_id == tenant_id).all()
    return [
        {
            "id": w.id,
            "url": w.url,
            "is_active": w.is_active,
            "created_at": w.created_at.isoformat() if w.created_at else None
        }
        for w in webhooks
    ]
