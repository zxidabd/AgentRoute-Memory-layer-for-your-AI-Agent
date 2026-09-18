# MemoryBrain — Product Roadmap & Feature Prioritization Matrix

This document outlines MemoryBrain's public/customer-facing roadmap and the RICE scoring model used to evaluate customer feedback against core platform goals.

---

## 1. Product Roadmap: Now, Next, Later

```
        NOW (Q3)                       NEXT (Q4)                      LATER (Q1+)
┌─────────────────────────┐    ┌─────────────────────────┐    ┌─────────────────────────┐
│ • Custom Enterprise     │    │ • Graph-Based Relational│    │ • Fine-Tuned Embedding  │
│   Limits & Quotas       │    │   Entity Memory Links   │    │   Adapters per Tenant   │
│                         │    │                         │    │                         │
│ • Advanced MCP Server   │    │ • Local-First Edge CDN  │    │ • Multi-Region Sync     │
│   Streaming & Tools     │    │   Cache for Prompts     │    │   (EU + US + APAC)      │
│                         │    │                         │    │                         │
│ • Self-Serve Team Seat  │    │ • Automated Memory      │    │ • Bring-Your-Own-LLM    │
│   Invites & SAML SSO    │    │   Consolidation Workers │    │   Memory Extraction     │
└─────────────────────────┘    └─────────────────────────┘    └─────────────────────────┘
```

### Detailed Milestone Breakdown:

#### A. NOW (Immediate Focus — Next 60 Days):
1. **Custom Enterprise Limits & Dedicated Quotas:**
   - Allow enterprise organizations to negotiate bespoke limits on `monthly_quota_memories` and `rate_limit_rpm` beyond the standard Scale tier via the billing management dashboard.
2. **Advanced Model Context Protocol (MCP) Extensions:**
   - Add streaming responses and dynamic tool definitions for Claude Desktop and Cursor.
   - Expose agent memory reflection and auto-pruning tools directly in MCP toolsets.
3. **Self-Serve Team Seat Invites & SAML SSO:**
   - Expand Clerk organization webhooks to support enterprise SAML/Okta identity providers for single-sign-on.

#### B. NEXT (Medium Term — 60 to 120 Days):
1. **Graph-Based Relational Entity Memory Links:**
   - Link memories as nodes in a knowledge graph (e.g. `User -> Prefers -> TypeScript` and `User -> WorksAt -> Stripe`).
   - Enable multi-hop entity traversal in `/v1/context` queries.
2. **Local-First Edge CDN Caching:**
   - Cloudflare Workers caching layer for ultra-frequent user context queries, dropping p95 recall latency from 22ms to <8ms for edge agents.
3. **Automated Memory Consolidation & De-duplication:**
   - Background LLM cron worker that periodically condenses 10 fragmented conversational memories into 1 crisp canonical profile fact.

#### C. LATER (Longer Term — 120+ Days):
1. **Fine-Tuned Domain Embedding Adapters:**
   - Customer-trained Low-Rank Adaptation (LoRA) projection heads for specialized medical, legal, and financial agent vocabularies.
2. **Multi-Region Live Active-Active Sync:**
   - Automated bi-directional replication between US and EU regions with localized data residency guarantees.
3. **Bring-Your-Own-LLM Memory Extraction:**
   - Allow customers to specify their own OpenAI/Anthropic/Gemini API keys for fact extraction workers.

---

## 2. Feature Prioritization Framework (RICE Scoring)

Features requested through support tickets, sales calls, or GitHub issues are ranked using the RICE formula:

$$\text{RICE Score} = \frac{\text{Reach} \times \text{Impact} \times \text{Confidence}}{\text{Effort}}$$

| Factor | Definition | Scoring Scale |
|---|---|---|
| **Reach (R)** | Number of active organizations impacted per quarter. | Exact count (e.g. 15, 100, 500) |
| **Impact (I)** | Impact on retention, conversion, or developer UX. | 3 = Massive, 2 = High, 1 = Medium, 0.5 = Low |
| **Confidence (C)** | How certain we are about the problem and technical solution. | 100% = High, 80% = Medium, 50% = Low |
| **Effort (E)** | Engineering person-weeks required to design, test, and ship. | 0.5, 1, 2, 4 weeks |

### Example Roadmap Prioritization Ranking:

| Feature Candidate | Reach | Impact | Confidence | Effort | RICE Score | Status |
|---|---|---|---|---|---|---|
| **Custom Enterprise Limits** | 20 orgs | 3 (Closes $2k/mo deals) | 100% | 1 week | **60.0** | **IN PROGRESS (NOW)** |
| **Advanced MCP Server Streaming** | 150 orgs | 2 (High dev delight) | 90% | 1.5 weeks | **180.0** | **IN PROGRESS (NOW)** |
| **Graph-Based Entity Memory** | 80 orgs | 2.5 (Major differentiator) | 70% | 3 weeks | **46.7** | **PLANNED (NEXT)** |
| **Edge CDN Caching** | 200 orgs | 1.5 (Speed boost) | 80% | 2 weeks | **120.0** | **PLANNED (NEXT)** |
