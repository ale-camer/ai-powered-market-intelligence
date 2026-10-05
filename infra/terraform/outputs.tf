output "vpc_id" {
  description = "The ID of the provisioned VPC"
  value       = module.vpc.vpc_id
}

output "alb_dns_name" {
  description = "Public DNS name of the Application Load Balancer"
  value       = module.ecs.alb_dns_name
}

output "rds_endpoint" {
  description = "Connection endpoint for the RDS PostgreSQL database"
  value       = module.rds.db_endpoint
}

output "redis_endpoint" {
  description = "Primary endpoint address for ElastiCache Redis"
  value       = module.elasticache.primary_endpoint_address
}

output "s3_bucket_name" {
  description = "Name of the S3 financial data lake bucket"
  value       = module.s3.bucket_name
}

output "ecs_cluster_name" {
  description = "Name of the ECS compute cluster"
  value       = module.ecs.ecs_cluster_name
}
