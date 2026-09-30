# recovery_window_in_days = 0 on both secrets: without it, a destroyed secret
# is only scheduled for deletion (7-30 days) and its name stays reserved, so
# the next `terraform apply` fails with "already scheduled for deletion".
# That makes repeated create/destroy cycles impossible, which is exactly the
# workflow this stack is built for.

resource "aws_secretsmanager_secret" "db_password" {
  name                    = "${local.name_prefix}/db-password"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "db_password" {
  secret_id     = aws_secretsmanager_secret.db_password.id
  secret_string = random_password.db.result
}

# Deliberately created empty: the value is set out-of-band with the AWS CLI
# so the API key never enters terraform.tfstate (which is plaintext JSON on
# disk). See terraform/README.md for the command.
resource "aws_secretsmanager_secret" "anthropic_api_key" {
  name                    = "${local.name_prefix}/anthropic-api-key"
  recovery_window_in_days = 0

  description = "Set manually: aws secretsmanager put-secret-value --secret-id <name> --secret-string <key>"
}
