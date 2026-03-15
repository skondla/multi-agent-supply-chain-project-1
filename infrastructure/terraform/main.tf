terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.24"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.12"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.5"
    }
  }

  backend "s3" {
    bucket         = "supply-chain-terraform-state"
    key            = "supply-chain/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "supply-chain-terraform-locks"
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "supply-chain-ai"
      Environment = var.environment
      ManagedBy   = "terraform"
      Owner       = "platform-team"
    }
  }
}

provider "kubernetes" {
  host                   = module.eks.cluster_endpoint
  cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)
  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    args        = ["eks", "get-token", "--cluster-name", module.eks.cluster_name]
    command     = "aws"
  }
}

provider "helm" {
  kubernetes {
    host                   = module.eks.cluster_endpoint
    cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)
    exec {
      api_version = "client.authentication.k8s.io/v1beta1"
      args        = ["eks", "get-token", "--cluster-name", module.eks.cluster_name]
      command     = "aws"
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_availability_zones" "available" { state = "available" }

# ── Modules ───────────────────────────────────────────────────────────────────
module "vpc" {
  source = "./modules/vpc"

  environment           = var.environment
  aws_region            = var.aws_region
  vpc_cidr              = var.vpc_cidr
  availability_zones    = slice(data.aws_availability_zones.available.names, 0, 3)
  public_subnet_cidrs   = var.public_subnet_cidrs
  private_subnet_cidrs  = var.private_subnet_cidrs
  database_subnet_cidrs = var.database_subnet_cidrs
}

module "eks" {
  source = "./modules/eks"

  environment         = var.environment
  cluster_name        = "${var.project_name}-${var.environment}"
  vpc_id              = module.vpc.vpc_id
  private_subnet_ids  = module.vpc.private_subnet_ids
  kubernetes_version  = var.kubernetes_version
  node_instance_types = var.node_instance_types
  min_nodes           = var.min_nodes
  max_nodes           = var.max_nodes
  desired_nodes       = var.desired_nodes

  depends_on = [module.vpc]
}

module "rds" {
  source = "./modules/rds"

  environment           = var.environment
  project_name          = var.project_name
  vpc_id                = module.vpc.vpc_id
  database_subnet_ids   = module.vpc.database_subnet_ids
  eks_security_group_id = module.eks.node_security_group_id
  db_instance_class     = var.db_instance_class
  db_name               = var.db_name
  db_username           = var.db_username
  allocated_storage     = var.db_allocated_storage
  multi_az              = var.environment == "production"

  depends_on = [module.vpc]
}

module "elasticache" {
  source = "./modules/elasticache"

  environment           = var.environment
  project_name          = var.project_name
  vpc_id                = module.vpc.vpc_id
  private_subnet_ids    = module.vpc.private_subnet_ids
  eks_security_group_id = module.eks.node_security_group_id
  node_type             = var.redis_node_type
  num_cache_nodes       = var.environment == "production" ? 3 : 1

  depends_on = [module.vpc]
}

module "msk" {
  source = "./modules/msk"

  environment             = var.environment
  project_name            = var.project_name
  vpc_id                  = module.vpc.vpc_id
  private_subnet_ids      = slice(module.vpc.private_subnet_ids, 0, 3)
  eks_security_group_id   = module.eks.node_security_group_id
  broker_instance_type    = var.kafka_broker_instance_type
  number_of_broker_nodes  = var.environment == "production" ? 3 : 1
  kafka_version           = "3.5.1"

  depends_on = [module.vpc]
}

module "ecr" {
  source = "./modules/ecr"

  environment  = var.environment
  project_name = var.project_name
  repositories = ["supply-chain-api", "supply-chain-worker", "supply-chain-ml"]
}

# ── S3 ────────────────────────────────────────────────────────────────────────
resource "aws_s3_bucket" "mlflow_artifacts" {
  bucket = "${var.project_name}-mlflow-${var.environment}-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_versioning" "mlflow_artifacts" {
  bucket = aws_s3_bucket.mlflow_artifacts.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "mlflow_artifacts" {
  bucket = aws_s3_bucket.mlflow_artifacts.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_s3_bucket_public_access_block" "mlflow_artifacts" {
  bucket                  = aws_s3_bucket.mlflow_artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ── KMS ───────────────────────────────────────────────────────────────────────
resource "aws_kms_key" "supply_chain" {
  description             = "Supply Chain AI Platform encryption key"
  deletion_window_in_days = 7
  enable_key_rotation     = true
}

resource "aws_kms_alias" "supply_chain" {
  name          = "alias/${var.project_name}-${var.environment}"
  target_key_id = aws_kms_key.supply_chain.key_id
}

# ── WAF ───────────────────────────────────────────────────────────────────────
resource "aws_wafv2_web_acl" "api_waf" {
  name  = "${var.project_name}-api-waf-${var.environment}"
  scope = "REGIONAL"

  default_action { allow {} }

  rule {
    name     = "AWSManagedRulesCommonRuleSet"
    priority = 1
    override_action { none {} }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "CommonRuleSetMetric"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "RateLimitRule"
    priority = 2
    action { block {} }
    statement {
      rate_based_statement {
        limit              = 2000
        aggregate_key_type = "IP"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "RateLimitMetric"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${var.project_name}-waf"
    sampled_requests_enabled   = true
  }
}
