# MemoryBrain Python SDK 🧠

Official Python client for [MemoryBrain](https://memorybrain.ai) — the enterprise-grade long-term memory layer for AI agents.

## Installation

```bash
pip install memorybrain
```

*(Zero external dependencies. Works out of the box with pure Python standard library!)*

## 2-Line Quickstart

```python
from memorybrain import MemoryBrain

mb = MemoryBrain(api_key="mb_live_your_key_here")

# 1. Store a memory or conversation turn
mb.store(user_id="u123", content="Prefers dark mode and TypeScript")

# 2. Recall relevant context (< 25ms)
result = mb.recall(user_id="u123", query="editor preferences")
print(result["context"])
```

## Features
- **Sub-25ms Semantic Recall**: Multi-factor ranking combining embeddings, Ebbinghaus forgetting decay, and importance.
- **Automatic Quota & Retry Handling**: Exponential backoff on transient network issues and typed exceptions (`AuthError`, `QuotaExceededError`).
- **Full GDPR Compliance**: 1-line complete user memory wipes with `mb.delete(user_id="u123")`.
