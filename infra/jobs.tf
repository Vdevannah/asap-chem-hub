# Ingestion on ECS Fargate (ARM64, 0.25 vCPU / 0.5 GB), image from Dockerfile.jobs.
#   jobs  : scheduled ingestion - DB login as asap_jobs (RDS IAM auth), API keys from SSM
#   admin : one-off migration / schema tasks - DB login as the master user (RDS-managed secret)

resource "aws_ecr_repository" "jobs" {
  name                 = "${local.name}-jobs"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "jobs" {
  repository = aws_ecr_repository.jobs.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the last 5 images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 5 }
      action       = { type = "expire" }
    }]
  })
}

resource "aws_ecs_cluster" "jobs" {
  name = local.name
  setting {
    name  = "containerInsights"
    value = "disabled"
  }
}

resource "aws_cloudwatch_log_group" "jobs" {
  name              = "/ecs/${local.name}-jobs"
  retention_in_days = 14
}

locals {
  jobs_image = "${aws_ecr_repository.jobs.repository_url}:${var.jobs_image_tag}"
  # SSM parameter ARNs only - Terraform never reads the values
  ssm_arns = { for n in var.ssm_parameter_names : n => "arn:aws:ssm:${local.region}:${local.account_id}:parameter/${local.name}/${n}" }
  db_env = [
    { name = "DB_HOST", value = aws_db_instance.db.address },
    { name = "DB_PORT", value = tostring(aws_db_instance.db.port) },
    { name = "DB_NAME", value = var.db_name },
    { name = "DB_SSL_CA", value = "/app/certs/global-bundle.pem" },
    { name = "AWS_REGION", value = local.region },
  ]
  master_secret_arn = aws_db_instance.db.master_user_secret[0].secret_arn
}

# --- IAM -------------------------------------------------------------------------------------
data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

# execution roles: pull the image, write logs, inject secrets at container start
resource "aws_iam_role" "jobs_execution" {
  name               = "${local.name}-jobs-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role" "admin_execution" {
  name               = "${local.name}-admin-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role_policy_attachment" "jobs_execution" {
  role       = aws_iam_role.jobs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy_attachment" "admin_execution" {
  role       = aws_iam_role.admin_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "jobs_execution_ssm" {
  statement {
    actions   = ["ssm:GetParameters"]
    resources = values(local.ssm_arns)
  }
}

resource "aws_iam_role_policy" "jobs_execution_ssm" {
  name   = "read-api-keys"
  role   = aws_iam_role.jobs_execution.id
  policy = data.aws_iam_policy_document.jobs_execution_ssm.json
}

data "aws_iam_policy_document" "admin_execution_secret" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [local.master_secret_arn]
  }
}

resource "aws_iam_role_policy" "admin_execution_secret" {
  name   = "read-db-master-secret"
  role   = aws_iam_role.admin_execution.id
  policy = data.aws_iam_policy_document.admin_execution_secret.json
}

# task roles: what the running code may do
resource "aws_iam_role" "jobs_task" {
  name               = "${local.name}-jobs-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role" "admin_task" {
  name               = "${local.name}-admin-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

data "aws_iam_policy_document" "jobs_task" {
  statement {
    actions   = ["rds-db:connect"]
    resources = ["arn:aws:rds-db:${local.region}:${local.account_id}:dbuser:${aws_db_instance.db.resource_id}/asap_jobs"]
  }
}

resource "aws_iam_role_policy" "jobs_task" {
  name   = "rds-iam-connect"
  role   = aws_iam_role.jobs_task.id
  policy = data.aws_iam_policy_document.jobs_task.json
}

data "aws_iam_policy_document" "admin_task" {
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.artifacts.arn}/migration/*"]
  }
}

resource "aws_iam_role_policy" "admin_task" {
  name   = "read-migration-export"
  role   = aws_iam_role.admin_task.id
  policy = data.aws_iam_policy_document.admin_task.json
}

# --- task definitions --------------------------------------------------------------------------
resource "aws_ecs_task_definition" "jobs" {
  family                   = "${local.name}-jobs"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.jobs_execution.arn
  task_role_arn            = aws_iam_role.jobs_task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "ARM64"
  }

  container_definitions = jsonencode([{
    name      = "jobs"
    image     = local.jobs_image
    essential = true
    command   = ["articles"]
    environment = concat(local.db_env, [
      { name = "DB_USER", value = "asap_jobs" },
      { name = "DB_AUTH", value = "iam" },
    ])
    secrets = [for n, arn in local.ssm_arns : { name = n, valueFrom = arn }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.jobs.name
        "awslogs-region"        = local.region
        "awslogs-stream-prefix" = "jobs"
      }
    }
  }])
}

resource "aws_ecs_task_definition" "admin" {
  family                   = "${local.name}-admin"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.admin_execution.arn
  task_role_arn            = aws_iam_role.admin_task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "ARM64"
  }

  container_definitions = jsonencode([{
    name      = "admin"
    image     = local.jobs_image
    essential = true
    command   = ["import", "--help"]
    environment = concat(local.db_env, [
      { name = "DB_USER", value = var.db_master_username },
      { name = "DB_AUTH", value = "password" },
    ])
    # the "password" key of the RDS-managed master secret, injected at start (never in Terraform)
    secrets = [{ name = "DB_PASSWORD", valueFrom = "${local.master_secret_arn}:password::" }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.jobs.name
        "awslogs-region"        = local.region
        "awslogs-stream-prefix" = "admin"
      }
    }
  }])
}
