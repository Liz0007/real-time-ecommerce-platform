variable "aws_region" {
  description = "AWS region. eu-south-2 is opt-in — enable it in the account before applying."
  type        = string
  default     = "eu-south-2"
}

variable "environment" {
  description = "Environment name, used in resource names and tags."
  type        = string
  default     = "demo"
}

variable "project_name" {
  description = "Short prefix for resource names."
  type        = string
  default     = "ecommerce"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = <<-EOT
    AZs to spread subnets across. Two is the minimum MSK accepts, and
    enough for this deployment; more AZs would mean more NAT gateways or
    a shared single point of failure.
  EOT
  type        = list(string)
  default     = ["eu-south-2a", "eu-south-2b"]
}

variable "db_username" {
  description = "Master username for the RDS instance."
  type        = string
  default     = "postgres"
}

variable "db_instance_class" {
  description = "RDS instance class. db.t3.micro is the cheapest that runs Postgres 16."
  type        = string
  default     = "db.t3.micro"
}

variable "admin_ip_cidr" {
  description = <<-EOT
    Your public IP in CIDR form (e.g. "203.0.113.4/32"), used to allow psql
    access to RDS from your laptop so migrations can be run without building
    an in-VPC task. Find it with: curl -s ifconfig.me

    Leave empty to disable direct access entirely. DEMO CONVENIENCE ONLY —
    a production database would not be publicly reachable at all.
  EOT
  type        = string
  default     = ""
}
