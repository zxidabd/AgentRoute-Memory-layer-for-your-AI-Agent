"""Stripe Billing integration: Checkout sessions, Customer Portal, and Webhook processing."""

import json
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from ..config import settings
from ..models.db_models import Organization
from .plans import get_plan, PlanTier, SubscriptionStatus

try:
    import stripe
    stripe.api_key = settings.stripe_secret_key
except ImportError:
    stripe = None


class StripeBillingService:
    """Manages Stripe customer lifecycle, checkout sessions, and webhook processing."""

    def __init__(self, secret_key: Optional[str] = None, webhook_secret: Optional[str] = None):
        self.secret_key = secret_key or settings.stripe_secret_key
        self.webhook_secret = webhook_secret or settings.stripe_webhook_secret
        if stripe:
            stripe.api_key = self.secret_key

    def create_checkout_session(
        self,
        db: Session,
        org_id: str,
        target_tier: str,
        success_url: Optional[str] = None,
        cancel_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """Creates a Stripe Checkout Session for upgrading plan tier."""
        plan = get_plan(target_tier)
        org = db.query(Organization).filter(Organization.id == org_id).first()
        if not org:
            raise ValueError(f"Organization {org_id} not found.")

        success = success_url or settings.billing_success_url
        cancel = cancel_url or settings.billing_cancel_url

        # If live stripe is available and configured with a real key
        if stripe and self.secret_key and not self.secret_key.startswith("sk_test_mock"):
            try:
                # Ensure customer exists
                customer_id = org.stripe_customer_id
                if not customer_id:
                    customer = stripe.Customer.create(
                        name=org.name,
                        metadata={"org_id": org.id}
                    )
                    customer_id = customer.id
                    org.stripe_customer_id = customer_id
                    db.commit()

                session = stripe.checkout.Session.create(
                    customer=customer_id,
                    payment_method_types=["card"],
                    line_items=[{
                        "price": plan.stripe_price_id,
                        "quantity": 1
                    }],
                    mode="subscription",
                    success_url=f"{success}&session_id={{CHECKOUT_SESSION_ID}}",
                    cancel_url=cancel,
                    metadata={"org_id": org.id, "target_tier": plan.tier.value}
                )
                return {
                    "checkout_url": session.url,
                    "session_id": session.id,
                    "provider": "stripe",
                    "tier": plan.tier.value
                }
            except Exception as e:
                # Fall through to simulated session if live call fails
                pass

        # Simulated sandbox checkout URL for offline local dev/testing
        session_id = f"cs_test_{org.id}_{int(time.time())}"
        mock_checkout_url = f"{success}?session_id={session_id}&tier={plan.tier.value}"
        return {
            "checkout_url": mock_checkout_url,
            "session_id": session_id,
            "provider": "stripe",
            "tier": plan.tier.value,
            "mock": True
        }

    def create_customer_portal(self, db: Session, org_id: str, return_url: Optional[str] = None) -> str:
        """Generates self-serve Stripe Customer Portal URL."""
        org = db.query(Organization).filter(Organization.id == org_id).first()
        if not org:
            raise ValueError("Organization not found.")

        ret_url = return_url or settings.billing_success_url
        if stripe and org.stripe_customer_id and not self.secret_key.startswith("sk_test_mock"):
            try:
                portal = stripe.billing_portal.Session.create(
                    customer=org.stripe_customer_id,
                    return_url=ret_url
                )
                return portal.url
            except Exception:
                pass

        return f"http://localhost:8000/dashboard?portal_simulated=true&org_id={org_id}"

    def process_webhook(self, payload_bytes: bytes, sig_header: Optional[str], db: Session) -> Dict[str, Any]:
        """Validates and processes Stripe webhook events."""
        event = None

        # Verify signature if live
        if stripe and sig_header and self.webhook_secret and not self.webhook_secret.startswith("whsec_mock"):
            try:
                event = stripe.Webhook.construct_event(
                    payload_bytes, sig_header, self.webhook_secret
                )
            except Exception as e:
                raise ValueError(f"Stripe webhook signature verification failed: {str(e)}")
        else:
            # Parse raw JSON for test/mock modes
            try:
                event = json.loads(payload_bytes.decode("utf-8"))
            except Exception as e:
                raise ValueError(f"Invalid JSON payload: {str(e)}")

        event_type = event.get("type", "")
        data_object = event.get("data", {}).get("object", {})

        return self._dispatch_event(event_type, data_object, db)

    def _dispatch_event(self, event_type: str, data: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """Dispatches event types to business logic."""
        now = datetime.now(timezone.utc)

        # 1. Subscription created or updated
        if event_type in ["customer.subscription.created", "customer.subscription.updated"]:
            sub_id = data.get("id")
            customer_id = data.get("customer")
            status = data.get("status", "active")
            items = data.get("items", {}).get("data", [])
            price_id = items[0].get("price", {}).get("id") if items else None
            metadata = data.get("metadata", {})
            org_id = metadata.get("org_id")

            # Determine tier
            tier = metadata.get("target_tier") or "growth"
            if price_id and "scale" in price_id.lower():
                tier = PlanTier.SCALE.value
            elif price_id and "enterprise" in price_id.lower():
                tier = PlanTier.ENTERPRISE.value

            period_start = datetime.fromtimestamp(data.get("current_period_start", int(time.time())), tz=timezone.utc)
            period_end = datetime.fromtimestamp(data.get("current_period_end", int(time.time()) + 2592000), tz=timezone.utc)

            # Query organization
            org = None
            if org_id:
                org = db.query(Organization).filter(Organization.id == org_id).first()
            elif customer_id:
                org = db.query(Organization).filter(Organization.stripe_customer_id == customer_id).first()

            if org:
                org.tier = tier
                org.subscription_tier = tier
                org.subscription_status = status
                org.stripe_subscription_id = sub_id
                org.current_period_start = period_start
                org.current_period_end = period_end
                org.billing_gateway = "stripe"
                db.commit()
                return {"status": "success", "action": "subscription_updated", "org_id": org.id, "tier": tier}

        # 2. Subscription deleted / canceled
        elif event_type == "customer.subscription.deleted":
            customer_id = data.get("customer")
            org = db.query(Organization).filter(Organization.stripe_customer_id == customer_id).first()
            if org:
                org.tier = PlanTier.STARTER.value
                org.subscription_tier = PlanTier.STARTER.value
                org.subscription_status = SubscriptionStatus.CANCELED.value
                db.commit()
                return {"status": "success", "action": "subscription_canceled", "org_id": org.id}

        # 3. Invoice payment succeeded
        elif event_type == "invoice.payment_succeeded":
            customer_id = data.get("customer")
            org = db.query(Organization).filter(Organization.stripe_customer_id == customer_id).first()
            if org:
                org.subscription_status = SubscriptionStatus.ACTIVE.value
                db.commit()
                return {"status": "success", "action": "payment_succeeded", "org_id": org.id}

        # 4. Invoice payment failed
        elif event_type == "invoice.payment_failed":
            customer_id = data.get("customer")
            org = db.query(Organization).filter(Organization.stripe_customer_id == customer_id).first()
            if org:
                org.subscription_status = SubscriptionStatus.PAST_DUE.value
                db.commit()
                return {"status": "success", "action": "payment_failed", "org_id": org.id}

        return {"status": "ignored", "event_type": event_type}
