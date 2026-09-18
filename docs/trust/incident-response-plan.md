---
title: Incident Response Plan
description: Operational incident classification, response workflow, containment protocols, and SLA.
---

# Enterprise Incident Response Plan

## 1. Purpose & Scope
This plan defines the procedures for detecting, triaging, containing, mitigating, and documenting security incidents impacting MemoryBrain infrastructure, multi-tenant databases, API endpoints, or customer data.

---

## 2. Severity Classification & Response SLAs

| Severity | Definition | Target Acknowledgment | Target Mitigation | Customer Notification SLA |
|---|---|---|---|---|
| **SEV-1 (Critical)** | Confirmed data breach, cross-tenant data leak, active ransomware, total API outage impacting all customers. | **< 15 minutes** | **< 2 hours** | **< 72 hours** (Mandated by GDPR / SOC 2) |
| **SEV-2 (High)** | Impairment of memory ingestion or recall for a subset of tenants; partial failure of authentication. | **< 30 minutes** | **< 4 hours** | Status page update within 1 hour; impacted customers notified within 24 hours |
| **SEV-3 (Medium)** | Non-critical component degradation (e.g. delayed usage meter sync, dashboard latency); circumvention with workaround. | **< 2 hours** | **< 1 business day** | Status page notice if customer visible |
| **SEV-4 (Low)** | Minor bug, cosmetic dashboard issue, single isolated false-positive rate limit. | **< 1 business day** | Scheduled sprint | Not required unless requested |

---

## 3. Incident Lifecycle Phases

`
   ┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌──────────────┐     ┌─────────────┐
   │ 1. DETECT   │ ──> │  2. TRIAGE   │ ──> │ 3. CONTAIN  │ ──> │ 4. ERADICATE │ ──> │ 5. POST-OP  │
   │ (Alerts/WAF)│     │ (Sev Assess) │     │ (Revoke/Iso)│     │ (Patch/Sync) │     │ (Postmortem)│
   └─────────────┘     └──────────────┘     └─────────────┘     └──────────────┘     └─────────────┘
`

### Phase 1: Detection & Reporting
- Automated triggers from Prometheus metrics (spikes in 5xx errors or auth rejections), Cloudflare WAF anomalies, or AWS GuardDuty alerts.
- Dedicated security inbox: security@memorybrain.ai.

### Phase 2: Triage & Incident Command
- The On-Call Incident Commander (CTO or designated senior engineer) assumes operational command.
- A dedicated incident channel (#incident-YYYYMMDD-event) is created.

### Phase 3: Containment
- **API Key Leak:** Immediately revoke the compromised API key via POST /v1/keys/{key_id}/revoke.
- **Tenant Isolation Breach:** Immediately isolate tenant session tokens, rotate encryption keys via KMS, and engage read-only freeze.
- **Service Attack:** Enable Cloudflare Under Attack mode and enforce IP rate-limiting.

### Phase 4: Eradication & Recovery
- Deploy verified hotfix via automated CI/CD pipeline (PR review + 100% test pass required).
- Restore database to last known clean transaction point if integrity was impacted.
- Verify system health via automated regression suite (un_all_tests.py).

### Phase 5: Post-Mortem & Corrective Action
- A formal Blameless Post-Mortem document is published within 5 business days detailing:
  - Root cause analysis (5 Whys).
  - Timeline of events.
  - Corrective preventive controls added to Vanta continuous monitoring.
