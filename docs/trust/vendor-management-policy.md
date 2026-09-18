---
title: Vendor Risk Management Policy
description: Framework for evaluating, onboarding, and monitoring third-party vendors and critical software dependencies.
---

# Vendor Risk Management Policy

## 1. Policy Statement
MemoryBrain evaluates all third-party vendors and software dependencies to prevent supply-chain vulnerabilities, data compromise, and compliance drift.

## 2. Vendor Risk Classification

| Tier | Definition | Examples | Minimum Requirements |
|---|---|---|---|
| **Tier 1 (Critical)** | Hosts or processes customer memory statements, credentials, or production databases. | AWS, Cloudflare, Clerk | SOC 2 Type II or ISO 27001 report, signed DPA with SCCs, annual security review. |
| **Tier 2 (Operational)** | Handles customer billing metadata or communication without processing memory statements. | Stripe, Razorpay, Resend, Vanta | PCI DSS / SOC 2 certification, signed DPA, MFA enforcement on accounts. |
| **Tier 3 (Commodity)** | Internal productivity tools with no access to production infrastructure or customer memory. | Slack, GitHub, Google Workspace | SSO/MFA required, least-privilege role assignment. |

## 3. Onboarding & Annual Review Protocol
1. **Security Due Diligence:** Pre-acquisition questionnaire evaluating encryption at rest/transit, incident disclosure policies, and data residency.
2. **Contractual Protections:** All vendors handling customer data must execute a Data Processing Agreement (DPA) and agree to 72-hour breach notification terms.
3. **Annual Audit:** Annual review of SOC 2 / ISO certifications recorded directly in Vanta.
