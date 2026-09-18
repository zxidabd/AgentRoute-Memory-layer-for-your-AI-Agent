# MemoryBrain — Master Operations Handbook

Welcome to the central operating manual for running MemoryBrain. This handbook connects all operational disciplines across customer support, sales, finance, hiring, product, churn retention, security, and infrastructure scaling into a single, discoverable system.

---

## 1. Directory of Operating Systems

```
                               ┌─────────────────────────────┐
                               │  MemoryBrain Operations Hub │
                               └──────────────┬──────────────┘
            ┌───────────────────┬─────────────┼─────────────┬───────────────────┐
            ▼                   ▼             ▼             ▼                   ▼
      Customer Support     Sales & CRM    Finance & ASC   Hiring & CS    Product Roadmap
        & SLA Matrix       Pipelines         606 SOP        Scorecard      & RICE Matrix
     [Section 2.A]        [Section 2.B]   [Section 2.C]   [Section 2.D]    [Section 2.E]
            │                   │             │             │                   │
            └───────────────────┴─────────────┼─────────────┴───────────────────┘
                                              ▼
                                Security, Churn & Infra Scaling
                                  [Sections 2.F, 2.G, 2.H]
```

| Area | Primary Focus | Master SOP Document | Process Owner | Cadence |
|---|---|---|---|---|
| **A. Customer Support** | Triage, SLAs, and developer FAQ | [`docs/ops/support-operations-handbook.md`](file:///C:/Agent-memory-layer/docs/ops/support-operations-handbook.md) | Support / DevRel Lead | Continuous (Daily SLA) |
| **B. Sales Pipeline** | Inbound triggers & deal progression | [`docs/ops/sales-pipeline-playbook.md`](file:///C:/Agent-memory-layer/docs/ops/sales-pipeline-playbook.md) | Founder / Sales Lead | Weekly Review (Mon 9 AM) |
| **C. Financial Ops** | ASC 606 Rev Rec, close, unit economics | [`docs/ops/finance-and-rev-rec.md`](file:///C:/Agent-memory-layer/docs/ops/finance-and-rev-rec.md) | Fractional Bookkeeper / CEO | Monthly Close (Day 5) |
| **D. Hiring & Talent** | First hire scorecard & hiring triggers | [`docs/ops/hiring-customer-success-lead.md`](file:///C:/Agent-memory-layer/docs/ops/hiring-customer-success-lead.md) | Founder | Event-Driven (Triggered) |
| **E. Product Roadmap** | RICE scoring & feature backlog | [`docs/ops/product-roadmap.md`](file:///C:/Agent-memory-layer/docs/ops/product-roadmap.md) | Product / Eng Lead | Monthly Review |
| **F. Churn Prevention** | Algorithmic usage health monitoring | [`agent_memory/analytics/health_score.py`](file:///C:/Agent-memory-layer/agent_memory/analytics/health_score.py) | Customer Success Lead | Automated / Daily |
| **G. Continuous Security**| Vanta triage & annual pen-tests | [`docs/ops/security-continuous-monitoring.md`](file:///C:/Agent-memory-layer/docs/ops/security-continuous-monitoring.md) | Security / Platform Lead | Weekly Triage (Tue 10 AM) |
| **H. Infra Scaling** | Capacity headroom & EU triggers | [`docs/ops/infra-scaling-playbook.md`](file:///C:/Agent-memory-layer/docs/ops/infra-scaling-playbook.md) | SRE / DevOps Lead | Event-Driven (5x Traffic) |
| **I. High-Availability** | 99.95% SLA & Failover Runbook | [`docs/trust/uptime-sla-runbook.md`](file:///C:/Agent-memory-layer/docs/trust/uptime-sla-runbook.md) | On-Call SRE | 24/7 Monitoring |

---

## 2. Core Operational Cadences

To keep the company moving forward without endless ad-hoc syncs, we adhere to four rhythmic operating meetings:

1. **Daily Standup & Support Triage (15 mins, async via Slack):**
   - Review open SEV-1/SEV-2 tickets.
   - Review accounts flagged by the **Usage Health Score** dashboard.
2. **Weekly Commercial & Pipeline Review (Monday 09:00 AM PT, 45 mins):**
   - Active sales deals in Stages 3 (Trial) and 4 (Contract).
   - High-usage self-serve accounts ready for enterprise outreach.
3. **Bi-Weekly Product & Engineering Planning (Wednesday 10:00 AM PT, 60 mins):**
   - RICE prioritization of new feature requests from support and sales.
   - Sprint backlog review and release target alignment.
4. **Monthly Financial Close & Unit Economics Audit (First Friday of Month, 60 mins):**
   - Review gross margin, COGS per 1M recalls, and GAAP deferred revenue schedule.
   - Reconcile Stripe/Razorpay payouts and cloud infrastructure costs.
