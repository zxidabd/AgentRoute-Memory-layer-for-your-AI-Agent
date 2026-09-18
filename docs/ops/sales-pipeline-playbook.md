# MemoryBrain — Sales Pipeline Playbook & Inbound Triggers

This playbook defines our sales pipeline stages, inbound qualification triggers, and deal progression workflows for converting self-serve developers into high-contract-value Enterprise customers.

---

## 1. CRM Pipeline Stages & Exit Criteria

```
[Lead] ──► [Demo Scheduled] ──► [POC / Trial] ──► [Contract / DPA] ──► [Closed-Won]
   │              │                   │                  │
   └──────────────┴───────────────────┴──────────────────┴──► [Closed-Lost / Disqualified]
```

| Stage | Definition | Required Actions to Advance |
|---|---|---|
| **1. Lead** | Inbound signup, contact form, or outbound reply matching ICP profile. | Verify company funding, agent product, and current memory architecture. |
| **2. Demo** | 20-minute technical architecture walk-through with Founder or Sales Lead. | Understand agent latency bottlenecks, token spend, and compliance requirements. |
| **3. Trial / POC** | Prospect active on 30-day Enterprise POC branch or sandbox. | Confirm integration of Python/TS SDK or MCP; verify sub-25ms recall. |
| **4. Contract / DPA** | MSA, DPA, and custom pricing review with procurement or security team. | Send standard DPA (`docs/trust/dpa-template.md`); address security questionnaires. |
| **5. Closed-Won** | Annual or multi-month contract countersigned; Stripe Invoicing scheduled. | Hand off to Customer Success; set up dedicated Slack Connect channel. |

---

## 2. Automated Inbound Enterprise Upsell Triggers

We monitor self-serve account activity to detect high-growth prospects before they reach out. The following automated telemetry signals trigger proactive outreach:

| Inbound Telemetry Signal | Trigger Threshold | Immediate Action |
|---|---|---|
| **Memory Quota Saturation** | Org reaches **$>80\%$ of Scale tier quota** (800,000 memories). | Automated founder email offering dedicated database cluster and custom pricing. |
| **Rapid API Key Generation** | Org generates **$>5$ project-scoped API keys** in 7 days. | Flags team expansion; invite lead to multi-seat enterprise demo. |
| **Corporate Domain Signup** | Signups with `@salesforce.com`, `@cisco.com`, or tier-1 AI labs. | Immediate priority research; send personalized intro within 2 hours. |
| **High Daily Overage Run-Rate** | Org incurs **$150+ in daily overage charges** on Growth/Scale. | Notify founder that migrating to Enterprise annual plan saves 40% on unit costs. |

---

## 3. Enterprise Qualification Criteria (BANT Matrix)

Before scheduling engineering time for custom Bring-Your-Own-Cloud (BYOC) or single-tenant deployments, verify:

1. **Budget:** Can the prospect support minimum contract size ($1,999/mo or $20k/yr commitment)?
2. **Authority:** Is the contact the CTO, VP of AI Engineering, or Head of Platform?
3. **Need:** Does the agent platform have $>50,000$ daily active users or strict HIPAA/SOC 2 requirements?
4. **Timeline:** Are they deploying to production within 60 days?

---

## 4. Weekly Pipeline Review Cadence
- **Timing:** Every Monday at 09:00 AM PT (45 minutes).
- **Attendees:** Founder, Founding CS/DevRel, Lead Backend Engineer.
- **Agenda:**
  1. Review Stage 4 (Contract) deals closing this week.
  2. Review Stage 3 (POC) technical blockers and customer feature requests.
  3. Triage top 10 self-serve orgs flagged by usage triggers.
  4. Review Closed-Lost post-mortems and feed feature gaps into the Product Roadmap.
