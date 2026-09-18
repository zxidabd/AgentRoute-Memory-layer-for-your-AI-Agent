# Show HN: Launch Kit & Community Playbook

**Target Submission Window:** Tuesday, 08:00 AM Eastern Time (12:00 PM UTC)  
**Format:** Text Post (Ask/Show HN)  
**Canonical URL:** `https://news.ycombinator.com/submit`

---

## 1. Post Title & Submission Text

### Title:
```text
Show HN: MemoryBrain – Persistent, sub-25ms memory layer for AI agents
```

### URL / Text Body:
```text
Hey HN,

We're the builders of MemoryBrain (https://memorybrain.ai). We built a managed, low-latency persistent memory layer that lets LLM agents remember users, past tool outputs, and long-term preferences across sessions in two lines of code.

### The Problem:
Every agent builder runs into the same wall: LLMs are stateless. When you want an agent to remember things across conversations, you usually end up with one of two bad options:
1. Shoving raw chat logs into the context window until you hit token limits, latency spikes (>2 seconds), and huge API bills.
2. Spinning up a raw vector database (Pinecone, Qdrant, pgvector) and writing your own chunking heuristics, embedding pipelines, hybrid search ranking, user isolation layers, and encryption.

Most teams spend weeks reinventing this plumbing rather than building their core agent logic.

### What MemoryBrain does:
MemoryBrain is purpose-built for agent memory. It provides:
- Sub-25ms hybrid semantic recall (combining dense vector embeddings with BM25 sparse keyword matching for exact IDs, codes, and names).
- AES-256 envelope encryption at rest on all memory payloads.
- Multi-tenant workspace isolation (Owner/Admin/Member RBAC and hashed `mb_live_...` API keys).
- Native Model Context Protocol (MCP) server for Claude Desktop and Cursor.
- Zero-dependency Python and TypeScript SDKs.
- 99.95% HA multi-AZ infrastructure with primary write and async read replica offloading.

### Quick Example (Python):
```python
from memorybrain import MemoryBrain

mb = MemoryBrain(api_key="mb_live_...")

# Store an observation or preference
mb.store(user_id="user_482", content="Prefers TypeScript, deploys to Fly.io, hates verbose comments.")

# Recall relevant context before prompting (<25ms)
memory = mb.recall(user_id="user_482", query="deployment preferences")
print(memory["context"])
```

### Interactive Playground & Open SDKs:
- Live Interactive Playground (no signup required): https://memorybrain.ai/playground
- Python SDK: `pip install memorybrain` (GitHub: https://github.com/memorybrain/memorybrain-python)
- TypeScript SDK: `npm install @memorybrain/sdk` (GitHub: https://github.com/memorybrain/memorybrain-ts)
- Public OpenAPI 3.1 Contract & Docs: https://docs.memorybrain.ai

We have a generous free tier (Starter: 1,000 memories, 10,000 recalls/mo, zero credit card required).

We’d love HN’s brutal, honest feedback on our architecture, developer ergonomics, and latency tradeoffs. We'll be here all day answering questions and pushing live hotfixes!
```

---

## 2. First Maker Comment (Deep Technical Architecture)

Post this immediately after submitting the Show HN post:

```text
Hi everyone, one of the founders here. A bit more detail on what’s under the hood for those interested in the architecture:

1. Hybrid Retrieval Engine:
Pure dense vector search fails unexpectedly on developer strings (e.g. error codes like `ERR_SOCKET_TIMEOUT`, UUIDs, or exact product names). We run a hybrid pipeline: dense cosine similarity for conceptual memory + BM25 sparse keyword indexing for exact identifiers, fused via Reciprocal Rank Fusion (RRF). This brings precision from ~74% to >94% without requiring separate vector + full-text databases on the client side.

2. Latency & Infrastructure:
Context retrieval sits directly on the critical path of an agent's response loop. If memory recall takes 150ms, the entire agent feels sluggish. MemoryBrain runs on containerized multi-AZ Cloud Run instances backed by Cloud SQL PostgreSQL with automated read replica routing. High-frequency `/v1/context` queries route to async replicas, keeping p95 recall latency under 22ms.

3. Security & Immutability:
Because agents frequently store sensitive context (user preferences, account credentials, internal workflows), every payload is encrypted using AES-256 Fernet ciphers before hitting disk. Furthermore, our audit trail (`memory_versions`) employs database-level immutability guards that reject SQL UPDATE and DELETE statements, providing out-of-the-box SOC 2 compliance evidence.

4. Model Context Protocol (MCP):
Rather than forcing every developer into proprietary SDKs, we built a native MCP server for Claude Desktop and Cursor (`npx -y @memorybrain/mcp-server`). You can point Cursor or Claude Desktop to MemoryBrain and get cross-session agent memory in 30 seconds without writing a line of backend code.

5. Pricing Transparency:
- Starter: Free forever ($0), 5,000 active memories, 25k recalls/mo. No credit card required.
- Growth: $49/mo, 50k memories, 500k recalls/mo, team projects.
- Scale: $249/mo, 1M memories, 5M recalls/mo, dedicated support.
- Enterprise: Custom / $1,999/mo, dedicated VPC, SOC 2, HIPAA, custom SLA.

Happy to dive deep into anything — query routing, failure handling, embedding models, or why we chose our storage model.
```

---

## 3. Anticipated HN Technical Questions & Battle-Tested Answers

### Q1: "Why not just use pgvector / Chroma / Pinecone yourself?"
> **Answer:** You absolutely can, and for simple hobby scripts, you probably should! But in production, raw vector databases only give you nearest-neighbor search over math vectors. You still have to write and maintain: (1) chunking heuristics, (2) embedding pipelines and backfill workers, (3) hybrid search fusing BM25 with dense vectors so exact names/error codes match, (4) user multi-tenancy and encryption at rest, (5) caching layers so your agents don't block for 150ms on every prompt, and (6) tamper-proof audit trails for compliance. MemoryBrain replaces that entire 4-week infrastructure engineering project with a 2-line SDK call.

### Q2: "What happens to my data? Can I export it?"
> **Answer:** You own 100% of your data. We offer full JSON/CSV export via `GET /v1/export` at any time with zero vendor lock-in. We do not use your memories to train foundation models, all fields are AES-256 encrypted at rest, and we support GDPR Article 17 "Right to be Forgotten" hard deletes within 60 seconds.

### Q3: "What embedding model are you using, and what about dimension drift?"
> **Answer:** We currently use normalized 384-dimensional dense embeddings optimized for low-latency CPU/edge inference combined with sparse BM25 indexing. Because agent memories are short, high-salience propositions rather than 50-page PDF chunks, 384-d captures rich semantic nuance while keeping vector comparison operations under 2ms. If an embedding model is updated, we handle versioning and asynchronous re-indexing under the hood without breaking recall APIs.

### Q4: "Can I self-host this?"
> **Answer:** Our Python and TypeScript SDKs are fully open-source under Apache 2.0. For enterprises with strict regulatory needs (banking, defense, healthcare), we offer a Bring-Your-Own-Cloud (BYOC) single-tenant deployment that installs into your own AWS/GCP VPC with your own KMS keys.
