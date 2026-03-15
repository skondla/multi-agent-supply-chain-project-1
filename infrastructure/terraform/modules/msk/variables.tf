variable "environment" { type = string }
variable "project_name" { type = string }
variable "vpc_id" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "eks_security_group_id" { type = string }
variable "broker_instance_type" { type = string }
variable "number_of_broker_nodes" { type = number }
variable "kafka_version" { type = string }
