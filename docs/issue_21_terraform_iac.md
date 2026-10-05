# Issue 21: Terraform Infrastructure as Code (IaC) for Cloud Deployment

**Branch:** `feature/issue-21-terraform-iac`  
**Status:** Completed  
**PR:** TBD  
**Milestone:** M5 — Quality, Security & Release  

---

## Objective

Provision and codify production-grade cloud infrastructure for the AI-Powered Market Intelligence platform using Terraform. Implement a modular, reusable Infrastructure as Code (IaC) architecture adhering to cloud security best practices (least-privilege security groups, zero public access for databases/caches, KMS encryption at rest, multi-AZ high availability, and automated health checks). Define infrastructure components across networking (VPC, public/private subnets, NAT gateway), relational data storage (AWS RDS PostgreSQL 16 with `pgvector` enabled), distributed caching (AWS ElastiCache for Redis), object storage (AWS S3 data lake with encryption and lifecycle management), container compute (AWS ECS Fargate for FastAPI and Celery workers), and traffic ingress (Application Load Balancer with SSL/TLS termination and `/health` routing). Provide a dedicated test suite under `@pytest.mark.issue_21` validating HCL syntax, module declarations, parameter mappings, and security guardrails.

---

## Acceptance Criteria

- [x] **Terraform Root & Environment Structure (`infra/terraform/`)**:
  - Root configuration (`main.tf`, `variables.tf`, `outputs.tf`, `versions.tf`, `terraform.tfvars.example`).
  - Provider specifications requiring `hashicorp/aws >= 5.0` and Terraform CLI `>= 1.5.0`.
  - Configurable environment tagging schema (`Project`, `Environment`, `ManagedBy = "Terraform"`).
- [x] **Networking Module (`infra/terraform/modules/vpc/`)**:
  - Multi-AZ VPC with configurable CIDR block (default `10.0.0.0/16`).
  - Segregated subnets across at least 2 Availability Zones:
    - Public subnets for Application Load Balancer and NAT Gateway(s).
    - Private application subnets for ECS Fargate tasks (FastAPI & Celery).
    - Isolated database/cache subnets for RDS PostgreSQL and ElastiCache Redis.
  - Security Groups with strict ingress/egress rules:
    - ALB Security Group: Ingress 80/443 from `0.0.0.0/0`.
    - App Security Group: Ingress 8000 from ALB Security Group only.
    - RDS Security Group: Ingress 5432 from App Security Group only.
    - Redis Security Group: Ingress 6379 from App Security Group only.
- [x] **Relational Database Module (`infra/terraform/modules/rds/`)**:
  - AWS RDS PostgreSQL 16 instance with automated multi-AZ option.
  - Custom DB parameter group enabling `pgvector` extension and optimized memory settings.
  - Encryption at rest via AWS KMS.
  - Strict network isolation: `publicly_accessible = false` in dedicated DB subnet group.
  - Automated backups, maintenance window, and performance insights.
- [x] **In-Memory Cache Module (`infra/terraform/modules/elasticache/`)**:
  - AWS ElastiCache for Redis (or replication group) in cluster mode.
  - In-transit and at-rest encryption enabled with auth token / password.
  - Dedicated cache subnet group in private subnets.
- [x] **Object Storage Module (`infra/terraform/modules/s3/`)**:
  - S3 bucket for financial data lake, raw documents, Airflow logs, and model artifacts.
  - Public access block enabled (`block_public_acls`, `block_public_policy`, `ignore_public_acls`, `restrict_public_buckets`).
  - Default server-side encryption with AWS KMS or AES-256 (`aws:kms`).
  - Bucket lifecycle configuration transitioning older objects to infrequent access / glacier.
- [x] **Container Compute & Delivery Module (`infra/terraform/modules/ecs/`)**:
  - AWS ECS Cluster with Fargate and Fargate Spot capacity providers.
  - Task Definitions for:
    - `api`: FastAPI container running `api` on port 8000 with CloudWatch logging and container health check.
    - `celery_worker`: Celery worker task processing queues (`high_priority`, `default`, `dlq`).
  - ECS Services with desired task counts, rolling deployment circuit breaker, and security group bindings.
  - Application Load Balancer (ALB) with HTTP/HTTPS listeners, target group pointing to ECS `api` service with `/health` path.
- [x] **Developer Ergonomics & Makefile Targets (`Makefile`)**:
  - Targets for infrastructure workflow: `terraform-init`, `terraform-validate`, and `terraform-plan`.
- [x] **Automated Test Suite (`tests/unit/test_terraform_config.py`)**:
  - Unit tests under `@pytest.mark.unit` and `@pytest.mark.issue_21`:
    - Validates root HCL files, provider versions, and variable definitions.
    - Validates presence and interface contracts of all 5 modules (`vpc`, `rds`, `elasticache`, `s3`, `ecs`).
    - Validates security configurations: non-public RDS, S3 public access block, KMS encryption directives, and security group isolation.
    - Validates Makefile Terraform lifecycle targets.

---

## Implementation Tasks

### 1. Preparation & Branching
```bash
make start-issue ID=21 NAME=terraform-iac
```

### 2. Root Module & Provider Specifications
- **File**: `infra/terraform/versions.tf`
  - Declare `required_version >= "1.5.0"` and provider `hashicorp/aws` (`~> 5.0`).
