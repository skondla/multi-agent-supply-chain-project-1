variable "environment" { type = string }
variable "project_name" { type = string }
variable "vpc_id" { type = string }
variable "database_subnet_ids" { type = list(string) }
variable "eks_security_group_id" { type = string }
variable "db_instance_class" { type = string }
variable "db_name" { type = string }
variable "db_username" { type = string }
variable "allocated_storage" { type = number }
variable "multi_az" {
  type    = bool
  default = false
}
