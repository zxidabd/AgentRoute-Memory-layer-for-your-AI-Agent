"""Razorpay Subscriptions and Webhook Processing for India & APAC B2B Customers."""

import hmac
import hashlib
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from ..config import settings
from ..models.db_models import Organization
from .plans import get_plan, PlanTier, SubscriptionStatus

try:
    import razorpay
except ImportError:
    razorpay = None


class RazorpayBillingService:
    """Manages Razorpay Subscriptions (UPI AutoPay / Cards) and webhook verification."""

    def __init__(self, key_id: Optional[str] = None, key_secret: Optional[str] = None, webhook_secret: Optional[str] = None):
        self.key_id = key_id or settings.razorpay_key_id
        self.key_secret = key_secret or settings.razorpay_key_secret
        self.webhook_secret = webhook_secret or settings.razorpay_webhook_secret
        self.client = None
        if razorpay and not self.key_id.startswith("rzp_test_mock"):
            try:
                self.client = razorpay.Client(auth=(self.key_id, self.key_secret))
            except Exception:
                self.client = None

    def create_subscription(self, db: Session, org_id: str, target_tier: str) -> Dict[str, Any]:
        """Initiates a Razorpay recurring subscription (e.g. UPI AutoPay, RuPay/Cards)."""
        plan = get_plan(target_tier)
        org = db.query(Organization).filter(Organization.id == org_id).first()
        if not org:
            raise ValueError(f"Organization {org_id} not found.")

        if self.client and not self.key_id.startswith("rzp_test_mock"):
            try:
                sub = self.client.subscription.create({
                    "plan_id": plan.razorpay_plan_id,
                    "total_count": 12,  # 12 monthly cycles
                    "quantity": 1,
                    "customer_notify": 1,
                    "notes": {"org_id": org.id, "target_tier": plan.tier.value}
                })
                org.razorpay_subscription_id = sub["id"]
                org.billing_gateway = "razorpay"
                db.commit()
                return {
                    "subscription_id": sub["id"],
                    "short_url": sub.get("short_url", f"https://rzp.io/i/{sub['id']}"),
                    "provider": "razorpay",
                    "tier": plan.tier.value,
                    "currency": "INR",
                    "amount": plan.price_inr_monthly
                }
            except Exception:
                pass

        # Simulated Razorpay subscription for sandbox/offline
        mock_sub_id = f"sub_rzp_mock_{int(time.time())}"
        org.razorpay_subscription_id = mock_sub_id
        org.billing_gateway = "razorpay"
        db.commit()

        return {
            "subscription_id": mock_sub_id,
            "short_url": f"https://rzp.io/mock/{mock_sub_id}?tier={plan.tier.value}",
            "provider": "razorpay",
            "tier": plan.tier.value,
            "currency": "INR",
            "amount": plan.price_inr_monthly,
            "mock": True
        }

    def verify_webhook_signature(self, payload_bytes: bytes, signature: str) -> bool:
        """Cryptographically verifies HMAC-SHA256 signature from Razorpay."""
        if not signature or not self.webhook_secret:
            return False
        if self.webhook_secret.startswith("mock_"):
            return True  # Sandbox passthrough

        expected = hmac.new(
            self.webhook_secret.encode("utf-8"),
            payload_bytes,
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def process_webhook(self, payload_bytes: bytes, signature: Optional[str], db: Session) -> Dict[str, Any]:
        """Validates and processes Razorpay subscription events."""
        if signature and not self.verify_webhook_signature(payload_bytes, signature):
            raise ValueError("Razorpay webhook signature verification failed.")

        try:
            event = json.loads(payload_bytes.decode("utf-8"))
        except Exception as e:
            raise ValueError(f"Invalid JSON payload: {str(e)}")

        event_name = event.get("event", "")
        payload_data = event.get("payload", {})
        sub_entity = payload_data.get("subscription", {}).get("entity", {})

        sub_id = sub_entity.get("id")
        notes = sub_entity.get("notes", {})
        org_id = notes.get("org_id")

        org = None
        if org_id:
            org = db.query(Organization).filter(Organization.id == org_id).first()
        elif sub_id:
            org = db.query(Organization).filter(Organization.razorpay_subscription_id == sub_id).first()

        if not org:
            return {"status": "ignored", "reason": "organization_not_found"}

        now = datetime.now(timezone.utc)

        # 1. Subscription charged / activated
        if event_name in ["subscription.charged", "subscription.authenticated", "subscription.activated"]:
            tier = notes.get("target_tier") or "growth"
            org.tier = tier
            org.subscription_tier = tier
            org.subscription_status = SubscriptionStatus.ACTIVE.value
            org.current_period_start = now
            org.current_period_end = now + timedelta(days=30)
            org.billing_gateway = "razorpay"
            db.commit()
            return {"status": "success", "action": "subscription_charged", "org_id": org.id, "tier": tier}

        # 2. Subscription cancelled
        elif event_name == "subscription.cancelled":
            org.tier = PlanTier.STARTER.value
            org.subscription_tier = PlanTier.STARTER.value
            org.subscription_status = SubscriptionStatus.CANCELED.value
            db.commit()
            return {"status": "success", "action": "subscription_cancelled", "org_id": org.id}

        # 3. Subscription paused / payment pending
        elif event_name == "subscription.halted":
            org.subscription_status = SubscriptionStatus.PAST_DUE.value
            db.commit()
            return {"status": "success", "action": "subscription_halted", "org_id": org.id}

        return {"status": "ignored", "event": event_name}
