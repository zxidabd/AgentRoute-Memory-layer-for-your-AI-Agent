# MemoryBrain — Infrastructure Scaling Triggers & Capacity Management

This runbook establishes empirical triggers and architectural procedures for scaling compute, database, and regional capacity as tenant volume grows.

---

## 1. Growth-Driven Load Testing & Re-Evaluation Triggers

Never scale capacity based on guesses. We conduct formal capacity re-evaluations under specific traffic and customer milestones:

| Trigger Event | Milestone Threshold | Action Required |
|---|---|---|
| **5x Active Org Growth** | Tenant count grows by 5x (e.g. 20 $\rightarrow$ 100 orgs). | Execute 200-concurrent-thread stress test using `tests/test_load_concurrency.py`. Verify p95 recall remains $<25\text{ms}$. |
| **Peak Ingress Surge** | Sustained traffic exceeds 2,500 queries per second (QPS). | Increase Cloud Run `max-instances` from 50 to 100; expand connection pool size. |
| **Database Storage Growth** | PostgreSQL storage exceeds 70% of provisioned disk. | Enable automatic Cloud SQL storage increase; review table vacuuming. |
| **First EU Enterprise Deal** | Closing a customer requiring GDPR European data residency. | Trigger EU region deployment checklist (below) to activate `europe-west1`. |

---

## 2. Database Replica Scaling Thresholds

Our primary write database delegates high-frequency context recall queries (`POST /v1/context`) to asynchronous read replicas. We monitor two key metrics to determine when to provision additional replicas:

```
                      ┌──────────────────────────────────────────────┐
                      │ Cloud SQL Primary Writer (db-custom-4-16384) │
                      └──────────────────────┬───────────────────────┘
                                             │
                       ┌─────────────────────┴─────────────────────┐
                       ▼                                           ▼
         ┌───────────────────────────┐               ┌───────────────────────────┐
         │ Cloud SQL Read Replica #1 │               │ Cloud SQL Read Replica #2 │
         │ (db-custom-4-16384)       │               │ (Provisioned when CPU>65%)│
         └───────────────────────────┘               └───────────────────────────┘
```

1. **CPU Utilization Trigger:** If read replica CPU exceeds **65% sustained over 15 minutes**, provision an additional read replica node in Zone B/C.
2. **Connection Pool Trigger:** If active connections exceed **70% of `max_connections` (140/200)**, increase PgBouncer pool ceiling and add replica capacity.
3. **Replication Lag Gate:** If replica lag exceeds **2.0 seconds**, alert SRE on-call and temporarily re-route critical reads to primary to prevent stale context recall.

---

## 3. Multi-Region EU Deployment Checklist

When the first European enterprise contract closes ($20,000+ commitment):

1. **GCP Project Setup:** Enable Cloud Run, Cloud SQL, and Secret Manager in region `europe-west1` (Belgium) or `europe-west3` (Frankfurt).
2. **KMS Key Provisioning:** Create dedicated European Cloud KMS keyring (`europe-west1-memorybrain-kms`) ensuring zero cross-border key exchange.
3. **Database Spin-Up:** Deploy regional PostgreSQL instance with local read replicas and private VPC connector.
4. **Cloudflare Geo-Steering:** Configure Cloudflare DNS load balancing to route traffic from European IPs directly to the EU Cloud Run cluster.
5. **DPA Certification:** Issue EU Data Residency confirmation letter to customer legal team.
