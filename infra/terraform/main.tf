# ==============================================================================
# AI-Powered Market Intelligence — Root Terraform Configuration
# ==============================================================================

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

# 1. Networking Layer (VPC, Subnets, Gateways, Route Tables, Security Groups)
module "vpc" {
  source = "./modules/vpc"

  project_name             = var.project_name
  environment              = var.environment
  vpc_cidr                 = var.vpc_cidr
  availability_zones       = var.availability_zones
  public_subnet_cidrs      = var.public_subnet_cidrs
  private_app_subnet_cidrs = var.private_app_subnet_cidrs
  private_db_subnet_cidrs  = var.private_db_subnet_cidrs
  app_port                 = var.app_port
}

# 2. Object Storage Layer (Financial Data Lake, Logs, Model Artifacts)
module "s3" {
  source = "./modules/s3"

  project_name = var.project_name
  environment  = var.environment
}

# 3. Relational Database Layer (PostgreSQL 16 + pgvector)
module "rds" {
  source = "./modules/rds"

  project_name       = var.project_name
  environment        = var.environment
  subnet_ids         = module.vpc.private_db_subnet_ids
  security_group_ids = [module.vpc.rds_security_group_id]
  instance_class     = var.rds_instance_class
  allocated_storage  = var.rds_allocated_storage
  db_name            = var.db_name
  db_username        = var.db_username
}

# 4. Distributed Cache Layer (ElastiCache Redis)
module "elasticache" {
  source = "./modules/elasticache"

  project_name       = var.project_name
  environment        = var.environment
  subnet_ids         = module.vpc.private_db_subnet_ids
  security_group_ids = [module.vpc.redis_security_group_id]
  node_type          = var.redis_node_type
  num_cache_clusters = var.redis_num_cache_clusters
}

# 5. Compute & Ingress Layer (ECS Fargate, ALB, CloudWatch)
module "ecs" {
  source = "./modules/ecs"

  project_name           = var.project_name
  environment            = var.environment
  vpc_id                 = module.vpc.vpc_id
  public_subnet_ids      = module.vpc.public_subnet_ids
  private_app_subnet_ids = module.vpc.private_app_subnet_ids
  alb_security_group_id  = module.vpc.alb_security_group_id
  ecs_security_group_id  = module.vpc.ecs_security_group_id
  app_port               = var.app_port
  app_image              = var.app_image
  api_cpu                = var.ecs_api_cpu
  api_memory             = var.ecs_api_memory
  api_desired_count      = var.ecs_api_desired_count
  worker_cpu             = var.ecs_worker_cpu
  worker_memory          = var.ecs_worker_memory
  worker_desired_count   = var.ecs_worker_desired_count
  database_host          = module.rds.db_address
  database_port          = module.rds.db_port
  database_name          = module.rds.db_name
  redis_endpoint         = module.elasticache.primary_endpoint_address
  redis_port             = module.elasticache.port
}
