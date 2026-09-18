---
title: Enterprise Security Whitepaper
description: Architecture, encryption, tenant isolation, and compliance posture of MemoryBrain.
---

# Enterprise Security Whitepaper

MemoryBrain is engineered from first principles for enterprise reliability, high-throughput agent operations, and strict data confidentiality. This whitepaper details our technical safeguards, cryptographic architecture, multi-tenant isolation, and continuous compliance monitoring.

---

## 1. Architectural Overview

MemoryBrain provides a long-term associative memory and episodic recall layer for autonomous AI agents. The platform operates under a zero-trust multi-tenant model where tenant isolation is enforced at every layer of the compute and storage stack.

`
                      ┌───────────────────────────────────────┐
                      │    Client Agent / Application Layer   │
                      │    (Python SDK / TS SDK / REST API)   │
                      └──────────────────┬────────────────────┘
                                         │ TLS 1.3 (HTTPS)
                                         ▼
                      ┌───────────────────────────────────────┐
                      │  Edge Reverse Proxy & Rate Limiter    │
                      │  (Cloudflare / DDoS / HMAC / CORS)    │
                      └──────────────────┬────────────────────┘
                                         │ Authenticated Context
                                         ▼
                      ┌───────────────────────────────────────┐
                      │    MemoryBrain Application Engine     │
                      │    (FastAPI / RBAC Middleware /       │
                      │     Idempotency / Plan Enforcement)   │
                      └─────────┬───────────────────┬─────────┘
                                │                   │
             AES-256 Field Enc  │                   │ SHA-256 Hashed Keys
                                ▼                   ▼
                      ┌──────────────────┐ ┌──────────────────┐
                      │  PostgreSQL +    │ │ Immutable Audit  │
                      │  pgvector Engine │ │ Version Ledger   │
                      └──────────────────┘ └──────────────────┘
`

---

## 2. Cryptographic Controls & Encryption

### 2.1 Encryption in Transit
- **Protocol:** All inbound and outbound communications mandate **TLS 1.3** (with TLS 1.2 as minimum fallback).
- **Ciphers:** High-security forward-secret ciphers only (ECDHE-RSA-AES128-GCM-SHA256, ECDHE-RSA-AES256-GCM-SHA384).
- **HSTS:** HTTP Strict Transport Security (HSTS) with a minimum 1-year duration and preload enabled.

### 2.2 Encryption at Rest
- **Database Storage:** Underpinned by cloud block storage volumes encrypted with AES-256 (AWS EBS or GCP Persistent Disk).
- **Application Field-Level Encryption:** All memory statements and entity values are encrypted at the application level before being written to persistent storage using **AES-256-Fernet / AES-256-GCM** envelope encryption (enc_v1:...).
- **Cryptographic Key Management:** Keys are decoupled from data volumes and managed via enterprise KMS (AWS KMS or GCP Cloud KMS) with automated annual key rotation.

---

## 3. Multi-Tenant Isolation & Identity Governance

### 3.1 Logical Partitioning
- Every database query strictly filters by org_id and project_id. Cross-tenant queries are structurally prevented by repository abstractions and verified by automated adversarial regression tests.

### 3.2 API Key Governance
- API keys follow the cryptographically secure structure: mb_{environment}_{32_urlsafe_random_chars}.
- Plaintext API keys are **never stored** in persistent memory. Only cryptographic **SHA-256 digests** (key_hash) are persisted.
- Keys can be instantly scoped by project, environment (dev, staging, prod), role (owner, developer, iewer), or revoked with sub-second propagation.

### 3.3 Three-Tier Role-Based Access Control (RBAC)
MemoryBrain enforces strict least-privilege access:
1. **Owner:** Full workspace control, team management, billing/plan management, organization deletion, API key provisioning.
2. **Developer:** Read/write memories, project creation, API key management, billing view.
3. **Viewer:** Read-only access to memories, projects, and billing usage metrics.

---

## 4. Auditability & Immutable Version Ledger

- Every modification, patch, or supersession to an existing memory creates an append-only entry in the memory_versions table.
- **Tamper-Proof Enforcement:** Database event listeners strictly disallow UPDATE and DELETE queries on memory_versions. Even system administrators cannot rewrite historical versions.
- Historical versions preserve the exact statement, author, timestamp, reason, and prior status.

---

## 5. Privacy & Data Governance (GDPR / CCPA)

- **Right to be Forgotten:** Automated cascading purge endpoint (DELETE /v1/users/{user_id}) permanently deletes all user facts, associative graph nodes, and embeddings across all agent environments within 60 seconds.
- **Portability:** Full compliance export available via GET /v1/export.
- **Retention Lifecycle:** Configurable retention policies; cancelled or downgraded organizations enjoy a 14-day grace period followed by soft-archival and permanent purge after 30 days.

---

## 6. Continuous Compliance Monitoring (SOC 2)

MemoryBrain uses **Vanta** for continuous automated evidence collection across infrastructure, code repositories, and identity systems:
- **SOC 2 Type I:** Point-in-time design and control certification.
- **SOC 2 Type II:** Continuous 3–6 month observation window verifying operational effectiveness across Security, Confidentiality, and Processing Integrity.
