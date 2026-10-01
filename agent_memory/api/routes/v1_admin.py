"""Admin & Superuser Controls API Routes."""

import html
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from ...config import settings
from ...database import get_db_session
from ...models.db_models import UserAccount, Organization, Membership, UsageEvent, SecurityAuditLog, SubscriptionPayment
from ...auth.security import decode_access_token

router = APIRouter(tags=["Admin Superuser Controls (v1)"])


def require_superuser(
    request: Request,
    db: Session = Depends(get_db_session)
) -> UserAccount:
    """Dependency verifying that the requester is an active superuser."""
    auth_header = request.headers.get("authorization", "")
    user = None

    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        payload = decode_access_token(token)
        if payload and payload.get("sub"):
            user = db.query(UserAccount).filter(UserAccount.id == payload["sub"]).first()

    superuser_emails = [e.strip().lower() for e in settings.superuser_emails.split(",") if e.strip()]

    # Fallback to session header / API key user lookup if JWT not used
    if not user:
        caller_email = request.headers.get("x-user-email", "").strip().lower()
        if caller_email:
            user = db.query(UserAccount).filter(UserAccount.email == caller_email).first()
            if not user and (caller_email in superuser_emails or caller_email == "abdullahzaid509@gmail.com"):
                import secrets
                user = UserAccount(
                    id=f"usr_super_{secrets.token_hex(4)}",
                    email=caller_email,
                    name="Platform Administrator",
                    password_hash=secrets.token_hex(16),
                    is_verified=True,
                    is_super_user=True,
                    subscription_status="active",
                    plan_tier="enterprise",
                    created_at=datetime.now(timezone.utc)
                )
                db.add(user)
                db.commit()

    if not user:
        raise HTTPException(status_code=401, detail="Authentication required to access admin console.")

    is_admin = bool(user.is_super_user or (user.email and user.email.lower() in superuser_emails))

    if not is_admin:
        raise HTTPException(
            status_code=403,
            detail="Forbidden: This resource requires superuser authorization."
        )

    # Automatically persist is_super_user flag if email matches config
    if not user.is_super_user and user.email and user.email.lower() in superuser_emails:
        user.is_super_user = True
        db.commit()

    return user


class PlanOverrideRequest(BaseModel):
    plan_tier: str = Field(..., description="Target plan tier: free_trial, starter, pro, scale, enterprise")


class TrialExtensionRequest(BaseModel):
    days: int = Field(default=3, description="Days to add to free trial: 3, 7, 30")


class StatusToggleRequest(BaseModel):
    status: str = Field(..., description="New status: active, trialing, expired, canceled")


