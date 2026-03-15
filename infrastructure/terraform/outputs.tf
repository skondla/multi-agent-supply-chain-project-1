output "vpc_id" {
  description = "VPC ID"
  value       = module.vpc.vpc_id
}

output "eks_cluster_name" {
  description = "EKS cluster name"
  value       = module.eks.cluster_name
}

output "eks_cluster_endpoint" {
  description = "EKS cluster API endpoint"
  value       = module.eks.cluster_endpoint
  sensitive   = true
}

output "rds_endpoint" {
  description = "Aurora PostgreSQL cluster endpoint"
  value       = module.rds.cluster_endpoint
  sensitive   = true
}

output "redis_endpoint" {
  description = "ElastiCache Redis primary endpoint"
  value       = module.elasticache.primary_endpoint
  sensitive   = true
}

output "kafka_bootstrap_brokers" {
  description = "MSK Kafka bootstrap brokers (TLS)"
  value       = module.msk.bootstrap_brokers_tls
  sensitive   = true
}

output "ecr_repository_urls" {
  description = "ECR repository URLs"
  value       = module.ecr.repository_urls
}

output "mlflow_bucket_name" {
  description = "S3 bucket for MLflow artifacts"
  value       = aws_s3_bucket.mlflow_artifacts.bucket
}

output "kms_key_arn" {
  description = "KMS key ARN"
  value       = aws_kms_key.supply_chain.arn
}

output "waf_web_acl_arn" {
  description = "WAF Web ACL ARN"
  value       = aws_wafv2_web_acl.api_waf.arn
}

output "aws_account_id" {
  description = "AWS Account ID"
  value       = data.aws_caller_identity.current.account_id
}
