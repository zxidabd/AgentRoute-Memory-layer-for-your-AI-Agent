# MemoryBrain — Customer Support Operations Handbook & SLA Matrix

This handbook defines support channels, response time SLAs, ticket triage workflows, bug escalation paths, and the canonical seeded FAQ for MemoryBrain customer operations.

---

## 1. Support Channels & Intake Routing

| Customer Tier | Primary Intake Channel | Secondary Channel | Target First Response SLA |
|---|---|---|---|
| **Starter (Free)** | Public Discord Community (`#dev-support`) | Email (`support@memorybrain.ai`) | **< 24 Hours** (Business Days) |
| **Growth ($49/mo)** | Dedicated Email (`support@memorybrain.ai`) | Discord VIP Role | **< 12 Hours** (7 Days/Week) |
| **Scale ($249/mo)** | Shared Slack Connect / Discord Channel | Priority Support Email | **< 6 Hours** (24/7 P1, Business P2) |
| **Enterprise ($1,999/mo)** | Dedicated Shared Slack Connect + PagerDuty P1 | Private Account Manager | **< 4 Hours** (SLA Guaranteed; <30m for SEV-1) |

---

## 2. Ticket Triage & Severity Matrix

Every inbound support ticket is tagged with a severity level upon arrival:

```
[Inbound Support Ticket]
          │
          ├── SEV-1: Outage / Data Loss / Recall Latency > 1000ms
          │     └── Immediate PagerDuty page to On-Call SRE (<15m SLA)
          │
          ├── SEV-2: Functional Regression / Auth Failure / SDK Import Error
          │     └── Triaged to Backend Engineer on call (<2h SLA)
          │
          ├── SEV-3: Billing / Plan Upgrade / Quota Increase
          │     └── Handled by Founder / Support Lead (<6h SLA)
          │
          └── SEV-4: How-to Question / Framework Integration / Feature Request
                └── Answered with Docs link or added to Seeded FAQ (<24h SLA)
```

---

## 3. Engineering Bug Escalation Protocol

When a ticket reveals a reproducible defect in the API, SDKs, or MCP server:
1. **Isolate Reproduction:** Support agent creates a minimal reproduction script in `tests/` or a curl snippet.
2. **File Issue:** File a GitHub Issue with label `bug` and severity badge (`sev-1` through `sev-3`).
3. **Notify Engineer:** Post in `#eng-hotfixes` Slack channel with ticket URL and reproduction script.
4. **Customer Communication:** Inform the customer within 1 hour:
   > *"We've reproduced this issue and isolated it to our query ranker cache. Our engineering team is testing a hotfix now. We'll update you as soon as the patch is deployed."*
5. **Close Loop:** Once the canary deployment passes, send the customer release notes and confirm resolution.

---

## 4. Canonical Seeded FAQ (From Design Partner Onboarding)

### Q1: "How do I authenticate the SDK in local development vs production?"
> **Answer:** In local development, you can use any test key with prefix `mb_dev_...` or omit auth if running the local sandbox server. In production, export `MEMORYBRAIN_API_KEY="mb_live_..."`. Both Python and TypeScript SDKs automatically read this environment variable without requiring manual parameters: `mb = MemoryBrain()`.

### Q2: "Can I use MemoryBrain with Cursor and Claude Desktop without writing Python code?"
> **Answer:** Yes! MemoryBrain provides an official Model Context Protocol (MCP) server. Run `npx -y @memorybrain/mcp-server` and add it to your `claude_desktop_config.json` or Cursor settings. It automatically exposes `recall_memory`, `store_memory`, and `get_profile` tools.

### Q3: "What happens if our agent hits our plan's monthly memory quota?"
> **Answer:** On the free Starter tier, additional writes receive HTTP 429 Quota Exceeded while recall queries continue functioning normally. On Growth and Scale tiers, overages are automatically permitted ($1.00 per 1,000 memories) so your production agent never suffers downtime during traffic surges.

### Q4: "How does MemoryBrain ensure low latency on context recall (<25ms)?"
> **Answer:** We run a dual database architecture: writes are handled by our primary PostgreSQL instance, while high-frequency `/v1/context` queries are automatically routed to asynchronous read replicas with local LRU embedding caches, ensuring median latency remains under 20ms.
