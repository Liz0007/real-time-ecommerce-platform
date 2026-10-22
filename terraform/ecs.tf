# ECS Fargate: one task definition and one service per entry in
# local.services.
#
# Service Connect provides internal DNS, which is what lets the hardcoded
# hostnames in the application code keep working. ai-agent-service calls
# http://order-service:8000 locally via Docker's network; with Service
# Connect the same name resolves inside the cluster, so no code changes
# are needed for service-to-service calls.

resource "aws_service_discovery_http_namespace" "main" {
  name        = local.name_prefix
  description = "Service Connect namespace for ${local.name_prefix}"
}

resource "aws_ecs_cluster" "main" {
  name = "${local.name_prefix}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_cloudwatch_log_group" "services" {
  for_each = local.services

  name              = "/${local.name_prefix}/ecs/${each.key}"
  retention_in_days = 7
}

# Full connection strings, one per database-using service. ECS injects a
# secret's entire value into one env var, so the URL is assembled here
# rather than having the application build it from parts.
#
# These do land in terraform.tfstate (it holds every resource attribute in
# plaintext), which is acceptable for a demo password that lives hours and
# is why the state file is gitignored. The Anthropic key is handled
# differently — created empty, set via CLI — because it outlives the stack.
resource "aws_secretsmanager_secret" "service_db_url" {
  for_each = { for k, v in local.services : k => v if v.db != null }

  name                    = "${local.name_prefix}/${each.key}/db-url"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "service_db_url" {
  for_each = aws_secretsmanager_secret.service_db_url

  secret_id = each.value.id
  secret_string = format(
    "%s://%s:%s@%s:5432/%s",
    # SQLAlchemy services need "postgresql+asyncpg"; the agent uses plain
    # psycopg, which only accepts "postgresql". See db_url_scheme in locals.tf.
    try(local.services[each.key].db_url_scheme, "postgresql+asyncpg"),
    var.db_username,
    random_password.db.result,
    aws_db_instance.main.address,
    local.services[each.key].db,
  )
}

resource "aws_ecs_task_definition" "services" {
  for_each = local.services

  family                   = "${local.name_prefix}-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = each.value.cpu
  memory                   = each.value.memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.task[each.key].arn

  # Images are built on an Apple Silicon Mac, so the tasks run on Graviton
  # rather than forcing cross-platform builds. ARM Fargate is also cheaper.
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "ARM64"
  }

  container_definitions = jsonencode([{
    name      = each.key
    image     = "${aws_ecr_repository.services[each.key].repository_url}:${var.image_tag}"
    essential = true

    portMappings = [{
      name          = "http"
      containerPort = each.value.port
      protocol      = "tcp"
      appProtocol   = "http"
    }]

    environment = concat(
      [
        { name = "AWS_REGION", value = var.aws_region },
      ],
      each.value.needs_kafka ? [
        { name = "KAFKA_BOOTSTRAP_SERVERS", value = aws_msk_cluster.main.bootstrap_brokers_sasl_iam },
        { name = "KAFKA_SECURITY_PROTOCOL", value = "SASL_SSL" },
      ] : [],
      each.value.needs_s3 ? [
        { name = "SINK_MODE", value = "s3" },
        { name = "S3_BUCKET", value = aws_s3_bucket.data_lake.bucket },
      ] : [],
    )

    secrets = concat(
      each.value.db == null ? [] : [
        {
          name      = each.value.db_env_var
          valueFrom = aws_secretsmanager_secret.service_db_url[each.key].arn
        },
      ],
      # Set out-of-band after apply; see terraform/README.md. If it is still
      # empty when the task starts, ECS fails to launch it — a loud failure
      # rather than an agent that silently cannot answer.
      each.value.needs_anthropic ? [
        {
          name      = "ANTHROPIC_API_KEY"
          valueFrom = aws_secretsmanager_secret.anthropic_api_key.arn
        },
      ] : [],
    )

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.services[each.key].name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = each.key
      }
    }
  }])
}

resource "aws_ecs_service" "services" {
  for_each = local.services

  name            = "${local.name_prefix}-${each.key}"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.services[each.key].arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = [for s in aws_subnet.private : s.id]
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  service_connect_configuration {
    enabled   = true
    namespace = aws_service_discovery_http_namespace.main.arn

    service {
      port_name      = "http"
      discovery_name = each.key

      # Makes the service reachable at http://<name>:<port> from any other
      # task in the namespace — matching the hostnames the code already uses.
      client_alias {
        port     = each.value.port
        dns_name = each.key
      }
    }
  }

  dynamic "load_balancer" {
    for_each = length(each.value.alb_paths) > 0 ? [1] : []
    content {
      target_group_arn = aws_lb_target_group.services[each.key].arn
      container_name   = each.key
      container_port   = each.value.port
    }
  }

  depends_on = [aws_lb_listener.http]
}
