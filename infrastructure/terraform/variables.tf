variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "supply-chain"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  validation {
    condition     = contains(["development", "staging", "production"], var.environment)
    error_message = "Environment must be development, staging, or production."
  }
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "vpc_cidr" {
  description = "VPC CIDR block"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidrs" {
  type    = list(string)
  default = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
}

variable "private_subnet_cidrs" {
  type    = list(string)
  default = ["10.0.10.0/24", "10.0.11.0/24", "10.0.12.0/24"]
}

variable "database_subnet_cidrs" {
  type    = list(string)
  default = ["10.0.20.0/24", "10.0.21.0/24", "10.0.22.0/24"]
}

variable "kubernetes_version" {
  type    = string
  default = "1.29"
}

variable "node_instance_types" {
  type    = list(string)
  default = ["m5.xlarge", "m5.2xlarge"]
}

variable "min_nodes" {
  type    = number
  default = 3
}

variable "max_nodes" {
  type    = number
  default = 20
}

variable "desired_nodes" {
  type    = number
  default = 3
}

variable "db_instance_class" {
  type    = string
  default = "db.r6g.xlarge"
}

variable "db_name" {
  type    = string
  default = "supply_chain_db"
}

variable "db_username" {
  type      = string
  default   = "supply_chain_admin"
  sensitive = true
}

variable "db_allocated_storage" {
  type    = number
  default = 100
}

variable "redis_node_type" {
  type    = string
  default = "cache.r6g.large"
}

variable "kafka_broker_instance_type" {
  type    = string
  default = "kafka.m5.large"
}
