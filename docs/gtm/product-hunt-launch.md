# Product Hunt: Launch Kit & Maker Assets

**Target Launch Time:** Tuesday, 12:01 AM Pacific Time (08:01 AM UTC) — 1 week following Show HN  
**Platform URL:** `https://www.producthunt.com/posts/new`

---

## 1. Product Listing Details

| Field | Content |
|---|---|
| **Product Name** | MemoryBrain |
| **Tagline** | Persistent long-term memory for AI agents in 2 lines of code |
| **Primary Category** | Developer Tools, Artificial Intelligence, API |
| **Secondary Category** | SaaS, Productivity, Open Source |
| **Website URL** | `https://memorybrain.ai` |
| **Docs URL** | `https://docs.memorybrain.ai` |
| **Interactive Playground** | `https://memorybrain.ai/playground` |

---

## 2. Description Copy

### Short Description (300 characters):
MemoryBrain gives your LLM agents persistent human-like memory across sessions. Store user preferences, past tool outputs, and context in 2 lines of code with sub-25ms hybrid recall, AES-256 encryption, and native Claude/Cursor MCP support.

### Long Description:
Building AI agents that remember users across sessions shouldn't require managing vector databases, embedding pipelines, chunking heuristics, and encryption keys.

MemoryBrain is a developer-first memory layer engineered for production AI agents.
- ⚡ **Sub-25ms Hybrid Semantic Recall:** Blends dense vector search with sparse BM25 matching so your agents never forget exact names, IDs, or conceptual nuances.
- 🔒 **Enterprise-Grade Security:** Zero-plaintext storage with AES-256 Fernet envelope encryption and SOC 2 Type I readiness.
- 🔌 **Native MCP Server:** Connect directly to Claude Desktop and Cursor in 30 seconds via Model Context Protocol (`npx -y @memorybrain/mcp-server`).
- 🛠️ **Lightweight SDKs:** Zero-dependency Python (`pip install memorybrain`) and TypeScript (`npm install @memorybrain/sdk`) packages.
- 🚀 **99.95% High-Availability:** Multi-AZ serverless compute backed by primary write and read replica routing.

---

## 3. Maker Opening Comment

```text
👋 Hey Product Hunt community!

I’m [Founder Name], maker of MemoryBrain.

Over the past year, we noticed every developer building AI agents hit the same frustrating wall: LLMs are fundamentally stateless. As soon as a user closes a chat window or opens a new session, the agent forgets their preferences, past bugs, hardware setup, and conversational history.

The default workaround is either stuffing massive chat logs into context windows (expensive, slow, token-heavy) or spinning up a raw vector database and spending weeks writing custom chunking scripts, embedding sync workers, and caching layers.

We built MemoryBrain to give any agent persistent, human-like memory in two lines of code:

from memorybrain import MemoryBrain
mb = MemoryBrain()
mb.store(user_id="user_123", content="Prefers dark mode and builds with Next.js")
context = mb.recall(user_id="user_123", query="preferred stack")

### Special Product Hunt Offer:
We have a generous free tier for developers (1,000 memories, 10k recalls/mo), but for the PH community today, use code **HUNTER90** inside your dashboard to get **90 days of our Growth Tier (50,000 memories, 500k recalls/mo, $147 value) 100% free**.

Try our live interactive playground (no signup required):
👉 https://memorybrain.ai/playground

We’d love your feedback, bug reports, and feature requests. What is your AI agent forgetting today?
```

---

## 4. Media Gallery Asset Specifications

| Asset # | Name | Dimensions | Content & Description |
|---|---|---|---|
| **Thumbnail** | `ph_icon.png` | 240 x 240 px | High-contrast glowing neural network brain icon with indigo/violet accents. |
| **Slide 1 (Hero)** | `ph_slide1_hero.png` | 1270 x 760 px | "Give Your AI Agent Long-Term Memory in 2 Lines of Code" with split-screen showing stateless failure vs MemoryBrain recall. |
| **Slide 2 (MCP)** | `ph_slide2_mcp.png` | 1270 x 760 px | "Native Model Context Protocol (MCP) for Claude & Cursor" showing Claude Desktop recalling developer preferences. |
| **Slide 3 (Latency)** | `ph_slide3_benchmarks.png` | 1270 x 760 px | "Sub-25ms Hybrid Recall" latency chart comparing MemoryBrain (18ms) against raw Pinecone/OpenAI embeddings (145ms). |
| **Slide 4 (Dashboard)** | `ph_slide4_dashboard.png` | 1270 x 760 px | MemoryBrain Developer Dashboard displaying project API keys, memory timeline, and usage telemetry. |
| **Slide 5 (Security)** | `ph_slide5_soc2.png` | 1270 x 760 px | "Enterprise Trust & SOC 2 Ready": AES-256 field encryption, tamper-proof version immutability, and 99.95% HA. |
| **Hero GIF / Video** | `ph_demo_video.gif` | 1270 x 760 px (30s) | Screencast showing `pip install memorybrain`, running store, recalling context in terminal, and seeing real-time dashboard update. |
