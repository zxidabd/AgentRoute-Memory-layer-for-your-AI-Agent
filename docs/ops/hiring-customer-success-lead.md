# MemoryBrain — Hiring Spec: Founding Customer Success & DevRel Engineer

This specification defines the role, profile, scorecard, and hiring triggers for MemoryBrain's first non-founder hire.

---

## 1. Role Overview & Strategic Mandate

- **Title:** Founding Customer Success & DevRel Engineer (Employee #3)
- **Reporting to:** CEO / Founder
- **Location:** Remote (US or European time zone preferred)
- **Mission:** Own the post-signup developer journey. Turn self-serve developers into champions, prevent early churn through proactive technical guidance, and bridge user feedback directly into the engineering roadmap.

---

## 2. When to Trigger This Hire (Bottleneck Conditions)

Do not hire on a fixed date. Trigger active recruiting only when at least two of the following conditions are met:
1. **Founder Support Bottleneck:** Founders spend $>25\%$ of working hours answering support tickets, debugging SDK issues, or conducting onboarding calls.
2. **Paying Customer Volume:** The platform surpasses **40 paying organizations** (Growth, Scale, or Enterprise).
3. **Enterprise POC Pipeline:** More than 3 concurrent enterprise prospects require hands-on architecture reviews and Slack Connect support.

---

## 3. Core Responsibilities

- **Developer Support & Triage:** Own the `support@memorybrain.ai` queue and Discord developer channels, maintaining our $<12\text{h}$ response time SLA.
- **Enterprise Onboarding:** Lead 30-minute technical kickoff calls for new Growth and Enterprise customers; assist in configuring MCP or Python/TypeScript SDKs in their agent codebase.
- **Documentation & Tutorials:** Write end-to-end integration tutorials (e.g. "Building a persistent LangGraph agent with MemoryBrain") and improve public docs based on recurring questions.
- **Proactive Churn Intervention:** Monitor the **Usage Health Score dashboard**; proactively reach out to accounts experiencing drops in weekly memory recalls.
- **Voice of the Customer:** Participate in weekly engineering reviews to champion the most frequently requested features with reproducible customer context.

---

## 4. Candidate Requirements & Qualifications

- **Software Engineering Background:** 2+ years of professional software engineering experience in Python or TypeScript. Able to read, debug, and contribute code to our open-source SDKs.
- **AI / Agent Familiarity:** Working experience with LLMs, LangChain, LlamaIndex, OpenAI Assistants API, or Model Context Protocol (MCP).
- **High Developer Empathy:** Exceptional written communication skills; ability to explain complex distributed systems tradeoffs (e.g. dense vs BM25 hybrid search) with clarity and patience.
- **Autonomy:** Thrives in an early-stage startup environment where processes are evolving rapidly.

---

## 5. 4-Stage Interview Process & Scorecard

```
[1. Resume / GitHub Screen] ──► [2. Technical Integration Demo] ──► [3. Bug Debugging Simulation] ──► [4. Founder Culture & Values]
```

| Evaluation Dimension | Scoring Criteria (1–5) | Key Assessment Question |
|---|---|---|
| **Technical Depth (Python/TS)** | Candidate writes clean, idiomatic SDK code and understands REST/SSE APIs. | "Walk us through how you would integrate MemoryBrain into a FastAPI bot." |
| **Developer Empathy & Support** | Patient, encouraging, and clear when diagnosing user errors. | "How would you respond to a frustrated user reporting 429 Quota Exceeded?" |
| **Communication & Writing** | Explains complex architectural tradeoffs concisely in markdown. | "Review and suggest improvements for our Quickstart guide." |
| **Startup Resilience & Ownership** | Comfortable wearing multiple hats without waiting for explicit instructions. | "Tell us about a time you identified and fixed a gap in a product without being asked." |
