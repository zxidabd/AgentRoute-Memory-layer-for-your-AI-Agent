---
title: BYOC & Dedicated Single-Tenant Architecture
description: Specification for Bring Your Own Cloud (BYOC) and dedicated containerized deployment for enterprise customers >= ,000/mo.
---

# BYOC & Dedicated Single-Tenant Architecture

*Note: In accordance with Step 4 Decision #5, this deployment option is available exclusively for contracts $\ge \,000\text{ / month}$.*

---

## 1. Overview
For enterprise organizations with stringent regulatory, banking, or defense requirements, MemoryBrain offers a **Bring Your Own Cloud (BYOC)** or **Dedicated Single-Tenant Virtual Private Cloud (VPC)** model.

`
          ┌──────────────────────────────────────────────────────────────────┐
          │             CUSTOMER CLOUD ACCOUNT (AWS / GCP)                   │
          │                                                                  │
          │   ┌──────────────────────────────────────────────────────────┐   │
          │   │      Customer Dedicated VPC / Kubernetes Cluster         │   │
          │   │                                                          │   │
          │   │   ┌──────────────────────────────────────────────────┐   │   │
          │   │   │  MemoryBrain Dedicated Engine (Docker / Helm)    │   │   │
          │   │   │  - Zero outbound telemetry without customer auth │   │   │
          │   │   │  - Customer-owned TLS certificates               │   │   │
          │   │   └────────────────────────┬─────────────────────────┘   │   │
          │   │                            │                             │   │
          │   │                            ▼                             │   │
          │   │   ┌──────────────────────────────────────────────────┐   │   │
          │   │   │  Customer-Owned Database (RDS PostgreSQL /       │   │   │
          │   │   │  Cloud SQL) with pgvector                        │   │   │
          │   │   │  - Customer KMS Key                              │   │   │
          │   │   │  - Private VPC Subnets Only (No public IP)       │   │   │
          │   │   └──────────────────────────────────────────────────┘   │   │
          │   └──────────────────────────────────────────────────────────┘   │
          └──────────────────────────────────────────────────────────────────┘
`

## 2. Technical Capabilities
1. **Customer-Owned KMS:** Data is encrypted using the customer's AWS KMS or GCP KMS key. If the customer disables the key, all memory access is instantly and irreversibly severed.
2. **Private Network Connectivity:** The memory cluster connects to internal customer microservices via AWS PrivateLink, Transit Gateway, or VPC Peering. No traffic traverses the public internet.
3. **Automated Terraform / Helm Distribution:** MemoryBrain provides a modular Terraform recipe (modules/memorybrain-byoc) and Helm chart for rapid infrastructure deployment into customer EKS or GKE clusters.
