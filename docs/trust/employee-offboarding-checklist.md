---
title: Employee & Contractor Offboarding Checklist
description: Mandatory security protocol for credential revocation and asset recovery within 24 hours of departure.
---

# Employee & Contractor Offboarding Protocol

## 1. Timing & Accountability
- **Accountable Role:** Security Officer / Compliance Lead
- **Enforcement SLA:** All credentials, keys, and access must be revoked within **24 hours** of employee or contractor separation (0 hours for involuntary terminations).

## 2. Mandatory Revocation Checklist

| Step | System / Asset | Action Required | Evidence Recorded In |
|---|---|---|---|
| 1 | **Primary SSO / Google Workspace** | Suspend account, revoke active OAuth sessions, forward emails to manager. | Vanta automated sync |
| 2 | **Clerk Identity & Dashboard** | Revoke internal workspace memberships; remove admin privileges. | Clerk Audit Log |
| 3 | **Cloud Providers (AWS / GCP)** | De-provision IAM roles, delete SSH keys, revoke temporary STS tokens. | AWS CloudTrail |
| 4 | **GitHub Organization** | Remove from memorybrain-ai organization and all private repositories. | GitHub Audit Log |
| 5 | **Database / Production Bastion** | Revoke pg_hba credentials, rotate shared developer passwords (if any). | Database access log |
| 6 | **Stripe & Razorpay Portals** | Remove user from dashboard team members. | Payment Gateway Log |
| 7 | **Physical Assets (Laptops/Tokens)** | Remote wipe mobile device management (MDM) profile; confirm return of hardware. | HR asset register |

## 3. Offboarding Verification
A sign-off record documenting the date, departing individual, revoking administrator, and timestamped confirmation is permanently archived in the compliance vault for SOC 2 sample testing.
