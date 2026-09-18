"""
Open-Core Self-Hosted Licensing & Feature Gating Engine.
Validates cryptographically signed offline license keys for enterprise self-hosted customers.
"""

import os
import json
import base64
import hmac
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from fastapi import HTTPException
from ..config import settings

# Master signing key (in production, held securely by the licensing server)
DEFAULT_LICENSE_SECRET = os.getenv("LICENSE_SIGNING_SECRET", "mb_master_licensing_hmac_secret_key_849201")


class LicenseError(Exception):
    """Raised when a license key is invalid, tampered, or expired."""
    pass


class LicenseValidator:
    """Manages generation, signature verification, and entitlement gating."""

    @classmethod
    def generate_signed_license(
        cls,
        customer_name: str,
        tier: str = "enterprise",
        entitlements: Optional[List[str]] = None,
        expires_days: int = 365,
        max_memories: int = 10000000,
        secret: str = DEFAULT_LICENSE_SECRET
    ) -> str:
        """Generates an offline cryptographically signed license key."""
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=expires_days)

        payload = {
            "customer_name": customer_name,
            "tier": tier.lower(),
            "entitlements": entitlements or [
                "enterprise_rbac",
                "saml_sso",
                "compliance_pack",
                "custom_limits",
                "unlimited_tenants",
                "priority_support"
            ],
            "max_memories": max_memories,
            "issued_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
        }

        payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
        payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode("utf-8").rstrip("=")
        sig = hmac.new(secret.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()

        return f"mb_lic_{payload_b64}.{sig}"

    @classmethod
    def verify_license_key(cls, key: str, secret: str = DEFAULT_LICENSE_SECRET) -> Dict[str, Any]:
        """Validates license signature, format, and expiration."""
        if not key or not key.startswith("mb_lic_"):
            raise LicenseError("Invalid license format: Key must start with 'mb_lic_'")

        stripped = key[len("mb_lic_"):]
        if "." not in stripped:
            raise LicenseError("Invalid license format: Missing signature delimiter")

        payload_b64, signature = stripped.split(".", 1)

        # 1. Verify HMAC-SHA256 signature
        expected_sig = hmac.new(secret.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            raise LicenseError("License signature verification failed: Key has been altered or forged")

        # 2. Decode payload
        padding = "=" * (-len(payload_b64) % 4)
        try:
            payload_json = base64.urlsafe_b64decode(payload_b64 + padding).decode("utf-8")
            payload = json.loads(payload_json)
        except Exception as e:
            raise LicenseError(f"Failed to decode license payload: {e}")

        # 3. Check expiration
        expires_at_str = payload.get("expires_at")
        if expires_at_str:
            expires_at = datetime.fromisoformat(expires_at_str)
            if datetime.now(timezone.utc) > expires_at:
                raise LicenseError(f"License expired on {expires_at_str}")

        return payload

    @classmethod
    def get_active_license_info(cls) -> Optional[Dict[str, Any]]:
        """Reads and verifies the license key configured in the environment."""
        key = os.getenv("MEMORYBRAIN_LICENSE_KEY", "").strip()
        if not key:
            return None
        try:
            return cls.verify_license_key(key)
        except LicenseError:
            return None

    @classmethod
    def is_feature_entitled(cls, feature_name: str) -> bool:
        """
        Determines if a feature is permitted.
        - Core features (store, recall, delete) are free and open-source for everyone.
        - Managed SaaS cloud instances are unlocked by subscription tier.
        - Self-hosted instances require an active enterprise license for enterprise features.
        """
        core_features = {"store_memory", "recall_context", "delete_memory", "single_admin", "rest_api", "mcp_server"}
        if feature_name in core_features:
            return True

        # In cloud environments, feature access is governed by the organization's billing plan
        is_self_hosted = os.getenv("DEPLOYMENT_MODE", "").lower() == "self_hosted"
        if not is_self_hosted:
            return True

        # In self-hosted mode, check license
        lic = cls.get_active_license_info()
        if not lic:
            return False

        entitlements = lic.get("entitlements", [])
        return feature_name in entitlements

    @classmethod
    def require_entitlement(cls, feature_name: str):
        """FastAPI dependency or route guard asserting feature entitlement."""
        if not cls.is_feature_entitled(feature_name):
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "ENTERPRISE_LICENSE_REQUIRED",
                    "feature": feature_name,
                    "message": (
                        f"The '{feature_name}' feature is part of the MemoryBrain Enterprise Edition. "
                        "To unlock this feature in your self-hosted deployment, obtain an Enterprise license key "
                        "at https://memorybrain.ai/pricing or contact sales@memorybrain.ai."
                    ),
                    "upgrade_url": "https://memorybrain.ai/pricing"
                }
            )
