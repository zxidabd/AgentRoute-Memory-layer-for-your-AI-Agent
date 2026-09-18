"""
Enterprise Contract & DPA Automated Dispatch Engine.
Manages generation, dispatch, and tracking of Data Processing Agreements (DPA) and MSAs.
"""

import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from ..models.db_models import Organization


class ContractDispatchService:
    """Automates sending enterprise DPAs and MSAs for countersignature."""

    @classmethod
    def generate_and_dispatch_dpa(
        cls,
        db: Session,
        org_id: str,
        authorized_signer_name: str,
        authorized_signer_email: str,
        eu_subprocessors_included: bool = True,
    ) -> Dict[str, Any]:
        org = db.query(Organization).filter(Organization.id == org_id).first()
        if not org:
            raise ValueError(f"Organization {org_id} not found")

        contract_id = f"dpa_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=30)

        dpa_envelope = {
            "contract_id": contract_id,
            "contract_type": "DATA_PROCESSING_AGREEMENT_GDPR_CCPA",
            "status": "DISPATCHED_PENDING_SIGNATURE",
            "organization": {
                "id": org.id,
                "name": org.name,
                "tier": org.tier,
            },
            "authorized_signer": {
                "name": authorized_signer_name,
                "email": authorized_signer_email,
            },
            "governing_clauses": [
                "European Commission Standard Contractual Clauses (Module 2: Controller-to-Processor)",
                "Article 28 GDPR Compliance Obligations",
                "California Consumer Privacy Act (CCPA) Service Provider Addendum",
                "Technical and Organizational Measures (TOMs) - AES-256 Envelope Encryption & Version Immutability",
                "72-Hour Security Incident Notification SLA"
            ],
            "subprocessors_disclosed": [
                "Amazon Web Services (Cloud Infrastructure & KMS)",
                "Google Cloud Platform (Cloud Run Serverless Compute & Cloud SQL)",
                "Cloudflare, Inc. (DDoS, WAF, Edge Network)",
                "Stripe, Inc. / Razorpay (Payment Processing)",
                "Clerk, Inc. (User Authentication & RBAC Sync)"
            ],
            "signing_url": f"https://memorybrain.ai/legal/sign/{contract_id}",
            "dispatched_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
        }

        return dpa_envelope
