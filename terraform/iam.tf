# Two kinds of role per the ECS model:
#
#   execution role - used by ECS itself, before the container starts: pull
#                    the image, fetch secrets, write logs. Shared by all.
#   task role      - the identity the application code runs as. One per
#                    service, carrying only what that service needs.
#
# The split matters for MSK IAM auth: the Kafka token is signed with the
# TASK role's credentials, which is why each Kafka-using service gets the
# MSK policy on its own role rather than a shared one.

data "aws_iam_policy_document" "ecs_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# --- execution role (shared) ---

resource "aws_iam_role" "ecs_execution" {
  name               = "${local.name_prefix}-ecs-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "ecs_execution_managed" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Secrets are injected by ECS *before* the container runs, so this
# permission belongs to the execution role, not the task role. A common
# mix-up, and the failure mode is a task that never starts.
data "aws_iam_policy_document" "execution_secrets" {
  statement {
    effect  = "Allow"
    actions = ["secretsmanager:GetSecretValue"]
    resources = concat(
      [for s in aws_secretsmanager_secret.service_db_url : s.arn],
      [aws_secretsmanager_secret.anthropic_api_key.arn],
    )
  }
}

resource "aws_iam_role_policy" "execution_secrets" {
  name   = "${local.name_prefix}-execution-secrets"
  role   = aws_iam_role.ecs_execution.id
  policy = data.aws_iam_policy_document.execution_secrets.json
}

# --- task roles (one per service) ---

resource "aws_iam_role" "task" {
  for_each = local.services

  name               = "${local.name_prefix}-${each.key}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

data "aws_iam_policy_document" "kafka_access" {
  statement {
    sid       = "Cluster"
    effect    = "Allow"
    actions   = ["kafka-cluster:Connect", "kafka-cluster:DescribeCluster"]
    resources = [aws_msk_cluster.main.arn]
  }
  statement {
    sid    = "Topics"
    effect = "Allow"
    actions = [
      "kafka-cluster:DescribeTopic",
      "kafka-cluster:CreateTopic",
      "kafka-cluster:WriteData",
      "kafka-cluster:ReadData",
    ]
    resources = ["arn:aws:kafka:${var.aws_region}:${data.aws_caller_identity.current.account_id}:topic/${aws_msk_cluster.main.cluster_name}/*"]
  }
  statement {
    sid       = "ConsumerGroups"
    effect    = "Allow"
    actions   = ["kafka-cluster:AlterGroup", "kafka-cluster:DescribeGroup"]
    resources = ["arn:aws:kafka:${var.aws_region}:${data.aws_caller_identity.current.account_id}:group/${aws_msk_cluster.main.cluster_name}/*"]
  }
}

resource "aws_iam_policy" "kafka_access" {
  name   = "${local.name_prefix}-kafka-access"
  policy = data.aws_iam_policy_document.kafka_access.json
}

resource "aws_iam_role_policy_attachment" "task_kafka" {
  for_each = { for k, v in local.services : k => v if v.needs_kafka }

  role       = aws_iam_role.task[each.key].name
  policy_arn = aws_iam_policy.kafka_access.arn
}

data "aws_iam_policy_document" "s3_access" {
  statement {
    effect    = "Allow"
    actions   = ["s3:PutObject", "s3:GetObject", "s3:ListBucket"]
    resources = [aws_s3_bucket.data_lake.arn, "${aws_s3_bucket.data_lake.arn}/*"]
  }
}

resource "aws_iam_policy" "s3_access" {
  name   = "${local.name_prefix}-s3-access"
  policy = data.aws_iam_policy_document.s3_access.json
}

resource "aws_iam_role_policy_attachment" "task_s3" {
  for_each = { for k, v in local.services : k => v if v.needs_s3 }

  role       = aws_iam_role.task[each.key].name
  policy_arn = aws_iam_policy.s3_access.arn
}

data "aws_caller_identity" "current" {}
