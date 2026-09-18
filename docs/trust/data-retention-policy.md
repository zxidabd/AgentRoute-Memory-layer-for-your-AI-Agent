---
title: Data Retention & Disposal Policy
description: Lifecycle, grace periods, archival, and hard deletion of customer memories and event logs.
---

# Data Retention & Disposal Policy

## 1. Overview
MemoryBrain retains customer memory records, embeddings, and telemetry only as long as necessary to provide autonomous agent memory capabilities or to meet legal and compliance obligations.

## 2. Retention Schedules by Data Type

| Data Category | Active Retention | Post-Termination Retention | Disposal Method |
|---|---|---|---|
| **Active Memories** (memories) | Indefinite (or until customer soft/hard deletion). | 14-day downgrade grace, 30-day post-cancellation grace. | Cryptographic wipe and permanent DB row deletion (DELETE FROM memories). |
| **Audit Ledger** (memory_versions) | Retained during active subscription for audit compliance. | 30 days post-cancellation. | Cascade purge upon organization deletion. |
| **Vector Embeddings** | Synced with memory lifecycle. | Purged concurrently with memory record. | Removed from vector index. |
| **Usage Meter Events** (usage_events) | 12 months for billing audit and reconciliation. | 12 months (financial records requirement). | Automated batch purge of records older than 365 days. |
| **API Key Hashes** (pi_keys) | Active until revoked or expired. | Preserved with evoked_at timestamp for security audit trail. | Purged on org deletion. |

## 3. Right to be Forgotten (GDPR Erasure)
Upon receiving a user deletion request (DELETE /v1/users/{user_id}), all memory facts, versions, and embeddings associated with that user are permanently purged within 60 seconds.
