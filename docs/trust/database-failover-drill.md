---
title: Database Failover Simulation & Drill Runbook
description: Non-destructive database primary failover simulation and recovery verification.
---

# Managed Database Failover Drill Runbook

## 1. Objective
To simulate a sudden failure of the primary PostgreSQL node and confirm that:
1. Cloud SQL / RDS initiates synchronous hot standby promotion within **< 30 seconds**.
2. Connection pooling in gent_memory/database.py reconnects automatically via retry logic without requiring an application restart.
3. Zero write transactions are corrupted.

---

## 2. Non-Destructive Failover Drill Procedure

### Phase 1: Pre-Drill Baseline Check
Verify all components are healthy before initiation:
`ash
curl -f https://api-staging.memorybrain.ai/healthz/liveness
curl -f https://api-staging.memorybrain.ai/healthz/readiness
`

### Phase 2: Trigger Controlled Primary Failover
In Google Cloud SQL or AWS RDS:
`ash
# GCP Cloud SQL Failover
gcloud sql instances failover memorybrain-staging-primary

# AWS RDS Multi-AZ Reboot with Failover
aws rds reboot-db-instance --db-instance-identifier memorybrain-staging-primary --force-failover
`

### Phase 3: Observe Application Reconnection
1. Monitor /healthz/liveness responses during the failover transition.
2. Verify transient database disconnect: HTTP 503 Service Unavailable observed for $< 15$ seconds.
3. Confirm automatic reconnection: HTTP 200 OK restored once standby node promotion completes.
4. Run smoke query: POST /v1/context to verify read and write capability.
