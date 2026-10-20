# MSK: provisioned, two brokers, IAM authentication.
#
# Provisioned rather than Serverless purely on cost: Serverless bills ~$0.86
# per cluster-hour regardless of load, while two kafka.t3.small brokers run
# ~$0.10/hour. For a cluster that idles between demos, that is a large
# difference for no functional gain.
#
# Two brokers is the minimum MSK accepts, one per AZ.

resource "aws_security_group" "msk" {
  name        = "${local.name_prefix}-msk-sg"
  description = "MSK brokers: IAM-auth TLS port, from ECS tasks only."
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Kafka IAM auth (SASL_SSL) from ECS tasks"
    from_port       = 9098
    to_port         = 9098
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs_tasks.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name_prefix}-msk-sg" }
}

# Mirrors the local Kafka setup: topics are created explicitly, never
# implicitly on first produce. Replication factor 2 matches the broker
# count; min.insync.replicas 1 keeps writes available if one broker is down.
resource "aws_msk_configuration" "main" {
  name              = "${local.name_prefix}-config"
  kafka_versions    = ["3.7.x"]
  server_properties = <<-PROPERTIES
    auto.create.topics.enable=false
    default.replication.factor=2
    min.insync.replicas=1
    num.partitions=3
  PROPERTIES
}

resource "aws_cloudwatch_log_group" "msk" {
  name              = "/${local.name_prefix}/msk"
  retention_in_days = 7
}

resource "aws_msk_cluster" "main" {
  cluster_name           = "${local.name_prefix}-kafka"
  kafka_version          = "3.7.x"
  number_of_broker_nodes = length(var.availability_zones)

  broker_node_group_info {
    instance_type   = var.msk_instance_type
    client_subnets  = [for s in aws_subnet.private : s.id]
    security_groups = [aws_security_group.msk.id]

    storage_info {
      ebs_storage_info { volume_size = var.msk_ebs_volume_size }
    }
  }

  configuration_info {
    arn      = aws_msk_configuration.main.arn
    revision = aws_msk_configuration.main.latest_revision
  }

  # IAM auth: clients sign requests with their AWS credentials instead of
  # presenting a stored password. On ECS that credential is the task role,
  # so no secret exists to leak or rotate. TLS in transit is required for it.
  client_authentication {
    sasl { iam = true }
  }

  encryption_info {
    encryption_in_transit {
      client_broker = "TLS"
      in_cluster    = true
    }
  }

  logging_info {
    broker_logs {
      cloudwatch_logs {
        enabled   = true
        log_group = aws_cloudwatch_log_group.msk.name
      }
    }
  }

  tags = { Name = "${local.name_prefix}-kafka" }
}
