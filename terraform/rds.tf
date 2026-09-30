# One Postgres instance hosting four logically separate databases (orders,
# payments, inventory, agent_knowledge).
#
# Locally each service has its own Postgres container, matching
# database-per-service. Here they share an instance to keep the demo cheap
# (~$0.02/hr instead of ~$0.08/hr) and to halve provisioning time. The
# separation is preserved logically — separate databases, and each service
# only ever receives a connection string for its own. Splitting them into
# four instances is a variable change, not a redesign.

resource "aws_db_subnet_group" "main" {
  name       = "${local.name_prefix}-db-subnets"
  # Public subnets, because publicly_accessible only works where the subnet
  # routes to an internet gateway — in the private subnets the instance gets
  # a public IP that nothing can reach. This is what makes running migrations
  # from a laptop possible.
  #
  # Exposure is still controlled by the security group, which allows only
  # admin_ip_cidr and the ECS tasks. A production database would sit in the
  # private subnets with no public access at all, reached through a bastion
  # or an in-VPC task.
  subnet_ids = [for s in aws_subnet.public : s.id]

  tags = { Name = "${local.name_prefix}-db-subnets" }
}

resource "random_password" "db" {
  length  = 24
  special = false # avoids characters needing percent-encoding in a URL
}

resource "aws_db_instance" "main" {
  identifier     = "${local.name_prefix}-postgres"
  engine         = "postgres"
  engine_version = "16"
  instance_class = var.db_instance_class

  allocated_storage = 20
  storage_type      = "gp3"
  storage_encrypted = true

  # RDS creates exactly one database at launch. The other three are created
  # by scripts/bootstrap_databases.sh after apply — see terraform/README.md.
  db_name  = "orders"
  username = var.db_username
  password = random_password.db.result

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  # Publicly reachable only when admin_ip_cidr is set, and even then the
  # security group restricts it to that one address. Demo convenience so
  # migrations can run from a laptop; a production instance would stay
  # private with access via a bastion or an in-VPC task.
  publicly_accessible = var.admin_ip_cidr != ""

  # Demo settings: no HA, no backups, no deletion guard — all chosen so the
  # stack is cheap to create and quick to destroy.
  multi_az                = false
  backup_retention_period = 0
  skip_final_snapshot     = true
  deletion_protection     = false
  apply_immediately       = true

  tags = { Name = "${local.name_prefix}-postgres" }
}
