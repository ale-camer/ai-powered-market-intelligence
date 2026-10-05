output "primary_endpoint_address" {
  description = "The primary endpoint address of the Redis replication group"
  value       = aws_elasticache_replication_group.redis.primary_endpoint_address
}

output "port" {
  description = "The port of the Redis replication group"
  value       = aws_elasticache_replication_group.redis.port
}

output "auth_token" {
  description = "Redis authentication token"
  value       = random_password.redis_auth_token.result
  sensitive   = true
}
