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

variable "msk_instance_type" {
  description = "MSK broker instance type. kafka.t3.small is the cheapest MSK supports."
  type        = string
  default     = "kafka.t3.small"
}

variable "msk_ebs_volume_size" {
  description = "EBS storage per broker, in GB."
  type        = number
  default     = 20
}

variable "image_tag" {
  description = "Container image tag deployed by ECS. CI overrides this with the commit SHA."
  type        = string
  default     = "latest"
}

variable "github_repo" {
  description = "GitHub repository allowed to deploy, as owner/name (e.g. octocat/my-repo)."
  type        = string
  # No default: must be supplied, so a fork can never trust the wrong repo.

  validation {
    condition     = can(regex("^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$", var.github_repo))
    error_message = "github_repo must look like owner/name."
  }
}