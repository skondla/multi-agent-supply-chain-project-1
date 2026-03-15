variable "environment" { type = string }
variable "project_name" { type = string }
variable "vpc_id" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "eks_security_group_id" { type = string }
variable "node_type" { type = string }
variable "num_cache_nodes" {
  type    = number
  default = 1
}
