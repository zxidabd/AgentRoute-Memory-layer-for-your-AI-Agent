# MemoryBrain — Launch Day War Room & SRE Runbook

This runbook governs operations, staffing, and incident management during the 24-hour launch window on Show HN and Product Hunt.

---

## 1. Staffing Roles & On-Call Rotation

| Role | Primary Lead | Backup Lead | Core Responsibilities |
|---|---|---|---|
| **War Room Commander (Founder/Ops)** | Founder | Product Lead | HN/PH comment monitoring, social responses, executive communication, triage dispatch. |
| **Rapid Hotfix Lead (Backend Eng)** | Lead Backend Eng | Platform Eng | Live code fixes, reproducing bug reports, running canary deployments, CI pipeline approval. |
| **Infrastructure & SRE Watch** | DevOps / Infra Eng | Systems Eng | Real-time monitoring of Cloud Run container scaling, Cloud SQL connection pools, error rates. |
| **Developer Support & Onboarding** | DevRel / Community | Founder | Assisting developers in Discord/Slack, answering API key questions, verifying sandbox issues. |

### Shift Schedule (24-Hour Coverage - US Pacific & Eastern Sync):
- **Wave 1 (05:00 AM – 11:00 AM PT):** Peak launch momentum (HN front page window & PH opening surge). Full team active in Discord voice war room.
- **Wave 2 (11:00 AM – 05:00 PM PT):** European afternoon + US mid-day developer traffic. Hotfix deployment & live thread responses.
- **Wave 3 (05:00 PM – 11:00 PM PT):** US evening + APAC morning traffic. Shift to asynchronous monitoring with P1 paging alarms.
- **Wave 4 (11:00 PM – 05:00 AM PT):** APAC peak. Automated Better Uptime paging enabled.

---

## 2. Response Time SLAs

| Surface | Target Response Time | Action Item |
|---|---|---|
| **Show HN Comments** | **< 15 minutes** | Acknowledge technical question, provide clear architecture explanation or runbook link. |
| **Product Hunt Comments** | **< 15 minutes** | Thank hunter, offer `HUNTER90` promo code, address feature requests. |
| **GitHub Issues / Bug Reports** | **< 30 minutes** | Triage label, assign hotfix engineer, provide reproducible code snippet. |
| **Discord / Slack Help Channel** | **< 10 minutes** | Live developer debugging and sandbox key assistance. |
| **P0 / SEV-1 Site Outage** | **< 5 minutes** | Immediate public status post, trigger Cloud Run rollback or failover runbook. |

---

## 3. Rapid Bug Triage & Hotfix Protocol

When an HN or PH commenter reports a bug:

```
[Commenter Reports Bug]
          │
          ▼
1. Reproduce in Local Environment (< 10 mins)
   - Reproduce bug in tests/
   - Validate whether it affects core memory recall or SDK packaging
          │
          ▼
2. Branch & Fix (< 20 mins)
   - Create fix branch: git checkout -b fix/launch-<bug-name>
   - Implement fix with dedicated unit test
   - Run: python run_all_tests.py
          │
          ▼
3. Automated Canary Release (< 5 mins)
   - Run: ./infra/cloudrun/deploy-canary.sh
   - Validate error rate remains < 0.5%
          │
          ▼
4. Close the Loop on HN / PH (< 5 mins)
   - Reply directly to commenter: 
     "Fixed in v1.2.4! Deployed and verified. Thanks for catching that."
   - Link commit or release notes.
```

> [!TIP]
> **Community Impact of Fast Fixes:** Replying to a critical HN comment with a deployed fix within 45 minutes turns a negative critic into an active advocate on the thread.

---

## 4. Incident Response & Public Communication Playbook

If traffic spikes cause elevated latencies (>500ms) or HTTP 500 errors:

1. **Do NOT go silent:** Post immediately in the pinned HN/PH comments.
2. **Standard Transparency Statement:**
   > *"Update from the team: We are currently seeing unexpected traffic volume on our US-East cluster causing elevated latency on new signups. We've scaled our Cloud Run min instances from 2 to 10 and warmed our read replica connection pool. Active memory recall APIs remain healthy (<25ms). Tracking live status at https://status.memorybrain.ai."*
3. **Rollback Trigger:** If a new release triggers error rate $>0.5\%$, the Cloud Run canary script automatically reverts traffic to 100% stable revision without human intervention.
