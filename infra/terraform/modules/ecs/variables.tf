variable "project_name" {
  description = "Project identifier"
  type        = string
}

variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "vpc_id" {
  description = "The VPC ID"
  type        = string
}

variable "public_subnet_ids" {
  description = "Public subnet IDs for ALB"
  type        = list(string)
}

variable "private_app_subnet_ids" {
  description = "Private application subnet IDs for ECS Fargate tasks"
  type        = list(string)
}

variable "alb_security_group_id" {
  description = "Security group ID for the Application Load Balancer"
  type        = string
}

variable "ecs_security_group_id" {
  description = "Security group ID for ECS Fargate tasks"
  type        = string
}

variable "app_port" {
  description = "Application port for FastAPI service"
  type        = number
  default     = 8000
}

variable "app_image" {
  description = "Container image URI"
  type        = string
}

variable "api_cpu" {
  description = "CPU units for API container (e.g. 512 = 0.5 vCPU)"
  type        = number
  default     = 512
}

variable "api_memory" {
  description = "Memory for API container in MB"
  type        = number
  default     = 1024
}

variable "api_desired_count" {
  description = "Desired number of API instances"
  type        = number
  default     = 2
}

variable "worker_cpu" {
  description = "CPU units for Celery worker container"
  type        = number
  default     = 512
}

variable "worker_memory" {
  description = "Memory for Celery worker container in MB"
  type        = number
  default     = 1024
}

variable "worker_desired_count" {
  description = "Desired number of Celery worker instances"
  type        = number
  default     = 2
}

variable "database_host" {
  description = "RDS PostgreSQL host address"
  type        = string
  default     = ""
}

variable "database_port" {
  description = "RDS PostgreSQL port"
  type        = number
  default     = 5432
}

variable "database_name" {
  description = "RDS PostgreSQL database name"
  type        = string
  default     = "market_intel"
}

variable "redis_endpoint" {
  description = "ElastiCache Redis primary endpoint"
  type        = string
  default     = ""
}

variable "redis_port" {
  description = "ElastiCache Redis port"
  type        = number
  default     = 6379
}
