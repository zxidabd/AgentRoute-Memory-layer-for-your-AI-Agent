# AWS Deployment Guide (Parity Architecture)

This guide details how to deploy MemoryBrain to Amazon Web Services (AWS) using our official Terraform parity module.

---

## 1. AWS Architecture Stack

- **Compute:** Amazon ECS on AWS Fargate (Serverless, multi-AZ, min 2 / max 50 instances).
- **Database:** Amazon RDS PostgreSQL 16 with `pgvector` extension enabled and Multi-AZ standby.
- **Read Replica:** Dedicated Amazon RDS PostgreSQL 16 read replica for `/v1/context` queries.
- **Cache & Queue:** Amazon ElastiCache for Redis (Redis 7, multi-AZ with automatic failover).
- **Ingress:** AWS Application Load Balancer (ALB) with ACM TLS certificate termination.

```
       [ Client Ingress ]
               │ HTTPS (443)
               ▼
       ┌───────────────────────────────┐
       │   Application Load Balancer   │
       └───────────────┬───────────────┘
                       │
         ┌─────────────┴─────────────┐
         ▼                           ▼
  ┌─────────────┐             ┌─────────────┐
  │ ECS Fargate │ (Zone A)    │ ECS Fargate │ (Zone B)
  └──────┬──────┘             └──────┬──────┘
         │                           │
         └─────────────┬─────────────┘
                       │
         ┌─────────────┴─────────────┐
         ▼                           ▼
  ┌──────────────┐            ┌──────────────┐
  │ RDS Postgres │ (Primary)  │ RDS Postgres │ (Replica)
  └──────────────┘            └──────────────┘
```

---

## 2. Terraform Deployment

### Prerequisites:
- AWS CLI configured with Administrator permissions (`aws configure`).
- Terraform 1.5.0+.

### Step 1: Navigate to AWS Module
```bash
cd infra/terraform/aws
```

### Step 2: Initialize Terraform & Review Plan
```bash
terraform init
terraform plan -var="environment=prod" -var="region=us-east-1"
```

### Step 3: Apply Infrastructure
```bash
terraform apply -auto-approve -var="environment=prod" -var="region=us-east-1"
```

### Outputs:
- `ecs_service_name`: Name of the running Fargate service.
- `postgres_primary_endpoint`: Active writer endpoint.
- `postgres_replica_endpoint`: Read replica endpoint.
- `redis_primary_endpoint`: ElastiCache endpoint.
