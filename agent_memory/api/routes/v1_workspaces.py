"""Workspaces, Projects, RBAC Team Management, and Clerk Webhooks API Routes."""

import uuid
import secrets
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, EmailStr
from fastapi import APIRouter, Depends, HTTPException, Request, Header, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from ...database import get_db_session
from ...models.db_models import Organization, Project, Membership, Invitation, APIKey
from ...auth.rbac_middleware import (
    AuthContext,
    AppRole,
    get_auth_context,
    require_permission,
    check_last_owner_guard
)
from ...auth.api_key_service import APIKeyService
from ...auth.clerk_service import ClerkService

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


class SignupRequest(BaseModel):
    name: str = Field(..., description="Developer or founder full name")
    email: EmailStr = Field(..., description="Work email address")
    organization_name: Optional[str] = Field(default=None, description="Company or workspace name")
    tier: str = Field(default="starter", description="starter, growth, scale, enterprise")


class LoginRequest(BaseModel):
    email: Optional[str] = Field(default=None, description="Email address to log in")
    api_key: Optional[str] = Field(default=None, description="Active API key to log in")


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

@router.post("/v1/auth/signup", summary="Self-Serve Developer Signup")
def self_serve_signup(
    payload: SignupRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    existing_mem = db.query(Membership).filter(Membership.email == payload.email).first()
    if existing_mem:
        org = db.query(Organization).filter(Organization.id == existing_mem.org_id).first()
        proj = db.query(Project).filter(Project.org_id == org.id).first() if org else None
        key_res = APIKeyService.generate_api_key(
            db=db,
            org_id=org.id if org else "org_default",
            name=f"Login Key {secrets.token_hex(3)}",
            role=existing_mem.role,
            project_id=proj.id if proj else None,
            environment="prod"
        )
        return {
            "status": "existing_user",
            "message": "Welcome back! Account found and new key provisioned.",
            "org": {"id": org.id, "name": org.name, "tier": org.tier} if org else None,
            "project_id": proj.id if proj else None,
            "api_key": key_res["api_key"],
            "user": {"email": existing_mem.email, "name": existing_mem.name}
        }

    org_name = payload.organization_name or f"{payload.name.split()[0]}'s Workspace"
    base_slug = org_name.lower().replace(" ", "-").replace(".", "")
    clean_slug = f"{base_slug}-{secrets.token_hex(3)}"
    org_id = f"org_{secrets.token_hex(6)}"

    org = Organization(
        id=org_id,
        name=org_name,
        slug=clean_slug,
        tier=payload.tier.lower() if payload.tier.lower() in ("starter", "growth", "scale", "enterprise") else "starter",
        subscription_status="active",
        created_at=datetime.now(timezone.utc)
    )
    db.add(org)

    project_id = f"proj_{secrets.token_hex(6)}"
    project = Project(
        id=project_id,
        org_id=org.id,
        name="Production Agent",
        environment="prod",
        created_at=datetime.now(timezone.utc)
    )
    db.add(project)

    clerk_id = f"user_{secrets.token_hex(8)}"
    membership = Membership(
        id=f"mem_{secrets.token_hex(6)}",
        org_id=org.id,
        clerk_user_id=clerk_id,
        email=payload.email,
        name=payload.name,
        role="owner",
        created_at=datetime.now(timezone.utc)
    )
    db.add(membership)
    db.commit()

    key_res = APIKeyService.generate_api_key(
        db=db,
        org_id=org.id,
        name="Default Live Key",
        role="owner",
        project_id=project.id,
        environment="prod"
    )

    return {
        "status": "created",
        "message": "Welcome to MemoryBrain! Workspace and API key successfully provisioned.",
        "org": {"id": org.id, "name": org.name, "slug": org.slug, "tier": org.tier},
        "project": {"id": project.id, "name": project.name},
        "api_key": key_res["api_key"],
        "user": {"email": payload.email, "name": payload.name, "role": "owner"}
    }


@router.post("/v1/auth/login", summary="Self-Serve Developer Login")
def self_serve_login(
    payload: LoginRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    if payload.api_key:
        api_key = APIKeyService.verify_api_key(db, payload.api_key)
        if not api_key:
            raise HTTPException(status_code=401, detail="Invalid or revoked API key.")
        org = db.query(Organization).filter(Organization.id == api_key.org_id).first()
        mem = db.query(Membership).filter(Membership.org_id == org.id).first() if org else None
        user_name = mem.name if (mem and mem.name and "alice" not in mem.name.lower()) else "Developer"
        user_email = mem.email if (mem and mem.email and "alice" not in mem.email.lower()) else "developer@company.internal"
        return {
            "status": "authenticated",
            "auth_type": "api_key",
            "org": {"id": org.id, "name": org.name, "tier": org.tier} if org else None,
            "project_id": api_key.project_id,
            "role": api_key.role,
            "api_key": payload.api_key,
            "user": {"name": user_name, "email": user_email, "role": api_key.role}
        }

    if payload.email:
        clean_email = payload.email.strip().lower()
        mem = db.query(Membership).filter(Membership.email.ilike(clean_email)).first()
        formatted_name = " ".join([part.capitalize() for part in clean_email.split('@')[0].replace('.', ' ').replace('_', ' ').replace('-', ' ').split()]) or "Developer"
        if not mem:
            org = db.query(Organization).first()
            if not org:
                org = Organization(
                    id="org_default_dev",
                    name="My Workspace",
                    slug="my-workspace",
                    tier="growth"
                )
                db.add(org)
                db.commit()

            proj = db.query(Project).filter(Project.org_id == org.id).first()
            if not proj:
                proj = Project(id="proj_prod", org_id=org.id, name="SupportBot", environment="prod")
                db.add(proj)
                db.commit()

            mem = Membership(
                id=f"mem_{secrets.token_hex(4)}",
                org_id=org.id,
                clerk_user_id=f"user_{secrets.token_hex(4)}",
                name=formatted_name,
                email=clean_email,
                role="owner"
            )
            db.add(mem)
            db.commit()
        elif not mem.name or "alice" in mem.name.lower():
            mem.name = formatted_name
            db.commit()

        user_name = mem.name or formatted_name
        org = db.query(Organization).filter(Organization.id == mem.org_id).first()
        proj = db.query(Project).filter(Project.org_id == org.id).first() if org else None
        key_res = APIKeyService.generate_api_key(
            db=db,
            org_id=org.id if org else "org_default",
            name=f"Session Key {secrets.token_hex(2)}",
            role=mem.role,
            project_id=proj.id if proj else None,
            environment="prod"
        )
        return {
            "status": "authenticated",
            "auth_type": "email",
            "org": {"id": org.id, "name": org.name, "tier": org.tier} if org else None,
            "project_id": proj.id if proj else None,
            "api_key": key_res["api_key"],
            "user": {"name": user_name, "email": mem.email or clean_email, "role": mem.role}
        }

    # Instant Demo Workspace Login
    demo_org = db.query(Organization).first()
    if not demo_org:
        demo_org = Organization(
            id="org_default_demo",
            name="Acme AI Technologies",
            slug="acme-ai-demo",
            tier="growth"
        )
        db.add(demo_org)
        db.commit()

    demo_proj = db.query(Project).filter(Project.org_id == demo_org.id).first()
    if not demo_proj:
        demo_proj = Project(id="proj_default_demo", org_id=demo_org.id, name="SupportBot", environment="prod")
        db.add(demo_proj)
        db.commit()

    key_res = APIKeyService.generate_api_key(
        db=db,
        org_id=demo_org.id,
        name="Instant Demo Key",
        role="owner",
        project_id=demo_proj.id,
        environment="prod"
    )

    return {
        "status": "authenticated",
        "auth_type": "demo",
        "org": {"id": demo_org.id, "name": demo_org.name, "tier": demo_org.tier},
        "project_id": demo_proj.id,
        "api_key": key_res["api_key"],
        "user": {"name": "Demo Founder", "email": "founder@acme.ai", "role": "owner"}
    }