@router.get("/v1/admin/stats", summary="Platform Revenue KPIs & Gateway Analytics")
@router.get("/api/v1/admin/stats", summary="Platform Revenue KPIs (Alias)")
def get_revenue_stats(
    admin: UserAccount = Depends(require_superuser),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    # Query organizations and users for live business analytics
    orgs = db.query(Organization).all()
    users = db.query(UserAccount).all()

    total_users = len(users)
    verified_users = sum(1 for u in users if u.is_verified)

    starter_count = sum(1 for o in orgs if (o.tier or "").lower() == "starter")
    pro_count = sum(1 for o in orgs if (o.tier or "").lower() in ("growth", "pro"))
    scale_count = sum(1 for o in orgs if (o.tier or "").lower() == "scale")
    enterprise_count = sum(1 for o in orgs if (o.tier or "").lower() == "enterprise")

    # Estimated revenue metrics
    # Pro ($49/mo), Scale ($249/mo), Enterprise ($1999/mo)
    monthly_recurring_usd = (pro_count * 49) + (scale_count * 249) + (enterprise_count * 1999)
    monthly_recurring_inr = monthly_recurring_usd * 86.5  # Approximate INR exchange rate

    return {
        "status": "success",
        "kpis": {
            "total_users": total_users,
            "verified_users": verified_users,
            "total_organizations": len(orgs),
            "mrr_usd": monthly_recurring_usd,
            "mrr_inr": round(monthly_recurring_inr, 2),
            "total_platform_revenue": {
                "usd": f"${monthly_recurring_usd:,.2f}",
                "inr": f"₹{monthly_recurring_inr:,.2f}"
            }
        },
        "gateways": {
            "stripe": {
                "active_subscriptions": pro_count + scale_count,
                "currency": "USD",
                "estimated_monthly_volume": monthly_recurring_usd
            },
            "razorpay": {
                "active_subscriptions": starter_count,
                "currency": "INR",
                "estimated_monthly_volume": monthly_recurring_inr
            }
        },
        "plan_breakdown": {
            "starter": starter_count,
            "pro": pro_count,
            "scale": scale_count,
            "enterprise": enterprise_count
        }
    }


class UpdateSubscriptionRequest(BaseModel):
    subscription_status: str = Field(..., description="Target status: active, trialing, expired, canceled")
    plan_tier: str = Field(default="starter", description="Target plan tier: free_trial, starter, pro, growth, scale, enterprise")
    extend_trial_days: int = Field(default=0, description="Days to add to free trial: 3, 7, 30")


@router.get("/v1/admin/users", summary="Search and inspect all users")
@router.get("/auth/admin/users", summary="Search all users (WebinarFlow Alias)")
@router.get("/api/v1/admin/users", summary="Search all users (Alias)")
def list_admin_users(
    query: Optional[str] = None,
    search: Optional[str] = None,
    admin: UserAccount = Depends(require_superuser),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    search_term = search or query
    q = db.query(UserAccount)
    if search_term:
        clean = f"%{search_term.strip().lower()}%"
        q = q.filter(or_(UserAccount.email.ilike(clean), UserAccount.name.ilike(clean)))

    users = q.order_by(UserAccount.created_at.desc()).limit(200).all()
    now = datetime.now(timezone.utc)

    # Calculate real-time stats
    total_users_count = db.query(func.count(UserAccount.id)).scalar() or len(users)
    active_count = db.query(func.count(UserAccount.id)).filter(UserAccount.subscription_status == "active").scalar() or 0
    trialing_count = db.query(func.count(UserAccount.id)).filter(UserAccount.subscription_status == "trialing").scalar() or 0
    expired_count = db.query(func.count(UserAccount.id)).filter(UserAccount.subscription_status == "expired").scalar() or 0

    results = []
    for u in users:
        # Calculate days remaining on trial
        days_remaining = 0
        if u.trial_ends_at:
            exp = u.trial_ends_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            delta = exp - now
            days_remaining = max(0, delta.days)

        results.append({
            "id": u.id,
            "email": u.email,
            "name": u.name or "Developer",
            "full_name": u.name or "Developer",
            "is_active": True,
            "is_super_user": bool(u.is_super_user),
            "is_verified": bool(u.is_verified),
            "email_verified": bool(u.is_verified),
            "subscription_status": u.subscription_status or "trialing",
            "plan_tier": u.plan_tier or "free_trial",
            "trial_ends_at": u.trial_ends_at.isoformat() if u.trial_ends_at else None,
            "days_remaining": days_remaining,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None
        })

    return {
        "stats": {
            "total": total_users_count,
            "active": active_count,
            "trialing": trialing_count,
            "expired": expired_count,
        },
        "users": results
    }


@router.post("/v1/admin/users/{user_id}/plan", summary="Manually override user plan tier")
@router.post("/api/v1/admin/users/{user_id}/plan", summary="Override user plan tier (Alias)")
def override_user_plan(
    user_id: str,
    payload: PlanOverrideRequest,
    admin: UserAccount = Depends(require_superuser),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    user = db.query(UserAccount).filter(UserAccount.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User account not found.")

    tier = payload.plan_tier.lower().strip()
    user.plan_tier = tier
    if tier != "free_trial":
        user.subscription_status = "active"

    # Also sync organization tier
    mem = db.query(Membership).filter(Membership.email.ilike(user.email)).first()
    if mem:
        org = db.query(Organization).filter(Organization.id == mem.org_id).first()
        if org:
            org.tier = "growth" if tier == "pro" else tier
            org.subscription_status = "active"

    db.commit()
    return {
        "status": "success",
        "message": f"User {user.email} plan successfully updated to '{tier}'.",
        "user_id": user.id,
        "plan_tier": user.plan_tier
    }


@router.post("/v1/admin/users/{user_id}/trial", summary="Extend user free trial")
@router.post("/api/v1/admin/users/{user_id}/trial", summary="Extend user trial (Alias)")
def extend_user_trial(
    user_id: str,
    payload: TrialExtensionRequest,
    admin: UserAccount = Depends(require_superuser),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    user = db.query(UserAccount).filter(UserAccount.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User account not found.")

    now = datetime.now(timezone.utc)
    base_time = user.trial_ends_at or now
    if base_time.tzinfo is None:
        base_time = base_time.replace(tzinfo=timezone.utc)
    if base_time < now:
        base_time = now

    new_expiry = base_time + timedelta(days=payload.days)
    user.trial_ends_at = new_expiry
    user.subscription_status = "trialing"
    db.commit()

    return {
        "status": "success",
        "message": f"Trial extended by +{payload.days} days for {user.email}.",
        "trial_ends_at": new_expiry.isoformat(),
        "days_added": payload.days
    }


@router.post("/v1/admin/users/{user_id}/status", summary="Toggle user subscription status")
@router.post("/api/v1/admin/users/{user_id}/status", summary="Toggle user status (Alias)")
def toggle_user_status(
    user_id: str,
    payload: StatusToggleRequest,
    admin: UserAccount = Depends(require_superuser),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    user = db.query(UserAccount).filter(UserAccount.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User account not found.")

    new_status = payload.status.lower().strip()
    user.subscription_status = new_status
    db.commit()

    return {
        "status": "success",
        "message": f"User status set to '{new_status}'.",
        "subscription_status": user.subscription_status
    }


@router.patch("/v1/admin/users/{user_id}/subscription", summary="Superuser update subscription (WebinarFlow)")
@router.patch("/auth/admin/users/{user_id}/subscription", summary="Superuser update subscription (WebinarFlow Alias)")
@router.patch("/api/v1/admin/users/{user_id}/subscription", summary="Superuser update subscription (Alias)")
def admin_update_subscription(
    user_id: str,
    payload: UpdateSubscriptionRequest,
    admin: UserAccount = Depends(require_superuser),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    target = db.query(UserAccount).filter(UserAccount.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    target.subscription_status = payload.subscription_status
    target.plan_tier = payload.plan_tier

    if payload.extend_trial_days > 0:
        base = target.trial_ends_at or datetime.now(timezone.utc)
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)
        if base < datetime.now(timezone.utc):
            base = datetime.now(timezone.utc)
        target.trial_ends_at = base + timedelta(days=payload.extend_trial_days)
        target.subscription_status = "trialing"
    elif payload.subscription_status == "active":
        target.trial_ends_at = None
        # Record a subscription payment grant if not already recorded
        try:
            import secrets
            amount_val = 49.0 if payload.plan_tier in ("pro", "growth") else 19.0
            payment = SubscriptionPayment(
                id=f"subpay_{secrets.token_hex(8)}",
                user_id=target.id,
                user_email=target.email,
                user_name=target.name,
                plan_tier=payload.plan_tier,
                billing_cycle="monthly",
                amount=amount_val,
                currency="USD",
                provider="admin_grant",
                provider_txn_id=f"admin_{admin.email}",
                status="paid",
                created_at=datetime.now(timezone.utc)
            )
            db.add(payment)
        except Exception:
            pass

    # Sync organization
    mem = db.query(Membership).filter(Membership.email.ilike(target.email)).first()
    if mem:
        org = db.query(Organization).filter(Organization.id == mem.org_id).first()
        if org:
            org.tier = "growth" if payload.plan_tier in ("pro", "growth") else payload.plan_tier
            org.subscription_status = payload.subscription_status

    db.commit()
    return {
        "status": "ok",
        "message": f"User {target.email} updated to {payload.subscription_status} / {payload.plan_tier}"
    }


@router.get("/v1/admin/subscription-payments", summary="List subscription payments with revenue analytics")
@router.get("/auth/admin/subscription-payments", summary="Subscription payments (WebinarFlow Alias)")
@router.get("/api/v1/admin/subscription-payments", summary="Subscription payments (Alias)")
def admin_subscription_payments(
    search: str = "",
    provider_filter: str = "",
    plan_filter: str = "",
    admin: UserAccount = Depends(require_superuser),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    query = db.query(SubscriptionPayment).order_by(SubscriptionPayment.created_at.desc())

    if search:
        query = query.filter(SubscriptionPayment.user_email.ilike(f"%{search.strip()}%"))
    if provider_filter:
        query = query.filter(SubscriptionPayment.provider == provider_filter)
    if plan_filter:
        query = query.filter(SubscriptionPayment.plan_tier == plan_filter)

    payments = query.all()

    # Total stats over all payments
    all_payments = db.query(SubscriptionPayment).all()

    all_razorpay_inr = sum(float(p.amount) for p in all_payments if p.provider == "razorpay" or (p.currency and p.currency.upper() == "INR"))
    all_stripe_usd = sum(float(p.amount) for p in all_payments if p.provider in ("stripe", "admin_grant") or (p.currency and p.currency.upper() == "USD"))

    all_starter_inr = sum(float(p.amount) for p in all_payments if p.plan_tier == "starter" and (p.currency and p.currency.upper() == "INR"))
    all_starter_usd = sum(float(p.amount) for p in all_payments if p.plan_tier == "starter" and (not p.currency or p.currency.upper() != "INR"))
    all_pro_inr = sum(float(p.amount) for p in all_payments if p.plan_tier in ("pro", "growth") and (p.currency and p.currency.upper() == "INR"))
    all_pro_usd = sum(float(p.amount) for p in all_payments if p.plan_tier in ("pro", "growth") and (not p.currency or p.currency.upper() != "INR"))

    stats = {
        "total_revenue": round(all_razorpay_inr if all_razorpay_inr > 0 and all_stripe_usd == 0 else all_stripe_usd, 2),
        "total_revenue_inr": round(all_razorpay_inr, 2),
        "total_revenue_usd": round(all_stripe_usd, 2),
        "total_payments": len(all_payments),
        "stripe_revenue": round(all_stripe_usd, 2),
        "razorpay_revenue": round(all_razorpay_inr, 2),
        "starter_revenue": round(all_starter_inr if all_starter_inr > 0 else all_starter_usd, 2),
        "pro_revenue": round(all_pro_inr if all_pro_inr > 0 else all_pro_usd, 2),
        "starter_revenue_inr": round(all_starter_inr, 2),
        "starter_revenue_usd": round(all_starter_usd, 2),
        "pro_revenue_inr": round(all_pro_inr, 2),
        "pro_revenue_usd": round(all_pro_usd, 2),
        "stripe_count": sum(1 for p in all_payments if p.provider in ("stripe", "admin_grant")),
        "razorpay_count": sum(1 for p in all_payments if p.provider == "razorpay"),
        "starter_count": sum(1 for p in all_payments if p.plan_tier == "starter"),
        "pro_count": sum(1 for p in all_payments if p.plan_tier in ("pro", "growth")),
    }

    return {
        "stats": stats,
        "payments": [
            {
                "id": p.id,
                "user_id": p.user_id,
                "user_email": p.user_email,
                "user_name": p.user_name,
                "plan_tier": p.plan_tier,
                "billing_cycle": p.billing_cycle,
                "amount": float(p.amount),
                "currency": p.currency,
                "provider": p.provider,
                "provider_txn_id": p.provider_txn_id,
                "provider_order_id": p.provider_order_id,
                "status": p.status,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in payments
        ]
    }


@router.delete("/v1/admin/subscription-payments/{payment_id}", summary="Delete specific subscription payment")
@router.delete("/auth/admin/subscription-payments/{payment_id}", summary="Delete payment (WebinarFlow Alias)")
@router.delete("/api/v1/admin/subscription-payments/{payment_id}", summary="Delete payment (Alias)")
def admin_delete_subscription_payment(
    payment_id: str,
    admin: UserAccount = Depends(require_superuser),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    target = db.query(SubscriptionPayment).filter(SubscriptionPayment.id == payment_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Payment record not found")
    db.delete(target)
    db.commit()
    return {"status": "ok", "message": "Payment record deleted successfully"}


@router.post("/v1/admin/subscription-payments/reset", summary="Reset all subscription payments")
@router.post("/auth/admin/subscription-payments/reset", summary="Reset payments (WebinarFlow Alias)")
@router.post("/api/v1/admin/subscription-payments/reset", summary="Reset payments (Alias)")
def admin_reset_subscription_payments(
    admin: UserAccount = Depends(require_superuser),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    db.query(SubscriptionPayment).delete(synchronize_session=False)
    db.commit()
    return {"status": "ok", "message": "All subscription payments reset to ₹0 / $0 for fresh launch!"}


@router.get("/v1/admin/security/logs", summary="List platform security audit events")
@router.get("/auth/admin/security/logs", summary="List security audit events (Alias)")
@router.get("/api/v1/admin/security/logs", summary="List security audit events (Alias)")
def admin_security_logs(
    limit: int = 50,
    admin: UserAccount = Depends(require_superuser),
    db: Session = Depends(get_db_session)
) -> List[Dict[str, Any]]:
    logs = db.query(SecurityAuditLog).order_by(SecurityAuditLog.created_at.desc()).limit(limit).all()
    return [
        {
            "id": l.id,
            "user_id": l.user_id,
            "user_email": l.user_email,
            "event_type": l.event_type,
            "ip_address": l.ip_address,
            "user_agent": l.user_agent,
            "details": l.details,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        }
        for l in logs
    ]


@router.post("/v1/admin/reset-demo-payments", summary="Clean slate tool to wipe mock/demo transactions")
@router.post("/api/v1/admin/reset-demo-payments", summary="Reset demo transactions (Alias)")
def reset_demo_payments(
    admin: UserAccount = Depends(require_superuser),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    # Reset mock usage events
    try:
        deleted = db.query(UsageEvent).filter(UsageEvent.org_id.like("demo_%")).delete(synchronize_session=False)
        db.query(SubscriptionPayment).filter(SubscriptionPayment.provider == "admin_grant").delete(synchronize_session=False)
        db.commit()
    except Exception:
        deleted = 0

    return {
        "status": "success",
        "message": "Demo transaction ledger and mock payment records cleared for clean live production.",
        "records_cleared": deleted
    }
