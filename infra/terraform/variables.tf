# ---------------------------------------------------------------------------------------------------------------------
# SHARED TERRAFORM VARIABLES (GCP & AWS INFRASTRUCTURE PARITY)
# ---------------------------------------------------------------------------------------------------------------------

variable "environment" {
  description = "Target deployment environment (prod, staging, dev)"
  type        = string
  default     = "prod"
}

variable "project_name" {
  description = "Name identifier for all provisioned infrastructure resources"
  type        = string
  default     = "memorybrain"
}

variable "region" {
  description = "Primary deployment cloud region"
  type        = string
  default     = "us-east-1"
}

variable "container_image" {
  description = "Container image URI for MemoryBrain API service"
  type        = string
  default     = "ghcr.io/memorybrain/memorybrain-api:v1.2.0"
}

variable "min_instances" {
  description = "Minimum container instances for high-availability baseline"
  type        = number
  default     = 2
}

variable "max_instances" {
  description = "Maximum container instances for autoscaling under traffic bursts"
  type        = number
  default     = 50
}

variable "container_concurrency" {
  description = "Maximum concurrent requests allocated per container instance"
  type        = number
  default     = 80
}

variable "db_instance_class" {
  description = "Managed PostgreSQL compute tier (GCP: db-custom-4-16384 / AWS: db.r6g.large)"
  type        = string
  default     = "db.r6g.large"
}

variable "db_allocated_storage_gb" {
  description = "Initial allocated disk storage for PostgreSQL in gigabytes"
  type        = number
  default     = 100
}

variable "redis_node_type" {
  description = "Managed Redis node size (GCP: redis.m5.large / AWS: cache.m6g.large)"
  type        = string
  default     = "cache.m6g.large"
}

variable "domain_name" {
  description = "Custom root domain for public API and documentation endpoints"
  type        = string
  default     = "memorybrain.ai"
}
