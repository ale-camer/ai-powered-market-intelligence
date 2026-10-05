variable "project_name" {
  description = "Project identifier"
  type        = string
}

variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "subnet_ids" {
  description = "Subnet IDs for ElastiCache subnet group"
  type        = list(string)
}

variable "security_group_ids" {
  description = "Security groups for the ElastiCache cluster"
  type        = list(string)
}

variable "node_type" {
  description = "Instance type for Redis nodes"
  type        = string
  default     = "cache.t4g.medium"
}

variable "num_cache_clusters" {
  description = "Number of cache nodes in the replication group"
  type        = number
  default     = 2
}
