output "vpc_id" {
  value = aws_vpc.main.id
}

output "public_subnet_ids" {
  value = [for s in aws_subnet.public : s.id]
}

output "private_subnet_ids" {
  value = [for s in aws_subnet.private : s.id]
}

output "data_lake_bucket" {
  description = "S3 bucket data-pipeline writes to when SINK_MODE=s3."
  value       = aws_s3_bucket.data_lake.bucket
}

output "rds_endpoint" {
  description = "host:port for the Postgres instance."
  value       = aws_db_instance.main.endpoint
}

output "rds_address" {
  description = "Hostname only, for building connection strings."
  value       = aws_db_instance.main.address
}

output "db_password_secret_name" {
  value = aws_secretsmanager_secret.db_password.name
}

output "anthropic_secret_name" {
  description = "Set its value with: aws secretsmanager put-secret-value --secret-id <this> --secret-string sk-ant-..."
  value       = aws_secretsmanager_secret.anthropic_api_key.name
}

output "aws_region" {
  value = var.aws_region
}

output "alb_url" {
  description = "Public entry point: agent-ui by default, order-service on /orders."
  value       = "http://${aws_lb.main.dns_name}"
}

output "msk_bootstrap_brokers" {
  description = "IAM-auth bootstrap string, injected into Kafka-using services."
  value       = aws_msk_cluster.main.bootstrap_brokers_sasl_iam
}

output "ecr_repository_urls" {
  value = { for k, v in aws_ecr_repository.services : k => v.repository_url }
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "github_actions_role_arn" {
  description = "Set as the AWS_ROLE_ARN variable in the GitHub repository."
  value       = aws_iam_role.github_actions.arn
}