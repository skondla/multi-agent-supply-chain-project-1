resource "random_password" "redis_auth" {
  length  = 32
  special = false
}

resource "aws_secretsmanager_secret" "redis_auth" {
  name                    = "supply-chain/${var.environment}/redis-auth"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "redis_auth" {
  secret_id     = aws_secretsmanager_secret.redis_auth.id
  secret_string = jsonencode({ auth_token = random_password.redis_auth.result })
}

resource "aws_security_group" "redis" {
  name        = "supply-chain-redis-sg-${var.environment}"
  description = "Security group for ElastiCache Redis"
  vpc_id      = var.vpc_id

  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [var.eks_security_group_id]
    description     = "Redis from EKS nodes"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "supply-chain-redis-sg-${var.environment}" }
}

resource "aws_elasticache_subnet_group" "main" {
  name       = "supply-chain-redis-subnet-${var.environment}"
  subnet_ids = var.private_subnet_ids
}

resource "aws_elasticache_parameter_group" "main" {
  name   = "supply-chain-redis7-${var.environment}"
  family = "redis7"

  parameter {
    name  = "maxmemory-policy"
    value = "allkeys-lru"
  }
  parameter {
    name  = "activerehashing"
    value = "yes"
  }
}

resource "aws_elasticache_replication_group" "main" {
  replication_group_id       = "supply-chain-${var.environment}"
  description                = "Supply Chain Redis cluster - ${var.environment}"
  node_type                  = var.node_type
  num_cache_clusters         = var.num_cache_nodes
  parameter_group_name       = aws_elasticache_parameter_group.main.name
  subnet_group_name          = aws_elasticache_subnet_group.main.name
  security_group_ids         = [aws_security_group.redis.id]
  engine_version             = "7.0"
  port                       = 6379
  auth_token                 = random_password.redis_auth.result
  transit_encryption_enabled = true
  at_rest_encryption_enabled = true
  automatic_failover_enabled = var.num_cache_nodes > 1
  multi_az_enabled           = var.num_cache_nodes > 1

  snapshot_retention_limit = var.environment == "production" ? 7 : 1
  snapshot_window          = "03:00-04:00"
  maintenance_window       = "sun:04:00-sun:05:00"

  tags = { Name = "supply-chain-redis-${var.environment}" }
}
