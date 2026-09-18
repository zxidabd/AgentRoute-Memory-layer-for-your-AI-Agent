"""Security test verifying that login without signup, wrong password, or unverified email is blocked."""

from fastapi.testclient import TestClient
from agent_memory.api.server import app
from agent_memory.database import get_db_session
from agent_memory.models.db_models import UserAccount, Organization, Project, Membership
from agent_memory.api.routes.v1_workspaces import hash_password
from datetime import datetime, timezone

client = TestClient(app)

def test_login_security_gates():
    db = next(get_db_session())
    try:
        # Create a verified test user and an unverified test user
        now = datetime.now(timezone.utc)
        verified_email = "verified.user@company.com"
        unverified_email = "unverified.user@company.com"

        # Cleanup prior test data
        db.query(UserAccount).filter(UserAccount.email.in_([verified_email, unverified_email])).delete(synchronize_session=False)
        db.commit()

        u_verified = UserAccount(
            id="usr_test_verified_sec",
            email=verified_email,
            name="Verified Test",
            password_hash=hash_password("Secret123!"),
            is_verified=True,
            created_at=now,
            updated_at=now
        )
        db.add(u_verified)

        org = Organization(id="org_sec_test", name="Security Test Org", slug="sec-test", tier="starter")
        db.add(org)
        proj = Project(id="proj_sec_test", org_id=org.id, name="Agent", environment="prod")
        db.add(proj)
        mem = Membership(id="mem_sec_test", org_id=org.id, clerk_user_id=u_verified.id, email=verified_email, role="owner")
        db.add(mem)

        u_unverified = UserAccount(
            id="usr_test_unverified_sec",
            email=unverified_email,
            name="Unverified Test",
            password_hash=hash_password("Secret123!"),
            is_verified=False,
            verification_code="654321",
            created_at=now,
            updated_at=now
        )
        db.add(u_unverified)
        db.commit()

        # 1. Blank login attempt must be rejected (400)
        res = client.post("/v1/auth/login", json={})
        assert res.status_code == 400, f"Expected 400 on empty login, got {res.status_code}"

        # 2. Non-existent email must NOT create a workspace, must return 404
        fake_email = "random_intruder@notregistered.com"
        res = client.post("/v1/auth/login", json={"email": fake_email, "password": "anyPassword123"})
        assert res.status_code == 404, f"Expected 404 on unregistered email, got {res.status_code}: {res.text}"
        # Ensure intruder did NOT get created in DB
        check_intruder = db.query(UserAccount).filter(UserAccount.email == fake_email).first()
        assert check_intruder is None, "Intruder should not exist in database"

        # 3. Existing email with NO password must be rejected (400)
        res = client.post("/v1/auth/login", json={"email": verified_email})
        assert res.status_code == 400, f"Expected 400 on missing password, got {res.status_code}"

        # 4. Existing email with WRONG password must be rejected (401)
        res = client.post("/v1/auth/login", json={"email": verified_email, "password": "WrongPassword!"})
        assert res.status_code == 401, f"Expected 401 on wrong password, got {res.status_code}"

        # 5. Unverified email with correct password must return status="unverified"
        res = client.post("/v1/auth/login", json={"email": unverified_email, "password": "Secret123!"})
        assert res.status_code == 200
        data = res.json()
        assert data.get("status") == "unverified", f"Expected unverified status, got {data}"
        assert "api_key" not in data, "Unverified user must not receive an API key"

        # 6. Verified email with correct password must succeed and return API key
        res = client.post("/v1/auth/login", json={"email": verified_email, "password": "Secret123!"})
        assert res.status_code == 200
        data = res.json()
        assert data.get("status") == "authenticated"
        assert data.get("api_key", "").startswith("mb_")
        assert data.get("user", {}).get("email") == verified_email

    finally:
        db.close()

if __name__ == "__main__":
    test_login_security_gates()
    print("test_login_security_gates passed [SUCCESS]")
