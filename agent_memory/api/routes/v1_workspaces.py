"""Workspaces, Projects, RBAC Team Management, and Auth API Routes."""

import uuid
import secrets
import hashlib
import hmac
import base64
import json
import logging
import httpx
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("agentroute.auth")
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, EmailStr
from fastapi import APIRouter, Depends, HTTPException, Request, Header, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from ...config import settings
from ...database import get_db_session
from ...models.db_models import Organization, Project, Membership, Invitation, APIKey, UserAccount, RefreshToken, EmailVerificationToken

from ...auth.rbac_middleware import (
    AuthContext,
    AppRole,
    get_auth_context,
    require_permission,
    check_last_owner_guard
)
from ...auth.api_key_service import APIKeyService
from ...auth.clerk_service import ClerkService
from ...services.email_service import EmailService
from ...auth.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_refresh_token,
    create_email_verification_token,
    hash_email_token
)


router = APIRouter(tags=["Workspaces & Team RBAC (v1)"])


# --- Schemas ---

class ProjectCreateRequest(BaseModel):
    name: str = Field(..., description="Project name, e.g. 'Customer-Support-Bot'")
    environment: str = Field(default="dev", description="Environment: dev, staging, prod")


class ProjectKeyCreateRequest(BaseModel):
    name: str = Field(..., description="Key label, e.g. 'Prod Ingestion Worker'")
    role: str = Field(default="developer", description="Assigned role: owner, developer, viewer")
    environment: Optional[str] = Field(default=None, description="Environment override (defaults to project's env)")
    expires_in_days: Optional[int] = Field(default=None, description="Optional key expiration in days")


class InviteCreateRequest(BaseModel):
    email: EmailStr = Field(..., description="Invitee's email address")
    role: str = Field(default="developer", description="Invitee's role: owner, developer, viewer")


class InviteAcceptRequest(BaseModel):
    clerk_user_id: str = Field(..., description="Clerk User ID of the accepting user")
    email: Optional[str] = Field(default=None, description="Email address")
    name: Optional[str] = Field(default=None, description="Full name")


class RoleUpdateRequest(BaseModel):
    role: str = Field(..., description="New role: owner, developer, viewer")



def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensures a datetime object is timezone-aware in UTC for safe comparison."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt




class SignupRequest(BaseModel):
    name: str = Field(..., description="Developer or founder full name")
    email: EmailStr = Field(..., description="Work email address")
    password: str = Field(..., min_length=8, description="Account password (minimum 8 characters)")
    organization_name: Optional[str] = Field(default=None, description="Company or workspace name")
    tier: str = Field(default="starter", description="starter, growth, scale, enterprise")


class VerifyEmailRequest(BaseModel):
    email: Optional[EmailStr] = Field(default=None, description="User email address")
    code: Optional[str] = Field(default=None, description="6-digit verification code")
    token: Optional[str] = Field(default=None, description="Cryptographic single-use verification token from email CTA")


class ResendCodeRequest(BaseModel):
    email: EmailStr = Field(..., description="User email address")


class ForgotPasswordRequest(BaseModel):
    email: EmailStr = Field(..., description="User email address")


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., description="Password reset token")
    new_password: str = Field(..., description="New account password")


class LoginRequest(BaseModel):
    email: Optional[str] = Field(default=None, description="Email address to log in")
    password: Optional[str] = Field(default=None, description="Account password")
    api_key: Optional[str] = Field(default=None, description="Active API key to log in")
    remember_me: bool = Field(default=False, description="Keep session persistent across browser restarts")


class GoogleAuthRequest(BaseModel):
    code: Optional[str] = Field(default=None, description="OAuth 2.0 authorization code from Google redirect")
    redirect_uri: Optional[str] = Field(default=None, description="Redirect URI used in Google consent flow")
    credential: Optional[str] = Field(default=None, description="Google ID Token JWT from Google Identity Services")
    email: Optional[str] = Field(default=None, description="Email directly provided or decoded")
    name: Optional[str] = Field(default=None, description="User full name from Google")
    picture: Optional[str] = Field(default=None, description="Avatar image URL from Google profile")


# --- Project Management Routes ---

@router.get("/v1/orgs/{org_id}/projects", summary="List projects for an organization")
def list_projects(
    org_id: str,
    context: AuthContext = Depends(require_permission("projects:read")),
    db: Session = Depends(get_db_session)
) -> List[Dict[str, Any]]:
    if context.org_id != org_id and context.role != AppRole.OWNER.value:
        raise HTTPException(status_code=403, detail="Cannot access projects of another organization.")

    projects = db.query(Project).filter(Project.org_id == org_id, Project.is_active == True).all()
    return [
        {
            "id": p.id,
            "org_id": p.org_id,
            "name": p.name,
            "environment": p.environment,
            "created_at": p.created_at.isoformat() if p.created_at else None
        }
        for p in projects
    ]


