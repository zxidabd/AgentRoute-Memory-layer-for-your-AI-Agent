---
title: Data Residency Architecture: EU Region
description: Specification for isolated EU (eu-west-1) infrastructure deployment for GDPR compliance.
---

# Multi-Region Data Residency Architecture (EU Region)

*Note: In accordance with Step 4 Decision #4, this infrastructure is deployed on-demand when triggered by the first paying EU enterprise customer.*

---

## 1. Architecture Topology
When provisioned, the European region (eu-west-1, Ireland) operates as a completely isolated, autonomous data plane:

`
                            ┌──────────────────────────────────────┐
                            │    Cloudflare Geo-DNS & Anycast      │
                            │    (Routes EU traffic to EU cluster) │
                            └──────────────────┬───────────────────┘
                                               │
                        ┌──────────────────────┴──────────────────────┐
                        ▼                                             ▼
          ┌───────────────────────────┐                 ┌───────────────────────────┐
          │      US DATA PLANE        │                 │       EU DATA PLANE       │
          │       (us-east-1)         │                 │        (eu-west-1)        │
          ├───────────────────────────┤                 ├───────────────────────────┤
          │ • API Cluster (ECS / EKS) │                 │ • API Cluster (ECS / EKS) │
          │ • Aurora PostgreSQL (US)  │                 │ • Aurora PostgreSQL (EU)  │
          │ • KMS Key (US-EAST-1)     │                 │ • KMS Key (EU-WEST-1)     │
          │ • S3 Backup Vault (US)    │                 │ • S3 Backup Vault (EU)    │
          └───────────────────────────┘                 └───────────────────────────┘
`

## 2. Technical Guarantees
1. **Zero Cross-Region Replication:** European customer memory records, embeddings, and telemetry **never leave** the eu-west-1 boundary.
2. **Dedicated KMS:** All encryption keys are provisioned in AWS KMS eu-west-1 and cannot be accessed or decrypted by US infrastructure.
3. **EU-Specific Subprocessors:** Transactional email and edge caching configure European data-residency locks.
