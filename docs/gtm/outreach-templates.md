# MemoryBrain — Founder Outreach Templates & Sequences

These message templates are designed for personalized 1-on-1 outreach to the 30 target ICP founders. Each template articulates the pain point, provides a concrete technical solution, offers **90-day complimentary Growth-tier access ($147 value)**, and includes a frictionless 2-minute code snippet.

---

## 1. Cold Email Sequence (Recommended Primary Channel)

### Subject Options:
- *Option A:* Persistent memory for {{Company}} agents? (90-day access)
- *Option B:* Fixing {{Company}}'s agent context loss without vector DB plumbing
- *Option C:* Quick question re: {{Company}} agent memory architecture

### Email Body:
```text
Hi {{First_Name}},

Saw that you're building {{Company}} — love the agent architecture you’ve put together for {{Product_Focus}}.

One consistent hurdle we hear from founders building in {{Vertical}} is that agents remain fundamentally stateless between sessions. Bolting on raw Pinecone/pgvector means managing chunking heuristics, embedding sync pipelines, and latency budgets (which kills UX when responses exceed 200ms).

We built MemoryBrain (https://memorybrain.ai) to solve this: a managed, persistent memory layer for AI agents with sub-25ms semantic recall, hybrid BM25 + dense ranking, and AES-256 field encryption.

It drops into existing agents in 2 lines:

from memorybrain import MemoryBrain
mb = MemoryBrain(api_key="{{Pre_Provisioned_API_Key}}")

# Store user nuance or past decision
mb.store(user_id="{{Sample_User_ID}}", content="User prefers FastAPI over Flask and deployed to us-east-1.")

# Recall before LLM prompt assembly (<25ms)
ctx = mb.recall(user_id="{{Sample_User_ID}}", query="deployment stack preference")

We're onboarding 10 design partners ahead of our public Show HN launch next month. I’d love to grant {{Company}} 90 days of complimentary access to our Growth tier (50k memories, 500k recalls/mo, $147 value) in exchange for raw technical feedback and a 1-sentence quote if you find it valuable.

Are you open to a 15-minute technical demo this Thursday or Friday? Alternatively, your pre-activated API key is in the snippet above if you'd prefer to drop it into a test branch first.

Best,
[Founder Name]
Founder & CEO, MemoryBrain
https://memorybrain.ai | [Direct Calendar Link]
```

---

## 2. LinkedIn InMail Template

```text
Hi {{First_Name}},

Loved your recent post on scaling {{Company}}'s agent workflows. 

Quick technical question: how are you currently handling persistent cross-session memory for your agents? Most teams we speak with find that raw vector databases add 150ms+ latency and require too much custom chunking/metadata plumbing.

We built MemoryBrain (https://memorybrain.ai) — a sub-25ms persistent memory API that provides hybrid search, user profiling, and AES-256 encrypted storage in 2 lines of Python/TypeScript (or native MCP for Claude/Cursor).

We're offering 90 days of complimentary Growth-tier access (50k memories, $147 value) to select AI agent founders ahead of our Show HN launch in exchange for candid engineering feedback.

Would you be open to checking out a 3-minute sandbox demo?

Best,
[Founder Name]
```

---

## 3. Twitter / X DM Template (Fast & Casual)

```text
Hey {{First_Name}}! Huge fan of what you're building at {{Company}}. 

Saw you're expanding your agent capabilities — wanted to share a quick tool we just built: MemoryBrain (https://memorybrain.ai). It gives AI agents persistent long-term memory in 2 lines of code with <25ms recall, full SOC-2 ready encryption, and zero vector DB maintenance.

We’re giving 10 agent founders 90 days free on our Growth tier for early feedback. Would love to send over a pre-provisioned API key if you or your lead eng want to test it in a branch. Let me know!
```

---

## 4. Design Partner Agreement Terms (90-Day Complimentary Access)
1. **Tier Granted:** Growth Tier ($49/month value, 100% discount applied for 90 days).
2. **Quota:** 50,000 active memories, 500,000 monthly recall queries, 5 projects, 10 API keys.
3. **Commitment from Partner:**
   - Integrate MemoryBrain into a staging or production agent within 14 days.
   - Participate in one 20-minute feedback call or async Slack debrief.
   - Provide a 1–2 sentence quote and company logo permission upon successful deployment.
4. **Post-90 Days:** Partner retains choice to convert to paid Growth plan at a grandfathered 20% lifetime discount or transition to the free Starter tier with zero data loss.
