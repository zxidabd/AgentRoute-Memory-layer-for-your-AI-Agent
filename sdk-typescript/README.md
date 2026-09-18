# MemoryBrain TypeScript / Node.js SDK 🧠

Official TypeScript client for [MemoryBrain](https://memorybrain.ai) — the enterprise-grade long-term memory layer for AI agents.

## Installation

```bash
npm install @memorybrain/sdk
```

## 2-Line Quickstart

```typescript
import { MemoryBrain } from "@memorybrain/sdk";

const mb = new MemoryBrain({ apiKey: "mb_live_your_key_here" });

// 1. Store a memory or conversation turn
await mb.store({
  userId: "u123",
  content: "Prefers dark mode and TypeScript"
});

// 2. Recall relevant context (< 25ms)
const result = await mb.recall({
  userId: "u123",
  query: "editor preferences"
});

console.log(result.context);
```

## Features
- **Zero External Runtime Dependencies**: Uses native `fetch` built into Node.js 18+, Bun, and Deno.
- **Typed Errors**: Automatically throws `AuthError`, `QuotaExceededError`, `RateLimitError`.
- **Sub-25ms Semantic Context Recall**: Automatic Ebbinghaus recency decay and multi-factor ranking.
