output "cloud_run_service_uri" {
  description = "Public HTTPS URI of the Cloud Run API service"
  value       = google_cloud_run_v2_service.api_service.uri
}

output "postgres_primary_connection" {
  description = "Cloud SQL primary instance connection name"
  value       = google_sql_database_instance.postgres_primary.connection_name
}

output "postgres_replica_connection" {
  description = "Cloud SQL async read replica connection name"
  value       = google_sql_database_instance.postgres_replica.connection_name
}

output "redis_endpoint" {
  description = "Memorystore Redis host IP address"
  value       = google_redis_instance.cache.host
}
