"""Unit tests for Terraform Infrastructure as Code (IaC) configuration.

Validates Terraform root structure, AWS provider constraints, networking security
groups, RDS pgvector configuration, ElastiCache encryption, S3 public access blocks,
ECS Fargate task definitions, and Makefile targets.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.issue_21]

TERRAFORM_DIR = Path("infra/terraform")


def test_terraform_root_structure_and_providers() -> None:
    """Validate root Terraform files exist and enforce provider version constraints."""
    required_files = [
        TERRAFORM_DIR / "versions.tf",
        TERRAFORM_DIR / "variables.tf",
        TERRAFORM_DIR / "main.tf",
        TERRAFORM_DIR / "outputs.tf",
        TERRAFORM_DIR / "terraform.tfvars.example",
    ]
    for file_path in required_files:
        assert file_path.exists(), f"Missing required Terraform root file: {file_path}"

    versions_content = (TERRAFORM_DIR / "versions.tf").read_text(encoding="utf-8")
    assert "hashicorp/aws" in versions_content
    assert "~> 5.0" in versions_content
    assert ">= 1.5.0" in versions_content

    main_content = (TERRAFORM_DIR / "main.tf").read_text(encoding="utf-8")
    assert 'provider "aws"' in main_content
    assert "default_tags" in main_content
    assert "ManagedBy" in main_content


def test_terraform_module_definitions_exist() -> None:
    """Validate all required child modules exist with complete module contracts."""
    modules = ["vpc", "rds", "elasticache", "s3", "ecs"]
    main_content = (TERRAFORM_DIR / "main.tf").read_text(encoding="utf-8")

    for mod in modules:
        mod_dir = TERRAFORM_DIR / "modules" / mod
        assert mod_dir.is_dir(), f"Module directory missing: {mod_dir}"
        assert (mod_dir / "main.tf").exists(), f"Missing main.tf in module {mod}"
        assert (mod_dir / "variables.tf").exists(), f"Missing variables.tf in module {mod}"
        assert (mod_dir / "outputs.tf").exists(), f"Missing outputs.tf in module {mod}"
        assert f'module "{mod}"' in main_content, f"Root main.tf must instantiate module '{mod}'"


def test_vpc_module_subnets_and_security_groups() -> None:
    """Validate VPC module declares multi-tier subnets and least-privilege security groups."""
    vpc_main = (TERRAFORM_DIR / "modules/vpc/main.tf").read_text(encoding="utf-8")

    # Networking resources
    assert 'resource "aws_vpc" "main"' in vpc_main
    assert 'resource "aws_internet_gateway" "gw"' in vpc_main
    assert 'resource "aws_nat_gateway" "nat"' in vpc_main
    assert 'resource "aws_subnet" "public"' in vpc_main
    assert 'resource "aws_subnet" "private_app"' in vpc_main
    assert 'resource "aws_subnet" "private_db"' in vpc_main

    # Security groups
    assert 'resource "aws_security_group" "alb"' in vpc_main
    assert 'resource "aws_security_group" "ecs_app"' in vpc_main
    assert 'resource "aws_security_group" "rds"' in vpc_main
    assert 'resource "aws_security_group" "redis"' in vpc_main

    # Security rules: ALB allows 80/443; ECS allows port from ALB;
    # RDS allows 5432 from ECS; Redis allows 6379 from ECS
    assert "from_port   = 80" in vpc_main
    assert "from_port   = 443" in vpc_main
    assert "to_port         = 5432" in vpc_main
    assert "security_groups = [aws_security_group.ecs_app.id]" in vpc_main
    assert "to_port         = 6379" in vpc_main


def test_rds_module_security_and_pgvector() -> None:
    """Validate RDS PostgreSQL 16 module enforces encryption, non-public access, and pgvector."""
    rds_main = (TERRAFORM_DIR / "modules/rds/main.tf").read_text(encoding="utf-8")

    assert 'resource "aws_db_parameter_group" "rds"' in rds_main
    assert 'family      = "postgres16"' in rds_main
    assert "shared_preload_libraries" in rds_main
    assert "pgvector" in rds_main

    assert 'resource "aws_db_instance" "postgres"' in rds_main
    assert "storage_encrypted     = true" in rds_main
    assert "publicly_accessible = false" in rds_main
    assert "aws_db_subnet_group.rds.name" in rds_main


def test_elasticache_module_encryption() -> None:
    """Validate ElastiCache Redis module configures cluster encryption in transit and at rest."""
    redis_main = (TERRAFORM_DIR / "modules/elasticache/main.tf").read_text(encoding="utf-8")

    assert 'resource "aws_elasticache_replication_group" "redis"' in redis_main
    assert 'engine         = "redis"' in redis_main
    assert "at_rest_encryption_enabled = true" in redis_main
    assert "transit_encryption_enabled = true" in redis_main
    assert "auth_token" in redis_main
    assert "automatic_failover_enabled = true" in redis_main


def test_s3_data_lake_security() -> None:
    """Validate S3 data lake module enforces public access block, encryption, and versioning."""
    s3_main = (TERRAFORM_DIR / "modules/s3/main.tf").read_text(encoding="utf-8")

    assert 'resource "aws_s3_bucket" "data_lake"' in s3_main
    assert 'resource "aws_s3_bucket_public_access_block" "data_lake"' in s3_main
    assert "block_public_acls       = true" in s3_main
    assert "block_public_policy     = true" in s3_main
    assert "restrict_public_buckets = true" in s3_main

    assert 'resource "aws_s3_bucket_server_side_encryption_configuration" "data_lake"' in s3_main
    assert "apply_server_side_encryption_by_default" in s3_main
    assert 'resource "aws_s3_bucket_versioning" "data_lake"' in s3_main
    assert 'status = "Enabled"' in s3_main


def test_ecs_fargate_services_and_alb() -> None:
    """Validate ECS module defines Fargate tasks, ALB with /health check, and CloudWatch logs."""
    ecs_main = (TERRAFORM_DIR / "modules/ecs/main.tf").read_text(encoding="utf-8")

    assert 'resource "aws_ecs_cluster" "main"' in ecs_main
    assert 'resource "aws_cloudwatch_log_group" "ecs"' in ecs_main

    # ALB target group with health check
    assert 'resource "aws_lb" "alb"' in ecs_main
    assert 'resource "aws_lb_target_group" "api"' in ecs_main
    assert 'path                = "/health"' in ecs_main

    # Task definitions & Fargate
    assert 'resource "aws_ecs_task_definition" "api"' in ecs_main
    assert 'resource "aws_ecs_task_definition" "worker"' in ecs_main
    assert 'requires_compatibilities = ["FARGATE"]' in ecs_main

    # ECS services
    assert 'resource "aws_ecs_service" "api"' in ecs_main
    assert 'resource "aws_ecs_service" "worker"' in ecs_main


def test_makefile_terraform_targets() -> None:
    """Validate Makefile contains terraform-fmt and terraform-validate targets."""
    makefile_content = Path("Makefile").read_text(encoding="utf-8")

    assert "terraform-fmt:" in makefile_content
    assert "terraform-validate:" in makefile_content
    assert "terraform -chdir=infra/terraform fmt -recursive" in makefile_content
    assert "terraform -chdir=infra/terraform validate" in makefile_content
