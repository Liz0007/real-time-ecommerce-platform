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