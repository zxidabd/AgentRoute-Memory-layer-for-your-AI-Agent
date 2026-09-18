# Self-Hosted Deployment Guide (Open-Core Edition)

Deploy MemoryBrain in your own private infrastructure (AWS, GCP, Hetzner, DigitalOcean, or bare-metal) using our official containerized `docker-compose` stack.

---

## 1. Architecture Overview

The self-hosted deployment packages the complete MemoryBrain platform:
- **`memorybrain-api`:** FastAPI application runtime with health probes and read/write session routing.
- **`memorybrain-postgres`:** PostgreSQL 16 equipped with the `pgvector` extension and HNSW cosine index.
- **`memorybrain-redis`:** Redis 7 with Append-Only File (AOF) durability for rate limiting, job queues, and 60s context caching.
- **`memorybrain-nginx`:** Reverse proxy handling SSL termination and Server-Sent Events (SSE) for MCP.
- **`memorybrain-certbot`:** Automated Let's Encrypt certificate renewal.

```
       [ Client Agents / Claude / Cursor ]
                       │ HTTPS (443)
                       ▼
       ┌───────────────────────────────┐
       │   Nginx Reverse Proxy & SSL   │
       └───────────────┬───────────────┘
                       │ HTTP (8000)
                       ▼
       ┌───────────────────────────────┐
       │    MemoryBrain API Server     │
       └───────┬───────────────┬───────┘
               │               │
               ▼               ▼
     ┌──────────────────┐ ┌──────────────────┐
     │  PostgreSQL 16   │ │     Redis 7      │
     │   (pgvector)     │ │  (AOF Persistent)│
     └──────────────────┘ └──────────────────┘
```

---

## 2. Hardware Prerequisites

- **Compute:** 2 vCPU minimum (4 vCPU recommended for high-volume agent recall).
- **Memory:** 4 GB RAM minimum (8 GB recommended, as HNSW vector indexes reside in RAM for sub-25ms performance).
- **Disk:** 40 GB SSD storage.
- **Software:** Docker Engine 24.0+ and Docker Compose v2.20+.

---

## 3. Quickstart Installation (3 Minutes)

### Step 1: Clone Repository & Enter Directory
```bash
git clone https://github.com/memorybrain/memorybrain.git
cd memorybrain/infra/self-hosted
```

### Step 2: Configure Environment Variables
```bash
cp .env.example .env
```
Generate secure passwords and an AES-256 encryption key:
```bash
# Generate encryption key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
Paste into `.env`:
```ini
POSTGRES_PASSWORD=your_secure_db_password_here
REDIS_PASSWORD=your_secure_redis_password_here
MEMORY_ENCRYPTION_KEY=your_generated_fernet_key
DOMAIN_NAME=memorybrain.yourcompany.com
CERTBOT_EMAIL=ops@yourcompany.com
```

### Step 3: Launch Stack
```bash
docker-compose up -d
```

Verify service health:
```bash
docker-compose ps
curl http://localhost:8000/healthz/liveness
# Returns: {"status":"alive","database":"connected"}
```

---

## 4. Open-Core vs Enterprise Licensing

MemoryBrain is distributed under an **Open-Core** model:

| Feature Area | Community Edition (Free Forever) | Enterprise Edition (Paid License Key) |
|---|---|---|
| **Core Storage & Retrieval** | Unlimited memories, facts, and searches | Unlimited memories, facts, and searches |
| **Model Context Protocol (MCP)** | Full Claude Desktop & Cursor support | Full Claude Desktop & Cursor support |
| **Encryption at Rest** | AES-256 Fernet payload encryption | AES-256 Fernet payload encryption |
| **Multi-Tenant Workspaces & RBAC** | Single Project / Admin key | Unlimited Orgs, Projects, and 3-Tier RBAC |
| **SAML / Okta SSO** | Not Included | Full SAML 2.0 / OIDC single sign-on |
| **Automated SOC 2 Compliance Pack** | Not Included | Point-in-time evidence collector (`/v1/compliance`) |
| **Usage Health Churn Analytics** | Not Included | Proactive tenant health score dashboard |
| **Support Model** | Community Discord & GitHub Issues | Dedicated Slack Connect + 4h SLA Support Add-on |

### Activating an Enterprise License:
If you have purchased an Enterprise self-hosted license, add your key to `.env`:
```ini
MEMORYBRAIN_LICENSE_KEY=mb_lic_eyJhbGciOiJI...
```
Restart the API container: `docker-compose restart api`.

---

## 5. Automated Database Backups (Customer Responsibility)

Because you manage the hosting environment, regular database backups are your responsibility. We recommend a daily cron job:

```bash
#!/bin/bash
# /etc/cron.daily/memorybrain-backup.sh
BACKUP_DIR="/var/backups/memorybrain"
mkdir -p "$BACKUP_DIR"
DATE=$(date +%Y%m%d_%H%M%S)

docker exec -t memorybrain-postgres pg_dump -U mb_admin memorybrain | gzip > "$BACKUP_DIR/mb_backup_$DATE.sql.gz"

# Retain 30 days of archives
find "$BACKUP_DIR" -type f -name "*.sql.gz" -mtime +30 -delete
```

---

## 6. Zero-Downtime Version Upgrades

When MemoryBrain releases a new version:
1. Pull updated image: `docker-compose pull api`
2. Run database migration: `docker-compose run --rm api alembic upgrade head`
3. Re-create container: `docker-compose up -d --no-deps api`
