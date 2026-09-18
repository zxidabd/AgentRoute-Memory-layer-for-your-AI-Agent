---
title: 99.95% Uptime SLA & High-Availability Operations Runbook
description: SLA calculation, error budgets, Better Uptime monitoring, on-call escalation, and manual SLA credit workflows.
---

# 99.95% High-Availability SLA & Operations Runbook

## 1. Service Level Agreement (SLA) Commitments

MemoryBrain contractually guarantees **99.95% Monthly Uptime** for all Growth and Enterprise production workspaces.

`
+------------------+-------------------------+------------------------+
| Commitment       | Allowed Downtime/Month  | Allowed Downtime/Year  |
+------------------+-------------------------+------------------------+
| 99.95% Uptime    | 21 minutes, 54 seconds  | 4 hours, 22 minutes    |
+------------------+-------------------------+------------------------+
`

### SLA Credit Schedule
Customers experiencing service downtime below guaranteed availability may submit an SLA credit claim:

| Monthly Uptime Percentage | Service Credit Percentage |
|---|---|
| **99.90% – < 99.95%** | **10% of monthly invoice** |
| **99.00% – < 99.90%** | **25% of monthly invoice** |
| **< 99.00%** | **50% of monthly invoice** |

*SLA credits are processed manually by the support engineering team via the Stripe billing dashboard upon review of outage logs within 30 days of the incident.*

---

## 2. Better Uptime & Monitoring Architecture

MemoryBrain utilizes **Better Uptime** (Better Stack) for synthetic uptime monitoring, multi-region probes, and automatic on-call escalation.

### Probe Configurations
1. **Primary Liveness Probe:**
   - URL: https://api.memorybrain.ai/healthz/liveness
   - Scrape Interval: **30 seconds**
   - Probe Locations: US East (N. Virginia), US West (Oregon), Europe (Frankfurt), Asia (Tokyo), Australia (Sydney).
   - Alert Trigger: 2 consecutive failures across any 2 regions.
2. **Traffic Readiness Probe:**
   - URL: https://api.memorybrain.ai/healthz/readiness
   - Scrape Interval: **60 seconds**
   - Verifies Primary PostgreSQL read/write state and Read-Replica sync status.

---

## 3. On-Call Escalation Matrix

`
       ┌───────────────────────────────┐
       │   Better Uptime Alert Trigger  │
       │   (2 Consecutive 5xx Probes)  │
       └──────────────┬────────────────┘
                      │ 0-5 mins
                      ▼
       ┌───────────────────────────────┐
       │   Tier 1: Primary On-Call Eng │
       │   (SMS, PagerDuty, Phone Call)│
       └──────────────┬────────────────┘
                      │ Unacknowledged > 10 mins
                      ▼
       ┌───────────────────────────────┐
       │   Tier 2: Secondary On-Call   │
       │   (Infrastructure Lead)       │
       └──────────────┬────────────────┘
                      │ Unacknowledged > 15 mins
                      ▼
       ┌───────────────────────────────┐
       │   Executive Escalation (CTO)  │
       │   Public Status Page Alert    │
       └───────────────────────────────┘
`

---

## 4. Disaster Recovery & Backup Verification
- **Tiered Retention:**
  - **Hourly:** Retained for 7 days
  - **Daily:** Retained for 35 days
  - **Weekly:** Retained for 12 months (cold object storage)
- **Automated Restore Drill:** Executed automatically each week via scripts/restore_drill.py to restore the latest production snapshot into a scratch database and verify memory statement decryption.
