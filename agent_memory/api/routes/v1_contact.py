"""Contact & Support API Routes for visitors and authenticated users."""

import html
import uuid
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, EmailStr
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from ...config import settings
from ...database import get_db_session
from ...models.db_models import ContactMessage
from ...services.email_service import EmailService

router = APIRouter(tags=["Contact & Support (v1)"])


class ContactRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, description="Sender's full name")
    email: EmailStr = Field(..., description="Sender's contact email")
    subject: str = Field(..., min_length=3, max_length=200, description="Inquiry subject")
    message: str = Field(..., min_length=10, max_length=5000, description="Detailed inquiry or ticket message")
    user_id: Optional[str] = Field(default=None, description="Optional authenticated user ID")


@router.post("/v1/contact", summary="Submit Support Inquiry or Contact Form")
@router.post("/api/v1/contact", summary="Submit Support Inquiry (Alias)")
def submit_contact_form(
    payload: ContactRequest,
    request: Request,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    # 1. Sanitize & HTML escape inputs to prevent XSS
    safe_name = html.escape(payload.name.strip())
    safe_email = payload.email.strip().lower()
    safe_subject = html.escape(payload.subject.strip())
    safe_message = html.escape(payload.message.strip())

    client_ip = request.client.host if request.client else None

    # 2. Persist to database ledger
    msg_id = f"cnt_{uuid.uuid4().hex[:12]}"
    record = ContactMessage(
        id=msg_id,
        name=safe_name,
        email=safe_email,
        subject=safe_subject,
        message=safe_message,
        user_id=payload.user_id,
        ip_address=client_ip
    )
    db.add(record)
    db.commit()

    # 3. Dispatch alert to business support inbox
    try:
        EmailService.send_contact_alert(
            name=safe_name,
            email=safe_email,
            subject=safe_subject,
            message=safe_message
        )
    except Exception:
        pass

    # 4. Dispatch automated acknowledgment to the visitor/user
    try:
        EmailService.send_contact_acknowledgment(
            name=safe_name,
            email=safe_email,
            subject=safe_subject
        )
    except Exception:
        pass

    return {
        "status": "success",
        "ticket_id": msg_id,
        "message": "Thank you! Your message has been received and our engineering team will respond shortly."
    }
