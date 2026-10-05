variable "aws_region" {
  description = "AWS region for provisioning resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Target deployment environment (e.g., production, staging)"
  type        = string
  default     = "production"
}

variable "project_name" {
  description = "Project name identifier used for resource naming and tagging"
  type        = string
  default     = "market-intelligence"
}

variable "vpc_cidr" {
  description = "CIDR block for the cloud VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "List of availability zones for multi-AZ topology"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_app_subnet_cidrs" {
  description = "CIDR blocks for private application subnets"
  type        = list(string)
  default     = ["10.0.10.0/24", "10.0.11.0/24"]
}

variable "private_db_subnet_cidrs" {
  description = "CIDR blocks for isolated database and cache subnets"
  type        = list(string)
  default     = ["10.0.20.0/24", "10.0.21.0/24"]
}

variable "rds_instance_class" {
  description = "AWS RDS instance class for PostgreSQL"
  type        = string
  default     = "db.t4g.medium"
}

variable "rds_allocated_storage" {
  description = "Allocated storage volume in GB for PostgreSQL RDS"
  type        = number
  default     = 20
}

variable "db_name" {
  description = "Database name for PostgreSQL"
  type        = string
  default     = "market_intel"
}

variable "db_username" {
  description = "Master username for PostgreSQL database"
  type        = string
  default     = "market_intel_admin"
}

variable "redis_node_type" {
  description = "Instance type for ElastiCache Redis cluster"
  type        = string
  default     = "cache.t4g.medium"
}

variable "redis_num_cache_clusters" {
  description = "Number of cache nodes in Redis replication group"
  type        = number
  default     = 2
}

variable "app_port" {
  description = "Exposed TCP port for the FastAPI service"
  type        = number
  default     = 8000
}

variable "app_image" {
  description = "Container image URI for FastAPI and Celery tasks"
  type        = string
  default     = "123456789012.dkr.ecr.us-east-1.amazonaws.com/market-intel:latest"
}

variable "ecs_api_cpu" {
  description = "vCPU allocation for ECS API container task"
  type        = number
  default     = 512
}

variable "ecs_api_memory" {
  description = "Memory allocation in MB for ECS API container task"
  type        = number
  default     = 1024
}

variable "ecs_api_desired_count" {
  description = "Desired number of running ECS API tasks"
  type        = number
  default     = 2
}

variable "ecs_worker_cpu" {
  description = "vCPU allocation for Celery worker container task"
  type        = number
  default     = 512
}

variable "ecs_worker_memory" {
  description = "Memory allocation in MB for Celery worker container task"
  type        = number
  default     = 1024
}

variable "ecs_worker_desired_count" {
  description = "Desired number of running Celery worker tasks"
  type        = number
  default     = 2
}
