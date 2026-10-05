# ==============================================================================
# RDS PostgreSQL with pgvector Module
# ==============================================================================

resource "aws_db_subnet_group" "rds" {
  name        = "${var.project_name}-${var.environment}-db-subnet-group"
  description = "Subnet group for RDS PostgreSQL database in isolated private subnets"
  subnet_ids  = var.subnet_ids

  tags = {
    Name        = "${var.project_name}-${var.environment}-db-subnet-group"
    Environment = var.environment
  }
}

# Parameter group enabling the pgvector extension on PostgreSQL 16
resource "aws_db_parameter_group" "rds" {
  name        = "${var.project_name}-${var.environment}-pg16-vector"
  family      = "postgres16"
  description = "PostgreSQL 16 parameter group with pgvector enabled"

  parameter {
    name  = "shared_preload_libraries"
    value = "pgvector"
  }

  tags = {
    Name        = "${var.project_name}-${var.environment}-pg16-vector"
    Environment = var.environment
  }
}

# Master Database Password
resource "random_password" "master_password" {
  length  = 24
  special = false
}

resource "aws_db_instance" "postgres" {
  identifier     = "${var.project_name}-${var.environment}-postgres"
  engine         = "postgres"
  engine_version = "16.2"
  instance_class = var.instance_class

  allocated_storage     = var.allocated_storage
  max_allocated_storage = 100
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = var.db_name
  username = var.db_username
  password = random_password.master_password.result

  db_subnet_group_name   = aws_db_subnet_group.rds.name
  parameter_group_name   = aws_db_parameter_group.rds.name
  vpc_security_group_ids = var.security_group_ids

  publicly_accessible = false
  multi_az            = var.multi_az

  backup_retention_period    = 7
  backup_window              = "03:00-04:00"
  maintenance_window         = "Mon:04:00-Mon:05:00"
  auto_minor_version_upgrade = true

  skip_final_snapshot = true
  deletion_protection = false

  tags = {
    Name        = "${var.project_name}-${var.environment}-postgres"
    Environment = var.environment
  }
}
