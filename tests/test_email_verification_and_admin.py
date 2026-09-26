"""Tests for Email Verification Tokens, Contact/Support Desk, and Superuser Admin Controls."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from agent_memory.api.server import app
from agent_memory.database import get_db_session
from agent_memory.models.db_models import UserAccount, EmailVerificationToken, ContactMessage
from agent_memory.auth.security import hash_email_token
from agent_memory.config import settings

settings.environment = "testing"
client = TestClient(app)


def test_email_verification_and_admin_suite():
    # 1. Signup with automatic 3-day trial and 24h verification token
    import secrets
    signup_email = f"tester_{secrets.token_hex(4)}@example.com"
    signup_pw = "StrongP@ssw0rd123"
    res = client.post("/v1/auth/signup", json={
        "name": "Sarah Connor",
        "email": signup_email,
        "password": signup_pw
    })
    assert res.status_code == 200, f"Signup failed: {res.text}"
    data = res.json()
    assert data["status"] == "pending_verification"
    assert data["subscription_status"] == "trialing"
    assert data["plan_tier"] == "free_trial"
    assert "trial_ends_at" in data

    # 2. Check token in DB
    db = next(get_db_session())
    user = db.query(UserAccount).filter(UserAccount.email == signup_email).first()
    assert user is not None
    assert user.is_verified is False

    tok_rec = db.query(EmailVerificationToken).filter(EmailVerificationToken.user_id == user.id).first()
    assert tok_rec is not None
    assert tok_rec.consumed is False

    # 3. Verify using OTP code
    otp = user.verification_code
    res_verify = client.post("/v1/auth/verify-email", json={
        "email": signup_email,
        "code": otp
    })
    assert res_verify.status_code == 200, f"Verification failed: {res_verify.text}"
    v_data = res_verify.json()
    assert v_data["status"] == "verified"
    assert "access_token" in v_data
    assert "mb_refresh_token" in res_verify.cookies

    # 4. Contact & Support Submission
    res_contact = client.post("/v1/contact", json={
        "name": "Sarah Connor",
        "email": signup_email,
        "subject": "Inquiry about multi-agent memory indexing",
        "message": "We have 15 agent workers needing sub-25ms hybrid context retrieval."
    })
    assert res_contact.status_code == 200
    c_data = res_contact.json()
    assert c_data["status"] == "success"
    assert "ticket_id" in c_data

    # 5. Superuser Admin Controls
    admin_headers = {"x-user-email": "abdullahzaid509@gmail.com"}

    # 5a. Admin Stats
    res_stats = client.get("/v1/admin/stats", headers=admin_headers)
    assert res_stats.status_code == 200
    s_data = res_stats.json()
    assert "kpis" in s_data
    assert "total_platform_revenue" in s_data["kpis"]

    # 5b. Search Users
    res_users = client.get("/v1/admin/users?query=Sarah", headers=admin_headers)
    assert res_users.status_code == 200
    u_list = res_users.json()
    assert len(u_list) >= 1
    sarah = next(u for u in u_list if u["email"] == signup_email)
    assert sarah["subscription_status"] == "trialing"

    # 5c. Plan Override to Pro
    res_override = client.post(f"/v1/admin/users/{sarah['id']}/plan", headers=admin_headers, json={
        "plan_tier": "pro"
    })
    assert res_override.status_code == 200
    assert res_override.json()["plan_tier"] == "pro"

    # 5d. Trial Extension (+7 days)
    res_extend = client.post(f"/v1/admin/users/{sarah['id']}/trial", headers=admin_headers, json={
        "days": 7
    })
    assert res_extend.status_code == 200
    assert res_extend.json()["days_added"] == 7

    # 5e. Reset Demo Payments
    res_reset = client.post("/v1/admin/reset-demo-payments", headers=admin_headers)
    assert res_reset.status_code == 200

    print("test_email_verification_and_admin_suite passed [SUCCESS]")


if __name__ == "__main__":
    test_email_verification_and_admin_suite()
