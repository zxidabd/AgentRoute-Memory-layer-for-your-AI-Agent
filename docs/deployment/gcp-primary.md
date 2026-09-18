# GCP Deployment Guide (Primary Managed SaaS Architecture)

This guide documents the primary cloud infrastructure running MemoryBrain on Google Cloud Platform (GCP).

---

## 1. GCP Architecture Topology

- **Compute:** Google Cloud Run v2 (Serverless, multi-AZ, min 2 / max 50 instances, 80 concurrency/container).
- **Database:** Google Cloud SQL PostgreSQL 16 with `pgvector` flags (`cloudsql.enable_pgvector = on`) and Regional HA failover.
- **Read Replica:** Google Cloud SQL Async Read Replica dedicated to `/v1/context` queries.
- **Cache & Queue:** Google Cloud Memorystore for Redis (Standard HA multi-zone).
- **Edge:** Cloudflare Anycast WAF + Google Cloud HTTPS External Load Balancer.

---

## 2. Terraform Deployment

### Step 1: Navigate to GCP Module
```bash
cd infra/terraform/gcp
```

### Step 2: Initialize & Apply
```bash
terraform init
terraform apply -var="environment=prod" -var="region=us-central1"
```

### Verification Probes:
- Liveness: `curl https://api.memorybrain.ai/healthz/liveness` (active DB check)
- Readiness: `curl https://api.memorybrain.ai/healthz/readiness` (primary + replica check)
- Startup: `curl https://api.memorybrain.ai/healthz/startup`
