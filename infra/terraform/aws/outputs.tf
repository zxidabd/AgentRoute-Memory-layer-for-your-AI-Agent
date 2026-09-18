output "ecs_service_name" {
  description = "Name of the ECS Fargate API service"
  value       = aws_ecs_service.api_service.name
}

output "postgres_primary_endpoint" {
  description = "Amazon RDS PostgreSQL primary connection endpoint"
  value       = aws_db_instance.postgres_primary.endpoint
}

output "postgres_replica_endpoint" {
  description = "Amazon RDS PostgreSQL read replica connection endpoint"
  value       = aws_db_instance.postgres_replica.endpoint
}

output "redis_primary_endpoint" {
  description = "ElastiCache Redis cluster primary connection endpoint"
  value       = aws_elasticache_replication_group.redis.primary_endpoint_address
}
