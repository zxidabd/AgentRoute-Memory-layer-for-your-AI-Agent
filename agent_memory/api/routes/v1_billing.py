"""B2B Billing and Subscription API Routes."""

from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Header, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...database import get_db_session
from ..auth import get_current_tenant
from ...billing.plans import PLANS, get_plan, PlanTier
from ...billing.usage_tracker import UsageTracker
from ...billing.stripe_service import StripeBillingService
from ...billing.razorpay_service import RazorpayBillingService

router = APIRouter(prefix="/v1/billing", tags=["B2B Billing & Subscriptions (v1)"])

stripe_service = StripeBillingService()
razorpay_service = RazorpayBillingService()


class CheckoutRequest(BaseModel):
    tier: str = Field(..., description="Target tier: growth, scale, or enterprise")
    gateway: str = Field(default="stripe", description="Payment gateway: stripe or razorpay")
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


@router.get("/plans", summary="List all subscription tiers and pricing")
def list_plans() -> Dict[str, Any]:
    """Returns details for all available B2B subscription tiers."""
    return {
        "plans": {tier.value: plan.dict() for tier, plan in PLANS.items()}
    }


@router.get("/usage", summary="Get real-time organization usage and quota status")
def get_usage(
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Returns current billing cycle usage, quota percentages, and accrued overages."""
    return UsageTracker.get_monthly_usage(db, tenant_id)


@router.post("/checkout", summary="Initiate plan upgrade checkout session")
def create_checkout(
    payload: CheckoutRequest,
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Creates a Stripe or Razorpay checkout session for upgrading subscription tier."""
    if payload.gateway.lower() == "razorpay":
        return razorpay_service.create_subscription(db, tenant_id, payload.tier)
    else:
        return stripe_service.create_checkout_session(
            db, tenant_id, payload.tier, payload.success_url, payload.cancel_url
        )


@router.post("/portal", summary="Open Stripe Customer Self-Serve Billing Portal")
def get_customer_portal(
    return_url: Optional[str] = Query(None),
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Generates customer portal link to update payment methods and view past invoices."""
    portal_url = stripe_service.create_customer_portal(db, tenant_id, return_url)
    return {"portal_url": portal_url}


@router.post("/webhooks/stripe", include_in_schema=False)
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None, alias="Stripe-Signature"),
    db: Session = Depends(get_db_session)
):
    """Processes incoming Stripe billing and subscription lifecycle events."""
    payload = await request.body()
    try:
        result = stripe_service.process_webhook(payload, stripe_signature, db)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/webhooks/razorpay", include_in_schema=False)
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: Optional[str] = Header(None, alias="X-Razorpay-Signature"),
    db: Session = Depends(get_db_session)
):
    """Processes incoming Razorpay subscription lifecycle events."""
    payload = await request.body()
    try:
        result = razorpay_service.process_webhook(payload, x_razorpay_signature, db)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