- **File**: `infra/terraform/variables.tf`
  - Input variables: `aws_region`, `environment`, `project_name`, `vpc_cidr`, `rds_instance_class`, `redis_node_type`, `ecs_cpu`, `ecs_memory`, `app_port`.
- **File**: `infra/terraform/main.tf`
  - Root module calling child modules: `vpc`, `s3`, `rds`, `elasticache`, and `ecs`.
  - Pass security group IDs, subnet IDs, and KMS keys between modules.
- **File**: `infra/terraform/outputs.tf`
  - Outputs: `alb_dns_name`, `rds_endpoint`, `redis_endpoint`, `s3_bucket_name`, `ecs_cluster_name`.
- **File**: `infra/terraform/terraform.tfvars.example`
  - Example variable assignments for development and production profiles.

### 3. Child Infrastructure Modules
- **File**: `infra/terraform/modules/vpc/main.tf`
  - `aws_vpc`, `aws_subnet` (public, private app, private db), `aws_internet_gateway`, `aws_nat_gateway`, `aws_route_table`, `aws_route_table_association`.
  - `aws_security_group` for ALB, App, RDS, and Redis with cross-referencing source security groups.
- **File**: `infra/terraform/modules/vpc/variables.tf` & `outputs.tf`
  - Export subnet IDs, VPC ID, and security group IDs.
- **File**: `infra/terraform/modules/s3/main.tf`
  - `aws_s3_bucket`, `aws_s3_bucket_public_access_block`, `aws_s3_bucket_server_side_encryption_configuration`, `aws_s3_bucket_versioning`.
- **File**: `infra/terraform/modules/s3/variables.tf` & `outputs.tf`
  - Export bucket ID and ARN.
- **File**: `infra/terraform/modules/rds/main.tf`
  - `aws_db_subnet_group`, `aws_db_parameter_group` (PostgreSQL 16, `shared_preload_libraries = "pgvector"`), `aws_db_instance` (`postgres`, multi_az, storage_encrypted = true).
- **File**: `infra/terraform/modules/rds/variables.tf` & `outputs.tf`
  - Export DB endpoint, address, and port.
- **File**: `infra/terraform/modules/elasticache/main.tf`
  - `aws_elasticache_subnet_group`, `aws_elasticache_parameter_group`, `aws_elasticache_replication_group` (engine: `redis`, transit_encryption_enabled, at_rest_encryption_enabled).
- **File**: `infra/terraform/modules/elasticache/variables.tf` & `outputs.tf`
  - Export Redis primary endpoint address and port.
- **File**: `infra/terraform/modules/ecs/main.tf`
  - `aws_ecs_cluster`, `aws_cloudwatch_log_group`.
  - `aws_lb`, `aws_lb_target_group` (path `/health`, matcher `200`), `aws_lb_listener`.
  - `aws_iam_role` (execution role, task role).
  - `aws_ecs_task_definition` (API and Worker).
  - `aws_ecs_service` (API linked to ALB, Worker running Celery).
- **File**: `infra/terraform/modules/ecs/variables.tf` & `outputs.tf`
  - Export ALB DNS name, ECS cluster name, service names.

### 4. Makefile Integration
- **File**: `Makefile`
  - Add Terraform validation and formatting commands:
    ```makefile
    .PHONY: terraform-fmt
    terraform-fmt: ## Format Terraform configuration files
    	terraform -chdir=infra/terraform fmt -recursive

    .PHONY: terraform-validate
    terraform-validate: ## Validate Terraform HCL files
    	terraform -chdir=infra/terraform init -backend=false
    	terraform -chdir=infra/terraform validate
    ```

### 5. Automated Unit & Security Tests
- **File**: `tests/unit/test_terraform_config.py`
  - Mark `@pytest.mark.unit` and `@pytest.mark.issue_21`:
    - `test_terraform_root_structure_and_providers`: Asserts `main.tf`, `variables.tf`, `outputs.tf`, `versions.tf` exist, validates AWS provider constraints.
    - `test_terraform_module_definitions_exist`: Checks that all 5 child modules (`vpc`, `rds`, `elasticache`, `s3`, `ecs`) have `main.tf`, `variables.tf`, and `outputs.tf`.
    - `test_vpc_module_security_groups_and_subnets`: Checks VPC module declares public, private app, and database subnets, plus security groups for ALB, ECS, RDS, and Redis.
    - `test_rds_module_security_and_pgvector`: Asserts RDS is not publicly accessible, has storage encryption enabled, and configures the `pgvector` parameter group.
    - `test_elasticache_module_encryption`: Asserts Redis replication group enables encryption at rest and in transit.
    - `test_s3_data_lake_security`: Asserts S3 module enforces public access block and server-side encryption.
    - `test_ecs_fargate_services_and_alb`: Asserts ECS defines Fargate launch type, task definitions for API and worker, ALB target group with `/health` check.
    - `test_makefile_terraform_targets`: Asserts `terraform-fmt` and `terraform-validate` exist in `Makefile`.

### 6. Verification & Quality Gates
```bash
make test-issue ID=21
.venv/bin/pytest tests/ --cov=src --cov-fail-under=80
make check
```

### 7. Git & Issue Finish
```bash
make finish-issue ID=21 MSG="feat(infra): implement production Terraform Infrastructure as Code for AWS deployment"
```
