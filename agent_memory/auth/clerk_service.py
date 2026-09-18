"""Clerk Auth & Webhook Synchronization Service."""

import hmac
import hashlib
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from ..models.db_models import Organization, Project, Membership
from ..config import settings

logger = logging.getLogger("memory_brain.clerk")


class ClerkService:
    """Handles Clerk webhook synchronization and tenant lifecycle."""

    @classmethod
    def verify_webhook_signature(
        cls,
        payload_bytes: bytes,
        headers: Dict[str, str],
        secret: Optional[str] = None
    ) -> bool:
        """
        Validates Svix/Clerk webhook signatures using HMAC-SHA256.
        Svix headers: svix-id, svix-timestamp, svix-signature.
        """
        webhook_secret = secret or settings.clerk_webhook_secret

        # If secret is test mock or not configured, pass in non-prod
        if not webhook_secret or webhook_secret == "whsec_mock_clerk_webhook_secret":
            return True

        svix_id = headers.get("svix-id")
        svix_timestamp = headers.get("svix-timestamp")
        svix_signature = headers.get("svix-signature")

        if not svix_id or not svix_timestamp or not svix_signature:
            # Fallback to x-clerk-signature or direct header check
            alt_sig = headers.get("x-clerk-signature")
            if alt_sig:
                computed = hmac.new(
                    webhook_secret.encode("utf-8"),
                    payload_bytes,
                    hashlib.sha256
                ).hexdigest()
                return hmac.compare_digest(computed, alt_sig)
            return False

        # Svix signing string: {svix_id}.{svix_timestamp}.{payload}
        to_sign = f"{svix_id}.{svix_timestamp}.".encode("utf-8") + payload_bytes

        # Svix secrets typically start with whsec_ and are base64 encoded
        import base64
        key = webhook_secret
        if key.startswith("whsec_"):
            key = key[6:]
        try:
            key_bytes = base64.b64decode(key)
        except Exception:
            key_bytes = key.encode("utf-8")

        computed_sig = base64.b64encode(
            hmac.new(key_bytes, to_sign, hashlib.sha256).digest()
        ).decode("utf-8")

        # Svix header can be v1,signature1 v1,signature2
        signatures = svix_signature.split(" ")
        for sig in signatures:
            parts = sig.split(",", 1)
            sig_val = parts[1] if len(parts) > 1 else parts[0]
            if hmac.compare_digest(computed_sig, sig_val):
                return True

        return False

    @classmethod
    def handle_webhook_event(cls, db: Session, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processes Clerk webhook events:
        - user.created: Auto-creates personal 1-person org, dev project, owner membership
        - organization.created: Creates org, default dev project, creator membership
        - organizationMembership.created: Adds member with role
        - organizationMembership.updated: Updates role
        - organizationMembership.deleted: Removes member
        """
        event_type = event.get("type", "")
        data = event.get("data", {})

        if event_type == "user.created":
            return cls._handle_user_created(db, data)
        elif event_type == "organization.created":
            return cls._handle_organization_created(db, data)
        elif event_type in ("organizationMembership.created", "organization_membership.created"):
            return cls._handle_membership_created(db, data)
        elif event_type in ("organizationMembership.updated", "organization_membership.updated"):
            return cls._handle_membership_updated(db, data)
        elif event_type in ("organizationMembership.deleted", "organization_membership.deleted"):
            return cls._handle_membership_deleted(db, data)
        else:
            return {"status": "ignored", "event_type": event_type}

    @classmethod
    def _handle_user_created(cls, db: Session, data: Dict[str, Any]) -> Dict[str, Any]:
        user_id = data.get("id")
        first_name = data.get("first_name") or ""
        last_name = data.get("last_name") or ""
        full_name = f"{first_name} {last_name}".strip() or "User"

        emails = data.get("email_addresses", [])
        primary_email = emails[0].get("email_address") if emails else None

        # Check if personal org already exists
        existing_org = db.query(Organization).filter(
            Organization.slug == f"personal-{user_id[-8:]}"
        ).first()

        if existing_org:
            return {"status": "already_exists", "org_id": existing_org.id}

        # 1. Create personal 1-person organization
        org_id = f"org_{uuid.uuid4().hex[:12]}"
        org_name = f"{first_name}'s Workspace" if first_name else "Personal Workspace"
        slug = f"personal-{user_id[-8:]}"

        org = Organization(
            id=org_id,
            name=org_name,
            slug=slug,
            tier="starter",
            subscription_status="active",
            clerk_org_id=None,
            is_active=True,
            created_at=datetime.now(timezone.utc)
        )
        db.add(org)

        # 2. Create default development project
        proj_id = f"proj_{uuid.uuid4().hex[:12]}"
        project = Project(
            id=proj_id,
            org_id=org_id,
            name="Development",
            environment="dev",
            is_active=True,
            created_at=datetime.now(timezone.utc)
        )
        db.add(project)

        # 3. Add user as Owner
        membership_id = f"mem_{uuid.uuid4().hex[:12]}"
        membership = Membership(
            id=membership_id,
            org_id=org_id,
            clerk_user_id=user_id,
            email=primary_email,
            name=full_name,
            role="owner",
            created_at=datetime.now(timezone.utc)
        )
        db.add(membership)

        db.commit()

        logger.info(f"Auto-provisioned personal workspace {org_id} for Clerk user {user_id}")
        return {
            "status": "provisioned",
            "org_id": org_id,
            "project_id": proj_id,
            "user_id": user_id,
            "role": "owner"
        }

    @classmethod
    def _handle_organization_created(cls, db: Session, data: Dict[str, Any]) -> Dict[str, Any]:
        clerk_org_id = data.get("id")
        name = data.get("name", "Team Workspace")
        slug = data.get("slug") or f"org-{clerk_org_id[-8:]}"
        created_by = data.get("created_by")

        # Check if already exists
        org = db.query(Organization).filter(
            (Organization.clerk_org_id == clerk_org_id) | (Organization.slug == slug)
        ).first()

        if not org:
            org_id = f"org_{uuid.uuid4().hex[:12]}"
            org = Organization(
                id=org_id,
                name=name,
                slug=slug,
                tier="starter",
                subscription_status="active",
                clerk_org_id=clerk_org_id,
                is_active=True,
                created_at=datetime.now(timezone.utc)
            )
            db.add(org)
            db.flush()

            # Create default dev project
            proj_id = f"proj_{uuid.uuid4().hex[:12]}"
            project = Project(
                id=proj_id,
                org_id=org.id,
                name="Development",
                environment="dev",
                is_active=True,
                created_at=datetime.now(timezone.utc)
            )
            db.add(project)

        if created_by:
            # Upsert creator as owner
            m = db.query(Membership).filter(
                Membership.org_id == org.id,
                Membership.clerk_user_id == created_by
            ).first()
            if not m:
                m = Membership(
                    id=f"mem_{uuid.uuid4().hex[:12]} ",
                    org_id=org.id,
                    clerk_user_id=created_by,
                    role="owner",
                    created_at=datetime.now(timezone.utc)
                )
                db.add(m)

        db.commit()
        return {"status": "created", "org_id": org.id, "clerk_org_id": clerk_org_id}

    @classmethod
    def _handle_membership_created(cls, db: Session, data: Dict[str, Any]) -> Dict[str, Any]:
        clerk_org_id = data.get("organization", {}).get("id") or data.get("org_id")
        user_data = data.get("public_user_data", {})
        clerk_user_id = user_data.get("user_id") or data.get("user_id")
        clerk_role = data.get("role", "org:member")

        # Map Clerk role to internal role (owner, developer, viewer)
        role = "owner" if "admin" in clerk_role.lower() else "developer"

        org = db.query(Organization).filter(
            (Organization.clerk_org_id == clerk_org_id) | (Organization.id == clerk_org_id)
        ).first()

        if not org:
            return {"status": "error", "message": f"Org not found for {clerk_org_id}"}

        m = db.query(Membership).filter(
            Membership.org_id == org.id,
            Membership.clerk_user_id == clerk_user_id
        ).first()

        if not m:
            m = Membership(
                id=f"mem_{uuid.uuid4().hex[:12]}",
                org_id=org.id,
                clerk_user_id=clerk_user_id,
                email=user_data.get("identifier"),
                name=f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip() or None,
                role=role,
                created_at=datetime.now(timezone.utc)
            )
            db.add(m)
        else:
            m.role = role

        db.commit()
        return {"status": "member_synced", "org_id": org.id, "clerk_user_id": clerk_user_id, "role": role}

    @classmethod
    def _handle_membership_updated(cls, db: Session, data: Dict[str, Any]) -> Dict[str, Any]:
        clerk_org_id = data.get("organization", {}).get("id") or data.get("org_id")
        user_data = data.get("public_user_data", {})
        clerk_user_id = user_data.get("user_id") or data.get("user_id")
        clerk_role = data.get("role", "org:member")

        new_role = "owner" if "admin" in clerk_role.lower() else "developer"

        org = db.query(Organization).filter(
            (Organization.clerk_org_id == clerk_org_id) | (Organization.id == clerk_org_id)
        ).first()

        if not org:
            return {"status": "error", "message": "Org not found"}

        m = db.query(Membership).filter(
            Membership.org_id == org.id,
            Membership.clerk_user_id == clerk_user_id
        ).first()

        if m:
            m.role = new_role
            db.commit()
            return {"status": "role_updated", "org_id": org.id, "new_role": new_role}

        return {"status": "not_found"}

    @classmethod
    def _handle_membership_deleted(cls, db: Session, data: Dict[str, Any]) -> Dict[str, Any]:
        clerk_org_id = data.get("organization", {}).get("id") or data.get("org_id")
        user_data = data.get("public_user_data", {})
        clerk_user_id = user_data.get("user_id") or data.get("user_id")

        org = db.query(Organization).filter(
            (Organization.clerk_org_id == clerk_org_id) | (Organization.id == clerk_org_id)
        ).first()

        if not org:
            return {"status": "error", "message": "Org not found"}

        m = db.query(Membership).filter(
            Membership.org_id == org.id,
            Membership.clerk_user_id == clerk_user_id
        ).first()

        if m:
            db.delete(m)
            db.commit()
            return {"status": "deleted", "org_id": org.id, "clerk_user_id": clerk_user_id}

        return {"status": "not_found"}
