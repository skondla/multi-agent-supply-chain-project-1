output "primary_endpoint" { value = aws_elasticache_replication_group.main.primary_endpoint_address }
output "reader_endpoint" { value = aws_elasticache_replication_group.main.reader_endpoint_address }
output "port" { value = aws_elasticache_replication_group.main.port }
output "secret_arn" { value = aws_secretsmanager_secret.redis_auth.arn }
