"""End-to-End Test for Google OAuth authentication endpoints."""

import base64
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from agent_memory.api.server import app
from agent_memory.database import get_db_session
from agent_memory.models.db_models import UserAccount, Organization, Project, Membership

client = TestClient(app)

def test_google_auth_flow():
    # 1. Testing GET /v1/auth/config
    res = client.get("/v1/auth/config")
    assert res.status_code == 200, f"Config failed: {res.text}"
    config = res.json()
    assert "google_client_id" in config

    # 2. Testing POST /v1/auth/google (Dev/Demo Direct Auth)
    demo_email = "test.google.dev@example.com"
    demo_name = "Alex GoogleDev"
    res = client.post("/v1/auth/google", json={
        "email": demo_email,
        "name": demo_name
    })
    assert res.status_code == 200, f"Google auth failed: {res.text}"
    auth_data = res.json()
    assert auth_data["status"] == "authenticated"
    assert auth_data["auth_type"] == "google"
    assert auth_data["user"]["email"] == demo_email
    assert auth_data["user"]["name"] == demo_name
    assert auth_data["api_key"].startswith("mb_")
    assert auth_data["project_id"] is not None

    # 3. Testing POST /v1/auth/google (Simulated JWT ID Token)
    jwt_payload = {
        "iss": "https://accounts.google.com",
        "sub": "109876543210987654321",
        "email": "sarah.connor@gmail.com",
        "email_verified": True,
        "name": "Sarah Connor",
        "picture": "https://lh3.googleusercontent.com/a/default-user"
    }
    header_b64 = base64.urlsafe_b64encode(json.dumps({"alg": "RS256", "typ": "JWT"}).encode()).decode().rstrip("=")
    payload_b64 = base64.urlsafe_b64encode(json.dumps(jwt_payload).encode()).decode().rstrip("=")
    fake_jwt = f"{header_b64}.{payload_b64}.fake_signature_bytes_here"

    res = client.post("/v1/auth/google", json={"credential": fake_jwt})
    assert res.status_code == 200, f"Simulated JWT failed: {res.text}"
    jwt_auth = res.json()
    assert jwt_auth["status"] == "authenticated"
    assert jwt_auth["user"]["email"] == "sarah.connor@gmail.com"
    assert jwt_auth["user"]["name"] == "Sarah Connor"
    assert jwt_auth["user"]["picture"] == "https://lh3.googleusercontent.com/a/default-user"

    # 4. Verify Database Records
    db = next(get_db_session())
    try:
        user1 = db.query(UserAccount).filter(UserAccount.email == demo_email).first()
        assert user1 is not None, "UserAccount not found in DB"
        assert user1.is_verified is True, "UserAccount should be pre-verified via Google"

        user2 = db.query(UserAccount).filter(UserAccount.email == "sarah.connor@gmail.com").first()
        assert user2 is not None, "JWT UserAccount not found in DB"
        assert user2.is_verified is True, "JWT UserAccount should be pre-verified"

        mem = db.query(Membership).filter(Membership.email == "sarah.connor@gmail.com").first()
        assert mem is not None, "Membership not found in DB"
        org = db.query(Organization).filter(Organization.id == mem.org_id).first()
        assert org is not None, "Organization not found in DB"
    finally:
        db.close()

if __name__ == "__main__":
    test_google_auth_flow()
    print("test_google_auth passed [SUCCESS]")
