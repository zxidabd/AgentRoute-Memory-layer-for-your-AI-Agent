# 🛡️ Disaster Recovery Plan & Backup Runbook

## Objectives: RPO & RTO

| Metric | Target | Description |
| :--- | :--- | :--- |
| **Recovery Point Objective (RPO)** | **< 15 minutes** | Maximum acceptable data loss window in a catastrophic failure. |
| **Recovery Time Objective (RTO)** | **< 30 minutes** | Maximum acceptable time to restore the entire memory API cluster. |

---

## 1. Automated Backup Strategy

* **Full Backups:** Daily snapshot via `pg_dump` compressed format stored in multi-region encrypted S3/GCS buckets.
* **Continuous Archiving:** PostgreSQL Write-Ahead Logs (WAL) streamed continuously to Cloud Storage for Point-in-Time Recovery (PITR).
* **Backup Encryption:** All backup snapshots are encrypted with AES-256 before upload.

---

## 2. Disaster Recovery Procedure (Step-by-Step)

In the event of total primary region failure:

1. **Activate Secondary Standby Cluster:**
   ```bash
   # Provision primary database from latest WAL archive:
   pg_restore --clean --if-exists --dbname=$SECONDARY_DATABASE_URL latest_backup.sql
   ```
2. **Promote Read Replica:**
   If a regional read replica exists, issue:
   ```sql
   SELECT pg_promote();
   ```
3. **Update DNS / Load Balancer:**
   Update Cloudflare / Route53 DNS target to route API traffic to the secondary cluster.
4. **Run Verification Suite:**
   ```powershell
   python tests/test_tenant_isolation_leak_proof.py
   python tests/test_production_lifecycle.py
   ```
5. **Verify Health:**
   Ensure `/healthz/readiness` returns HTTP 200.
