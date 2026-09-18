# ---------------------------------------------------------------------------------------------------------------------
# GOOGLE CLOUD PLATFORM (GCP) PRIMARY ARCHITECTURE TERRAFORM MODULE
# Cloud Run (multi-AZ) + Cloud SQL PostgreSQL 16 (pgvector) + Memorystore Redis
# ---------------------------------------------------------------------------------------------------------------------

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.15"
    }
  }
}

provider "google" {
  region = var.region
}

# 1. Cloud SQL PostgreSQL 16 with pgvector extension support
resource "google_sql_database_instance" "postgres_primary" {
  name             = "${var.project_name}-${var.environment}-pg16"
  database_version = "POSTGRES_16"
  region           = var.region

  settings {
    tier              = "db-custom-4-16384"
    disk_size         = var.db_allocated_storage_gb
    disk_autoresize   = true
    availability_type = "REGIONAL" # Multi-zone HA failover

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      start_time                     = "03:00"
    }

    database_flags {
      name  = "cloudsql.enable_pgvector"
      value = "on"
    }
    database_flags {
      name  = "max_connections"
      value = "200"
    }
  }

  deletion_protection = var.environment == "prod" ? true : false
}

# 2. Cloud SQL Async Read Replica for /v1/context queries
resource "google_sql_database_instance" "postgres_replica" {
  name                 = "${var.project_name}-${var.environment}-pg16-replica"
  database_version     = "POSTGRES_16"
  region               = var.region
  master_instance_name = google_sql_database_instance.postgres_primary.name

  settings {
    tier            = "db-custom-4-16384"
    disk_size       = var.db_allocated_storage_gb
    disk_autoresize = true

    database_flags {
      name  = "cloudsql.enable_pgvector"
      value = "on"
    }
  }
}

# 3. Google Cloud Memorystore for Redis
resource "google_redis_instance" "cache" {
  name           = "${var.project_name}-${var.environment}-redis"
  tier           = "STANDARD_HA" # Multi-zone failover
  memory_size_gb = 5
  region         = var.region

  redis_version = "REDIS_7_0"
  display_name  = "MemoryBrain Distributed Context Cache and Rate Limiter"
}

# 4. Serverless Cloud Run v2 API Service
resource "google_cloud_run_v2_service" "api_service" {
  name     = "${var.project_name}-${var.environment}-api"
  location = var.region

  template {
    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    max_instance_request_concurrency = var.container_concurrency

    containers {
      image = var.container_image

      resources {
        limits = {
          cpu    = "2000m"
          memory = "2Gi"
        }
        cpu_idle = false # Always allocate CPU for ultra-low latency
      }

      env {
        name  = "ENVIRONMENT"
        value = var.environment
      }
      env {
        name  = "REDIS_URL"
        value = "redis://${google_redis_instance.cache.host}:${google_redis_instance.cache.port}/0"
      }

      startup_probe {
        http_get {
          path = "/healthz/startup"
          port = 8000
        }
        initial_delay_seconds = 2
        period_seconds        = 5
        failure_threshold     = 6
      }

      liveness_probe {
        http_get {
          path = "/healthz/liveness"
          port = 8000
        }
        period_seconds    = 10
        timeout_seconds   = 3
        failure_threshold = 3
      }
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }
}