@router.post("/v1/orgs/{org_id}/projects", summary="Create a new project in an organization")
def create_project(
    org_id: str,
    payload: ProjectCreateRequest,
    context: AuthContext = Depends(require_permission("projects:manage")),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    if context.org_id != org_id:
        raise HTTPException(status_code=403, detail="Cannot create projects for another organization.")

    env = payload.environment.lower()
    if env not in ("dev", "staging", "prod"):
        raise HTTPException(status_code=400, detail="Environment must be one of: dev, staging, prod")

    # Check unique constraint (org_id, name, environment)
    existing = db.query(Project).filter(
        Project.org_id == org_id,
        Project.name == payload.name,
        Project.environment == env
    ).first()

    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Project with name '{payload.name}' and environment '{env}' already exists in this organization."
        )

    proj_id = f"proj_{uuid.uuid4().hex[:12]}"
    project = Project(
        id=proj_id,
        org_id=org_id,
        name=payload.name,
        environment=env,
        is_active=True,
        created_at=datetime.now(timezone.utc)
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    return {
        "id": project.id,
        "org_id": project.org_id,
        "name": project.name,
        "environment": project.environment,
        "created_at": project.created_at.isoformat()
    }


@router.delete("/v1/orgs/{org_id}/projects/{project_id}", summary="Delete a project")
def delete_project(
    org_id: str,
    project_id: str,
    context: AuthContext = Depends(require_permission("projects:manage")),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    if context.org_id != org_id:
        raise HTTPException(status_code=403, detail="Cannot modify projects of another organization.")

    project = db.query(Project).filter(Project.id == project_id, Project.org_id == org_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    db.delete(project)
    db.commit()
    return {"status": "deleted", "project_id": project_id}


# --- Project-Scoped API Key Routes ---

@router.get("/v1/projects/{project_id}/keys", summary="List API keys for a project")
def list_project_keys(
    project_id: str,
    context: AuthContext = Depends(require_permission("keys:read")),
    db: Session = Depends(get_db_session)
) -> List[Dict[str, Any]]:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project or project.org_id != context.org_id:
        raise HTTPException(status_code=404, detail="Project not found in organization.")

    return APIKeyService.list_keys_for_project(db, project_id=project_id, org_id=context.org_id)


@router.post("/v1/projects/{project_id}/keys", summary="Create a project-scoped API key")
def create_project_key(
    project_id: str,
    payload: ProjectKeyCreateRequest,
    context: AuthContext = Depends(require_permission("keys:manage")),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project or project.org_id != context.org_id:
        raise HTTPException(status_code=404, detail="Project not found in organization.")

    env = payload.environment or project.environment or "dev"

    key_data = APIKeyService.generate_api_key(
        db=db,
        org_id=context.org_id,
        name=payload.name,
        project_id=project_id,
        environment=env,
        role=payload.role,
        created_by_id=context.user_id,
        expires_in_days=payload.expires_in_days
    )
    return key_data


@router.delete("/v1/projects/{project_id}/keys/{key_id}", summary="Revoke a project-scoped API key")
def revoke_project_key(
    project_id: str,
    key_id: str,
    context: AuthContext = Depends(require_permission("keys:manage")),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project or project.org_id != context.org_id:
        raise HTTPException(status_code=404, detail="Project not found in organization.")

    success = APIKeyService.revoke_api_key(db, key_id=key_id, org_id=context.org_id)
    if not success:
        raise HTTPException(status_code=404, detail="API key not found.")

    return {"status": "revoked", "key_id": key_id}


@router.get("/v1/orgs/{org_id}/keys", summary="List all API keys for an organization")
def list_org_keys(
    org_id: str,
    context: AuthContext = Depends(require_permission("keys:read")),
    db: Session = Depends(get_db_session)
) -> List[Dict[str, Any]]:
    if context.org_id != org_id and context.role != AppRole.OWNER.value:
        raise HTTPException(status_code=403, detail="Cannot access keys of another organization.")
    return APIKeyService.list_keys_for_org(db, org_id=org_id)


@router.post("/v1/orgs/{org_id}/keys", summary="Create an organization or project API key")
def create_org_key(
    org_id: str,
    payload: ProjectKeyCreateRequest,
    context: AuthContext = Depends(require_permission("keys:manage")),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    if context.org_id != org_id and context.role != AppRole.OWNER.value:
        raise HTTPException(status_code=403, detail="Cannot create keys for another organization.")

    project = db.query(Project).filter(Project.org_id == org_id).first()
    project_id = project.id if project else None
    env = payload.environment or (project.environment if project else "prod") or "prod"

    key_data = APIKeyService.generate_api_key(
        db=db,
        org_id=org_id,
        name=payload.name,
        project_id=project_id,
        environment=env,
        role=payload.role,
        created_by_id=context.user_id,
        expires_in_days=payload.expires_in_days
    )
    return key_data


@router.delete("/v1/keys/{key_id}", summary="Revoke an API key directly")
def revoke_key_direct(
    key_id: str,
    context: AuthContext = Depends(require_permission("keys:manage")),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    success = APIKeyService.revoke_api_key(db, key_id=key_id, org_id=context.org_id)
    if not success:
        raise HTTPException(status_code=404, detail="API key not found.")
    return {"status": "revoked", "key_id": key_id}


# --- Team Members & Invitations Routes (Owner only for mutations) ---

@router.get("/v1/orgs/{org_id}/members", summary="List organization team members")
def list_members(
    org_id: str,
    context: AuthContext = Depends(require_permission("team:read")),
    db: Session = Depends(get_db_session)
) -> List[Dict[str, Any]]:
    if context.org_id != org_id and context.role != AppRole.OWNER.value:
        raise HTTPException(status_code=403, detail="Cannot view team members of another organization.")

    members = db.query(Membership).filter(Membership.org_id == org_id).all()
    return [
        {
            "id": m.id,
            "clerk_user_id": m.clerk_user_id,
            "email": m.email,
            "name": m.name,
            "role": m.role,
            "created_at": m.created_at.isoformat() if m.created_at else None
        }
        for m in members
    ]


@router.post("/v1/orgs/{org_id}/invites", summary="Invite a new member to the organization")
def create_invite(
    org_id: str,
    payload: InviteCreateRequest,
    context: AuthContext = Depends(require_permission("team:manage")),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    if context.org_id != org_id:
        raise HTTPException(status_code=403, detail="Cannot invite members to another organization.")

    role = payload.role.lower()
    if role not in ("owner", "developer", "viewer"):
        raise HTTPException(status_code=400, detail="Role must be one of: owner, developer, viewer")

    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=7)

    invite = Invitation(
        id=f"inv_{uuid.uuid4().hex[:12]}",
        org_id=org_id,
        email=payload.email,
        role=role,
        token=token,
        invited_by_id=context.user_id,
        expires_at=expires_at,
        created_at=now
    )
    db.add(invite)
    db.commit()

    return {
        "id": invite.id,
        "email": invite.email,
        "role": invite.role,
        "token": token,
        "expires_at": expires_at.isoformat(),
        "invite_url": f"/invite/{token}"
    }


@router.post("/v1/invites/{token}/accept", summary="Accept an organization invitation")
def accept_invite(
    token: str,
    payload: InviteAcceptRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    invite = db.query(Invitation).filter(Invitation.token == token).first()
    if not invite:
        raise HTTPException(status_code=404, detail="Invitation not found.")

    if invite.accepted_at is not None:
        raise HTTPException(status_code=400, detail="Invitation has already been accepted.")

    now = datetime.now(timezone.utc)
    exp = invite.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if now > exp:
        raise HTTPException(status_code=400, detail="Invitation has expired.")

    # Check if already a member
    existing = db.query(Membership).filter(
        Membership.org_id == invite.org_id,
        Membership.clerk_user_id == payload.clerk_user_id
    ).first()

    if existing:
        invite.accepted_at = now
        db.commit()
        return {
            "status": "already_member",
            "org_id": invite.org_id,
            "role": existing.role
        }

    membership_id = f"mem_{uuid.uuid4().hex[:12]}"
    membership = Membership(
        id=membership_id,
        org_id=invite.org_id,
        clerk_user_id=payload.clerk_user_id,
        email=payload.email or invite.email,
        name=payload.name,
        role=invite.role,
        invited_by_id=invite.invited_by_id,
        created_at=now
    )
    db.add(membership)
    invite.accepted_at = now
    db.commit()

    return {
        "status": "accepted",
        "membership_id": membership_id,
        "org_id": invite.org_id,
        "role": invite.role
    }


@router.patch("/v1/orgs/{org_id}/members/{member_id}/role", summary="Change member's role")
def update_member_role(
    org_id: str,
    member_id: str,
    payload: RoleUpdateRequest,
    context: AuthContext = Depends(require_permission("team:manage")),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    if context.org_id != org_id:
        raise HTTPException(status_code=403, detail="Cannot modify members of another organization.")

    new_role = payload.role.lower()
    if new_role not in ("owner", "developer", "viewer"):
        raise HTTPException(status_code=400, detail="Role must be one of: owner, developer, viewer")

    member = db.query(Membership).filter(Membership.id == member_id, Membership.org_id == org_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found.")

    # Apply Last Owner Guard if demoting an owner
    if member.role == AppRole.OWNER.value and new_role != AppRole.OWNER.value:
        check_last_owner_guard(db, org_id=org_id, member_id=member_id, action="demote")

    member.role = new_role
    db.commit()

    return {"status": "updated", "member_id": member.id, "new_role": new_role}


@router.delete("/v1/orgs/{org_id}/members/{member_id}", summary="Remove member from organization")
def remove_member(
    org_id: str,
    member_id: str,
    context: AuthContext = Depends(require_permission("team:manage")),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    if context.org_id != org_id:
        raise HTTPException(status_code=403, detail="Cannot remove members from another organization.")

    # Apply Last Owner Guard
    check_last_owner_guard(db, org_id=org_id, member_id=member_id, action="remove")

    member = db.query(Membership).filter(Membership.id == member_id, Membership.org_id == org_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found.")

    db.delete(member)
    db.commit()

    return {"status": "removed", "member_id": member_id}


# --- Clerk Webhooks Handler ---

@router.post("/v1/auth/clerk/webhook", summary="Clerk Webhook Endpoint")
async def clerk_webhook(
    request: Request,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    payload_bytes = await request.body()
    headers = dict(request.headers)

    valid = ClerkService.verify_webhook_signature(payload_bytes, headers)
    if not valid:
        raise HTTPException(status_code=400, detail="Invalid Clerk webhook signature.")

    import json
    try:
        event = json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")

    result = ClerkService.handle_webhook_event(db, event)
    return result


# --- Self-Serve Signup & Login Routes ---

@router.post("/v1/auth/signup", summary="Self-Serve Developer Signup with Verification")
@router.post("/api/v1/auth/signup", summary="Self-Serve Developer Signup (Alias)")
def self_serve_signup(
    payload: SignupRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    clean_email = payload.email.strip().lower()

    # Check UserAccount
    user = db.query(UserAccount).filter(UserAccount.email == clean_email).first()
    if user and user.is_verified:
        raise HTTPException(status_code=400, detail="An account with this email already exists. Please sign in.")

    # 1. Generate 6-digit confirmation code & 24h cryptographic token
    otp_code = str(secrets.randbelow(900000) + 100000)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=30)
    pw_hash = hash_password(payload.password)

    # Superuser check
    superuser_emails = [e.strip().lower() for e in settings.superuser_emails.split(",") if e.strip()]
    is_super = bool(clean_email in superuser_emails or clean_email == "abdullahzaid509@gmail.com")

    # 3-Day Free Trial
    trial_expiry = now + timedelta(days=3)

    if user:
        user.name = payload.name
        user.password_hash = pw_hash
        user.verification_code = otp_code
        user.verification_code_expires_at = expires_at
        user.subscription_status = "trialing"
        user.plan_tier = "free_trial"
        user.trial_ends_at = trial_expiry
        user.is_super_user = is_super or user.is_super_user
        user.updated_at = now
    else:
        user = UserAccount(
            id=f"usr_{secrets.token_hex(6)}",
            email=clean_email,
            password_hash=pw_hash,
            name=payload.name,
            is_verified=False,
            verification_code=otp_code,
            verification_code_expires_at=expires_at,
            subscription_status="trialing",
            plan_tier="free_trial",
            trial_ends_at=trial_expiry,
            is_super_user=is_super,
            created_at=now,
            updated_at=now
        )
        db.add(user)
    db.commit()

    # 2. Store 24-hour cryptographic token in email_verification_tokens
    raw_token = create_email_verification_token(user.id)
    token_hash = hash_email_token(raw_token)
    verif_token_rec = EmailVerificationToken(
        id=f"evt_{secrets.token_hex(8)}",
        user_id=user.id,
        token_hash=token_hash,
        expires_at=now + timedelta(hours=24),
        consumed=False,
        created_at=now
    )
    db.add(verif_token_rec)
    db.commit()

    # 3. Dispatch verification email with direct CTA button and backup OTP code
    try:
        EmailService.send_verification_email(clean_email, payload.name, token=raw_token, code=otp_code)
    except Exception:
        pass

    return {
        "status": "pending_verification",
        "email": clean_email,
        "subscription_status": "trialing",
        "plan_tier": "free_trial",
        "trial_ends_at": trial_expiry.isoformat(),
        "message": f"Verification email dispatched to {clean_email}. Please click the link in your inbox or enter the 6-digit code to activate your account."
    }


@router.post("/v1/auth/verify-email", summary="Confirm Email with Token or 6-Digit OTP Code")
@router.post("/api/v1/auth/verify-email", summary="Confirm Email (Alias)")
def verify_email(
    payload: VerifyEmailRequest,
    response: Response,
    request: Request,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    user = None

    # Path A: Single-Use Cryptographic Token Verification
    if payload.token:
        token_hash = hash_email_token(payload.token.strip())
        tok_rec = db.query(EmailVerificationToken).filter(
            EmailVerificationToken.token_hash == token_hash,
            EmailVerificationToken.consumed == False
        ).first()

        if not tok_rec:
            raise HTTPException(status_code=400, detail="Invalid or already consumed verification link. Please request a new one.")

        exp = ensure_utc(tok_rec.expires_at)
        if exp and now > exp:
            raise HTTPException(status_code=400, detail="Verification link has expired (24-hour window). Please request a new link.")

        tok_rec.consumed = True
        user = db.query(UserAccount).filter(UserAccount.id == tok_rec.user_id).first()

    # Path B: 6-Digit OTP Code Verification
    elif payload.email and payload.code:
        clean_email = payload.email.strip().lower()
        user = db.query(UserAccount).filter(UserAccount.email == clean_email).first()
        if not user:
            raise HTTPException(status_code=404, detail="Account not found. Please sign up.")

        if not user.verification_code or user.verification_code != payload.code.strip():
            raise HTTPException(status_code=400, detail="Invalid verification code.")
        exp = ensure_utc(user.verification_code_expires_at)
        if exp and now > exp:
            raise HTTPException(status_code=400, detail="Verification code has expired. Please request a new code.")

    else:
        raise HTTPException(
            status_code=400,
            detail="Either a verification token or email + 6-digit code must be provided."
        )

    if not user:
        raise HTTPException(status_code=404, detail="User account not found.")

    user.is_verified = True
    user.verification_code = None
    user.updated_at = now
    db.commit()

    # Ensure Organization, Project, and Membership exist
    clean_email = user.email
    mem = db.query(Membership).filter(Membership.email.ilike(clean_email)).first()
    if not mem:
        org_name = f"{user.name.split()[0]}'s Workspace" if (user.name and user.name.strip()) else "My Workspace"
        base_slug = org_name.lower().replace(" ", "-").replace(".", "")
        clean_slug = f"{base_slug}-{secrets.token_hex(3)}"
        org = Organization(
            id=f"org_{secrets.token_hex(6)}",
            name=org_name,
            slug=clean_slug,
            tier="starter",
            subscription_status="trialing",
            created_at=datetime.now(timezone.utc)
        )
        db.add(org)
        db.commit()

        project = Project(
            id=f"proj_{secrets.token_hex(6)}",
            org_id=org.id,
            name="Production Agent",
            environment="prod",
            created_at=datetime.now(timezone.utc)
        )
        db.add(project)

        mem = Membership(
            id=f"mem_{secrets.token_hex(6)}",
            org_id=org.id,
            clerk_user_id=user.id,
            email=clean_email,
            name=user.name,
            role="owner",
            created_at=datetime.now(timezone.utc)
        )
        db.add(mem)
        db.commit()

        key_res = APIKeyService.generate_api_key(
            db=db,
            org_id=org.id,
            name="Default Live Key",
            role="owner",
            project_id=project.id,
            environment="prod"
        )
        api_key = key_res["api_key"]
        try:
            EmailService.send_welcome_email(clean_email, user.name or "Developer", api_key)
        except Exception:
            pass
    else:
        org = db.query(Organization).filter(Organization.id == mem.org_id).first()
        proj = db.query(Project).filter(Project.org_id == org.id).first() if org else None
        key_res = APIKeyService.generate_api_key(
            db=db,
            org_id=org.id if org else "org_default",
            name=f"Session Key {secrets.token_hex(2)}",
            role="owner",
            project_id=proj.id if proj else None,
            environment="prod"
        )
        api_key = key_res["api_key"]

    # Issue initial JWT Access Token & Set Refresh Token Cookie for instant dashboard access
    access_token = create_access_token(
        user_id=user.id,
        org_id=org.id if org else "",
        role="owner"
    )

    raw_refresh = generate_refresh_token()
    refresh_hash = hash_refresh_token(raw_refresh)
    refresh_record = RefreshToken(
        id=f"rt_{secrets.token_hex(8)}",
        user_id=user.id,
        token_hash=refresh_hash,
        expires_at=now + timedelta(days=settings.refresh_token_expire_days),
        created_at=now,
        user_agent=request.headers.get("user-agent", "")[:512],
        ip_address=request.client.host if request.client else None
    )
    db.add(refresh_record)
    user.last_login_at = now
    db.commit()

    response.set_cookie(
        key="mb_refresh_token",
        value=raw_refresh,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=settings.refresh_token_expire_days * 86400,
        path="/"
    )

    return {
        "status": "verified",
        "message": "Email verified successfully! Workspace ready with 3-day free trial.",
        "access_token": access_token,
        "token_type": "bearer",
        "api_key": api_key,
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": "owner",
            "is_super_user": bool(user.is_super_user),
            "subscription_status": user.subscription_status or "trialing",
            "plan_tier": user.plan_tier or "free_trial",
            "trial_ends_at": user.trial_ends_at.isoformat() if user.trial_ends_at else None
        },
        "org": {"id": org.id, "name": org.name, "tier": org.tier} if org else None
    }


@router.post("/v1/auth/resend-code", summary="Resend Verification Code / Token")
@router.post("/api/v1/auth/resend-verification", summary="Resend Verification Link (Alias)")
def resend_verification_code(
    payload: ResendCodeRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    clean_email = payload.email.strip().lower()
    user = db.query(UserAccount).filter(UserAccount.email == clean_email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Account not found.")
    if user.is_verified:
        return {"status": "already_verified", "message": "This email is already verified. Please sign in."}

    now = datetime.now(timezone.utc)
    otp_code = str(secrets.randbelow(900000) + 100000)
    user.verification_code = otp_code
    user.verification_code_expires_at = now + timedelta(minutes=30)

    # Issue fresh 24h cryptographic token
    raw_token = create_email_verification_token(user.id)
    token_hash = hash_email_token(raw_token)
    verif_token_rec = EmailVerificationToken(
        id=f"evt_{secrets.token_hex(8)}",
        user_id=user.id,
        token_hash=token_hash,
        expires_at=now + timedelta(hours=24),
        consumed=False,
        created_at=now
    )
    db.add(verif_token_rec)
    db.commit()

    EmailService.send_verification_email(clean_email, user.name or "Developer", token=raw_token, code=otp_code)
    return {"status": "sent", "message": f"Fresh verification link and code sent to {clean_email}."}


@router.post("/v1/auth/forgot-password", summary="Request Password Reset Link via Resend")
def forgot_password(
    payload: ForgotPasswordRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    clean_email = payload.email.strip().lower()
    user = db.query(UserAccount).filter(UserAccount.email == clean_email).first()
    if user:
        reset_token = secrets.token_urlsafe(32)
        user.reset_token = reset_token
        user.reset_token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        db.commit()
        EmailService.send_password_reset(clean_email, reset_token)

    return {
        "status": "success",
        "message": "If an account exists with that email, a password reset link has been dispatched."
    }


@router.post("/v1/auth/reset-password", summary="Reset Password with Secure Token")
def reset_password(
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    user = db.query(UserAccount).filter(UserAccount.reset_token == payload.token.strip()).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired password reset token.")
    exp = ensure_utc(user.reset_token_expires_at)
    if exp and now > exp:
        raise HTTPException(status_code=400, detail="Password reset token has expired. Please request a new one.")


    user.password_hash = hash_password(payload.new_password)
    user.reset_token = None
    user.reset_token_expires_at = None
    user.updated_at = now
    db.commit()

    return {"status": "success", "message": "Password updated successfully. You can now sign in."}


@router.post("/v1/auth/login", summary="Secure Developer Login with JWT + Refresh Token")
def self_serve_login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    # --- API Key login path ---
    if payload.api_key:
        api_key = APIKeyService.verify_api_key(db, payload.api_key)
        if not api_key:
            raise HTTPException(status_code=401, detail="Invalid or revoked API key.")
        org = db.query(Organization).filter(Organization.id == api_key.org_id).first()
        mem = db.query(Membership).filter(Membership.org_id == org.id).first() if org else None
        user_name = mem.name if (mem and mem.name) else "Developer"
        user_email = mem.email if (mem and mem.email) else ""
        return {
            "status": "authenticated",
            "auth_type": "api_key",
            "org": {"id": org.id, "name": org.name, "tier": org.tier} if org else None,
            "project_id": api_key.project_id,
            "role": api_key.role,
            "api_key": payload.api_key,
            "user": {"name": user_name, "email": user_email, "role": api_key.role}
        }

    # --- Email + Password login path ---
    if not payload.email:
        raise HTTPException(
            status_code=400,
            detail="Please enter your work email and password, or provide an active API key."
        )

    clean_email = payload.email.strip().lower()
    if not payload.password:
        raise HTTPException(status_code=400, detail="Password is required to sign in.")

    user = db.query(UserAccount).filter(UserAccount.email == clean_email).first()
    if not user:
        raise HTTPException(
            status_code=404,
            detail="No account found with this email. Please sign up to create your workspace."
        )

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")

    # Email verification gate
    if not user.is_verified:
        return {
            "status": "unverified",
            "email": clean_email,
            "message": "Please verify your email before logging in."
        }

    # Find membership and org
    mem = db.query(Membership).filter(Membership.email.ilike(clean_email)).first()
    if not mem:
        raise HTTPException(
            status_code=403,
            detail="No active workspace found for this account. Please contact support."
        )

    org = db.query(Organization).filter(Organization.id == mem.org_id).first()
    proj = db.query(Project).filter(Project.org_id == org.id).first() if org else None

    # Generate JWT access token
    access_token = create_access_token(
        user_id=user.id,
        org_id=org.id if org else "",
        role=mem.role,
        remember_me=payload.remember_me
    )

    # Generate refresh token
    raw_refresh = generate_refresh_token()
    refresh_hash = hash_refresh_token(raw_refresh)
    now = datetime.now(timezone.utc)

    refresh_record = RefreshToken(
        id=f"rt_{secrets.token_hex(8)}",
        user_id=user.id,
        token_hash=refresh_hash,
        expires_at=now + timedelta(days=settings.refresh_token_expire_days),
        created_at=now,
        user_agent=request.headers.get("user-agent", "")[:512],
        ip_address=request.client.host if request.client else None
    )
    db.add(refresh_record)

    # Update last login
    user.last_login_at = now
    user.updated_at = now
    db.commit()

    # Also generate an API key for backward compatibility with dashboard
    key_res = APIKeyService.generate_api_key(
        db=db,
        org_id=org.id if org else "org_default",
        name=f"Session Key {secrets.token_hex(2)}",
        role=mem.role,
        project_id=proj.id if proj else None,
        environment="prod"
    )

    # Set refresh token as httpOnly secure cookie
    cookie_max_age = settings.refresh_token_expire_days * 86400
    response.set_cookie(
        key="mb_refresh_token",
        value=raw_refresh,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=cookie_max_age,
        path="/"
    )

    user_name = user.name or mem.name or "Developer"
    return {
        "status": "authenticated",
        "auth_type": "email_password",
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.access_token_expire_minutes * 60 if not payload.remember_me else 30 * 86400,
        "org": {"id": org.id, "name": org.name, "tier": org.tier} if org else None,
        "project_id": proj.id if proj else None,
        "role": mem.role,
        "api_key": key_res["api_key"],
        "user": {"name": user_name, "email": clean_email, "role": mem.role}
    }


@router.get("/v1/auth/config", summary="Get Public Auth Configuration")
def get_auth_config() -> Dict[str, Any]:
    return {
        "google_client_id": settings.google_client_id or "",
        "has_google_auth": bool(settings.google_client_id),
        "app_base_url": settings.app_base_url
    }


@router.post("/v1/auth/google", summary="Google OAuth 2.0 Social Login")
@router.post("/api/v1/auth/google", summary="Google OAuth 2.0 Social Login (Alias)")
def google_auth(
    payload: GoogleAuthRequest,
    response: Response,
    request: Request,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    email = None
    name = payload.name
    picture = payload.picture

    # 1. OAuth 2.0 Authorization Code Exchange (Frontend redirect flow)
    if payload.code:
        token_url = "https://oauth2.googleapis.com/token"
        redirect_uri = payload.redirect_uri or settings.google_redirect_uri
        if redirect_uri and not redirect_uri.startswith("http"):
            redirect_uri = f"{settings.app_base_url.rstrip('/')}/{redirect_uri.lstrip('/')}"
        token_payload = {
            "code": payload.code.strip(),
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code"
        }
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(token_url, data=token_payload)
                if res.status_code == 200:
                    token_data = res.json()
                    access_token_google = token_data.get("access_token")
                    if access_token_google:
                        userinfo_res = client.get(
                            "https://www.googleapis.com/oauth2/v3/userinfo",
                            headers={"Authorization": f"Bearer {access_token_google}"}
                        )
                        if userinfo_res.status_code == 200:
                            profile = userinfo_res.json()
                            email = profile.get("email")
                            name = profile.get("name") or name
                            picture = profile.get("picture") or picture
                else:
                    logger.warning(f"Google OAuth token exchange returned {res.status_code}: {res.text}")
        except Exception as exc:
            logger.warning(f"Google OAuth exchange error: {exc}")

    # 2. Google Identity Services ID Token JWT Verification
    if not email and payload.credential:
        token = payload.credential.strip()
        try:
            with httpx.Client(timeout=5.0) as client:
                res = client.get(f"https://oauth2.googleapis.com/tokeninfo?id_token={token}")
                if res.status_code == 200:
                    data = res.json()
                    email = data.get("email")
                    name = data.get("name") or name
                    picture = data.get("picture") or picture
                    if settings.google_client_id and data.get("aud") != settings.google_client_id:
                        raise HTTPException(status_code=401, detail="Google token audience mismatch.")
        except HTTPException:
            raise
        except Exception:
            pass

        # Fallback: Parse JWT payload directly if tokeninfo network failed
        if not email:
            try:
                parts = token.split(".")
                if len(parts) >= 2:
                    padding = "=" * (4 - (len(parts[1]) % 4))
                    decoded = base64.urlsafe_b64decode(parts[1] + padding).decode("utf-8")
                    payload_data = json.loads(decoded)
                    email = payload_data.get("email")
                    name = payload_data.get("name") or name
                    picture = payload_data.get("picture") or picture
            except Exception:
                pass

    # Direct email fallback only allowed in development/testing
    if not email and payload.email:
        if settings.environment in ("development", "testing", "local"):
            email = payload.email.strip().lower()

    if not email:
        raise HTTPException(
            status_code=400,
            detail="Unable to verify Google credentials. Please select a valid Google account."
        )

    clean_email = email.strip().lower()
    user_name = name or (" ".join([part.capitalize() for part in clean_email.split('@')[0].replace('.', ' ').replace('_', ' ').replace('-', ' ').split()]) or "Developer")

    # Superuser check
    superuser_emails = [e.strip().lower() for e in settings.superuser_emails.split(",") if e.strip()]
    is_super = bool(clean_email in superuser_emails or clean_email == "abdullahzaid509@gmail.com")

    # Look up or create UserAccount
    user = db.query(UserAccount).filter(UserAccount.email == clean_email).first()
    now = datetime.now(timezone.utc)
    trial_expiry = now + timedelta(days=3)

    if not user:
        user = UserAccount(
            id=f"usr_{secrets.token_hex(8)}",
            email=clean_email,
            name=user_name,
            password_hash=hash_password(secrets.token_hex(24)),
            is_verified=True,
            is_super_user=is_super,
            subscription_status="trialing",
            plan_tier="free_trial",
            trial_ends_at=trial_expiry,
            last_login_at=now,
            created_at=now,
            updated_at=now
        )
        db.add(user)
        db.commit()
    else:
        user.is_verified = True
        user.verification_code = None
        user.last_login_at = now
        if not user.name and user_name:
            user.name = user_name
        if is_super:
            user.is_super_user = True
        if not user.trial_ends_at:
            user.subscription_status = "trialing"
            user.plan_tier = "free_trial"
            user.trial_ends_at = trial_expiry
        user.updated_at = now
        db.commit()

    # Ensure Organization, Project, and APIKey exist for user
    mem = db.query(Membership).filter(Membership.email.ilike(clean_email)).first()
    if not mem:
        org_name = f"{user_name.split()[0]}'s Workspace" if user_name else "My Workspace"
        base_slug = org_name.lower().replace(" ", "-").replace(".", "")
        clean_slug = f"{base_slug}-{secrets.token_hex(3)}"
        org = Organization(
            id=f"org_{secrets.token_hex(6)}",
            name=org_name,
            slug=clean_slug,
            tier="starter",
            subscription_status="trialing",
            created_at=now
        )
        db.add(org)
        db.commit()

        project = Project(
            id=f"proj_{secrets.token_hex(6)}",
            org_id=org.id,
            name="Production Agent",
            environment="prod",
            created_at=now
        )
        db.add(project)
        proj = project

        mem = Membership(
            id=f"mem_{secrets.token_hex(6)}",
            org_id=org.id,
            clerk_user_id=user.id,
            email=clean_email,
            name=user_name,
            role="owner",
            created_at=now
        )
        db.add(mem)
        db.commit()

        key_res = APIKeyService.generate_api_key(
            db=db,
            org_id=org.id,
            name="Default Live Key",
            role="owner",
            project_id=project.id,
            environment="prod"
        )
        api_key = key_res["api_key"]
        try:
            EmailService.send_welcome_email(clean_email, user_name, api_key)
        except Exception:
            pass
    else:
        org = db.query(Organization).filter(Organization.id == mem.org_id).first()
        proj = db.query(Project).filter(Project.org_id == org.id).first() if org else None
        key_res = APIKeyService.generate_api_key(
            db=db,
            org_id=org.id if org else "org_default",
            name=f"Google Session Key {secrets.token_hex(2)}",
            role="owner",
            project_id=proj.id if proj else None,
            environment="prod"
        )
        api_key = key_res["api_key"]

    # Issue JWT access token & set secure refresh token cookie
    access_token = create_access_token(
        user_id=user.id,
        org_id=org.id if org else "",
        role="owner"
    )

    raw_refresh = generate_refresh_token()
    refresh_hash = hash_refresh_token(raw_refresh)
    refresh_record = RefreshToken(
        id=f"rt_{secrets.token_hex(8)}",
        user_id=user.id,
        token_hash=refresh_hash,
        expires_at=now + timedelta(days=settings.refresh_token_expire_days),
        created_at=now,
        user_agent=request.headers.get("user-agent", "")[:512],
        ip_address=request.client.host if request.client else None
    )
    db.add(refresh_record)
    db.commit()

    response.set_cookie(
        key="mb_refresh_token",
        value=raw_refresh,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=settings.refresh_token_expire_days * 86400,
        path="/"
    )

    return {
        "status": "authenticated",
        "auth_type": "google",
        "message": "Successfully authenticated with Google.",
        "access_token": access_token,
        "token_type": "bearer",
        "api_key": api_key,
        "user": {
            "id": user.id,
            "email": clean_email,
            "name": user.name or user_name,
            "role": "owner",
            "picture": picture,
            "is_super_user": bool(user.is_super_user),
            "subscription_status": user.subscription_status or "trialing",
            "plan_tier": user.plan_tier or "free_trial",
            "trial_ends_at": user.trial_ends_at.isoformat() if user.trial_ends_at else None
        },
        "org": {"id": org.id, "name": org.name, "tier": org.tier} if org else None,
        "project_id": proj.id if 'proj' in locals() and proj else None
    }


@router.post("/v1/auth/refresh", summary="Refresh Access Token using Refresh Cookie")
def refresh_access_token(
    request: Request,
    response: Response,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    raw_token = request.cookies.get("mb_refresh_token")
    if not raw_token:
        raise HTTPException(status_code=401, detail="No refresh token provided. Please log in.")

    token_hash = hash_refresh_token(raw_token)
    now = datetime.now(timezone.utc)

    rt = db.query(RefreshToken).filter(
        RefreshToken.token_hash == token_hash,
        RefreshToken.revoked_at == None
    ).first()

    if not rt:
        raise HTTPException(status_code=401, detail="Invalid or revoked refresh token. Please log in again.")

    exp = rt.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if now > exp:
        rt.revoked_at = now
        db.commit()
        raise HTTPException(status_code=401, detail="Refresh token expired. Please log in again.")

    # Get user and membership
    user = db.query(UserAccount).filter(UserAccount.id == rt.user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User account not found.")

    mem = db.query(Membership).filter(Membership.email.ilike(user.email)).first()
    org_id = mem.org_id if mem else ""
    role = mem.role if mem else "developer"

    # Issue new access token
    access_token = create_access_token(
        user_id=user.id,
        org_id=org_id,
        role=role
    )

    # Rotate refresh token (revoke old, issue new)
    rt.revoked_at = now
    new_raw = generate_refresh_token()
    new_hash = hash_refresh_token(new_raw)
    new_rt = RefreshToken(
        id=f"rt_{secrets.token_hex(8)}",
        user_id=user.id,
        token_hash=new_hash,
        expires_at=now + timedelta(days=settings.refresh_token_expire_days),
        created_at=now,
        user_agent=request.headers.get("user-agent", "")[:512],
        ip_address=request.client.host if request.client else None
    )
    db.add(new_rt)
    db.commit()

    response.set_cookie(
        key="mb_refresh_token",
        value=new_raw,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=settings.refresh_token_expire_days * 86400,
        path="/"
    )

    org = db.query(Organization).filter(Organization.id == org_id).first() if org_id else None
    return {
        "status": "refreshed",
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.access_token_expire_minutes * 60,
        "user": {"id": user.id, "email": user.email, "name": user.name, "role": role},
        "org": {"id": org.id, "name": org.name, "tier": org.tier} if org else None
    }


@router.post("/v1/auth/logout", summary="Logout and Invalidate Refresh Token")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    raw_token = request.cookies.get("mb_refresh_token")
    if raw_token:
        token_hash = hash_refresh_token(raw_token)
        rt = db.query(RefreshToken).filter(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked_at == None
        ).first()
        if rt:
            rt.revoked_at = datetime.now(timezone.utc)
            db.commit()

    response.delete_cookie("mb_refresh_token", path="/")
    return {"status": "logged_out", "message": "Successfully logged out."}


@router.get("/v1/auth/me", summary="Get Current Authenticated User Profile")
def get_current_user(
    request: Request,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    # Try Authorization header first
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        payload = decode_access_token(token)
        if payload:
            user = db.query(UserAccount).filter(UserAccount.id == payload["sub"]).first()
            if user:
                org = db.query(Organization).filter(Organization.id == payload.get("org_id")).first()
                return {
                    "authenticated": True,
                    "user": {
                        "id": user.id,
                        "email": user.email,
                        "name": user.name,
                        "role": payload.get("role", "developer"),
                        "email_verified": user.is_verified,
                        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None
                    },
                    "org": {"id": org.id, "name": org.name, "tier": org.tier} if org else None
                }

    raise HTTPException(status_code=401, detail="Not authenticated. Please log in.")

