resource "random_password" "db_password" {
  length  = 32
  special = false
}

resource "aws_secretsmanager_secret" "db_credentials" {
  name                    = "supply-chain/${var.environment}/db-credentials"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "db_credentials" {
  secret_id = aws_secretsmanager_secret.db_credentials.id
  secret_string = jsonencode({
    username = var.db_username
    password = random_password.db_password.result
    host     = aws_rds_cluster.main.endpoint
    port     = 5432
    dbname   = var.db_name
  })
}

resource "aws_db_subnet_group" "main" {
  name       = "supply-chain-db-subnet-${var.environment}"
  subnet_ids = var.database_subnet_ids
  tags       = { Name = "supply-chain-db-subnet-${var.environment}" }
}

resource "aws_security_group" "rds" {
  name        = "supply-chain-rds-sg-${var.environment}"
  description = "Security group for Aurora PostgreSQL"
  vpc_id      = var.vpc_id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [var.eks_security_group_id]
    description     = "PostgreSQL from EKS nodes"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "supply-chain-rds-sg-${var.environment}" }
}

resource "aws_rds_cluster_parameter_group" "main" {
  name   = "supply-chain-pg15-${var.environment}"
  family = "aurora-postgresql15"

  parameter {
    name  = "log_min_duration_statement"
    value = "1000"
  }
  parameter {
    name  = "shared_preload_libraries"
    value = "pg_stat_statements"
  }
  parameter {
    name  = "pg_stat_statements.track"
    value = "ALL"
  }
}

resource "aws_rds_cluster" "main" {
  cluster_identifier              = "supply-chain-${var.environment}"
  engine                          = "aurora-postgresql"
  engine_version                  = "15.4"
  database_name                   = var.db_name
  master_username                 = var.db_username
  master_password                 = random_password.db_password.result
  db_subnet_group_name            = aws_db_subnet_group.main.name
  vpc_security_group_ids          = [aws_security_group.rds.id]
  db_cluster_parameter_group_name = aws_rds_cluster_parameter_group.main.name

  backup_retention_period      = var.multi_az ? 30 : 7
  preferred_backup_window      = "03:00-04:00"
  preferred_maintenance_window = "sun:04:00-sun:05:00"
  deletion_protection          = var.multi_az
  skip_final_snapshot          = !var.multi_az
  final_snapshot_identifier    = var.multi_az ? "supply-chain-final-snapshot" : null

  storage_encrypted                   = true
  enabled_cloudwatch_logs_exports     = ["postgresql"]

  tags = { Name = "supply-chain-aurora-${var.environment}" }
}

resource "aws_rds_cluster_instance" "main" {
  count              = var.multi_az ? 2 : 1
  identifier         = "supply-chain-${var.environment}-${count.index + 1}"
  cluster_identifier = aws_rds_cluster.main.id
  instance_class     = var.db_instance_class
  engine             = aws_rds_cluster.main.engine
  engine_version     = aws_rds_cluster.main.engine_version

  performance_insights_enabled = true
  monitoring_interval          = 60
  auto_minor_version_upgrade   = true
}
