# ---------------------------------------------------------------------------------------------------------------------
# AMAZON WEB SERVICES (AWS) PARITY ARCHITECTURE TERRAFORM MODULE
# ECS Fargate + Amazon RDS PostgreSQL 16 (pgvector) + ElastiCache Redis
# ---------------------------------------------------------------------------------------------------------------------

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.30"
    }
  }
}

provider "aws" {
  region = var.region
}

# 1. RDS DB Parameter Group enabling pgvector
resource "aws_db_parameter_group" "pg16_vector" {
  name   = "${var.project_name}-${var.environment}-pg16-vector"
  family = "postgres16"

  parameter {
    name  = "shared_preload_libraries"
    value = "vector"
  }
  parameter {
    name  = "max_connections"
    value = "200"
  }
}

# 2. Amazon RDS PostgreSQL 16 Primary (Multi-AZ)
resource "aws_db_instance" "postgres_primary" {
  identifier             = "${var.project_name}-${var.environment}-pg16"
  engine                 = "postgres"
  engine_version         = "16.2"
  instance_class         = var.db_instance_class
  allocated_storage      = var.db_allocated_storage_gb
  max_allocated_storage  = 500
  storage_type           = "gp3"
  multi_az               = true
  publicly_accessible    = false
  parameter_group_name   = aws_db_parameter_group.pg16_vector.name
  skip_final_snapshot    = var.environment == "prod" ? false : true

  backup_retention_period = 35
  backup_window           = "03:00-04:00"
}

# 3. Amazon RDS PostgreSQL 16 Read Replica (for /v1/context)
resource "aws_db_instance" "postgres_replica" {
  identifier             = "${var.project_name}-${var.environment}-pg16-replica"
  replicate_source_db    = aws_db_instance.postgres_primary.identifier
  instance_class         = var.db_instance_class
  storage_type           = "gp3"
  publicly_accessible    = false
  parameter_group_name   = aws_db_parameter_group.pg16_vector.name
  skip_final_snapshot    = true
}

# 4. Amazon ElastiCache for Redis (Multi-AZ)
resource "aws_elasticache_replication_group" "redis" {
  replication_group_id       = "${var.project_name}-${var.environment}-redis"
  description                = "MemoryBrain Distributed Context Cache and Rate Limiter"
  node_type                  = var.redis_node_type
  port                       = 6379
  automatic_failover_enabled = true
  multi_az_enabled           = true
  num_cache_clusters         = 2
  parameter_group_name       = "default.redis7"
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
}

# 5. Amazon ECS Fargate Cluster & Service
resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-${var.environment}-cluster"
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${var.project_name}-${var.environment}-api"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "2048"
  memory                   = "4096"

  container_definitions = jsonencode([
    {
      name      = "api"
      image     = var.container_image
      essential = true
      portMappings = [
        {
          containerPort = 8000
          hostPort      = 8000
        }
      ]
      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:8000/healthz/liveness || exit 1"]
        interval    = 15
        timeout     = 5
        retries     = 3
        startPeriod = 10
      }
      environment = [
        { name = "ENVIRONMENT", value = var.environment },
        { name = "DATABASE_URL", value = "postgresql://app:${aws_db_instance.postgres_primary.endpoint}/memorybrain" },
        { name = "READ_DATABASE_URL", value = "postgresql://app:${aws_db_instance.postgres_replica.endpoint}/memorybrain" },
        { name = "REDIS_URL", value = "redis://${aws_elasticache_replication_group.redis.primary_endpoint_address}:6379/0" }
      ]
    }
  ])
}

resource "aws_ecs_service" "api_service" {
  name            = "${var.project_name}-${var.environment}-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.min_instances
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = ["subnet-abc12345", "subnet-def67890"]
    assign_public_ip = true
  }
}
