variable "project_name" {
  description = "Project identifier"
  type        = string
}

variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "subnet_ids" {
  description = "Subnet IDs for RDS subnet group (isolated private database subnets)"
  type        = list(string)
}

variable "security_group_ids" {
  description = "Security groups for the RDS instance"
  type        = list(string)
}

variable "instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t4g.medium"
}

variable "allocated_storage" {
  description = "Allocated storage volume in GB"
  type        = number
  default     = 20
}

variable "db_name" {
  description = "PostgreSQL database name"
  type        = string
  default     = "market_intel"
}

variable "db_username" {
  description = "Master username for PostgreSQL database"
  type        = string
  default     = "market_intel_admin"
}

variable "multi_az" {
  description = "Enable Multi-AZ high availability"
  type        = bool
  default     = true
}
