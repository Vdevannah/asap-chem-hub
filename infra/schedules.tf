# EventBridge Scheduler -> ECS RunTask (Fargate, public subnet + public IP, no NAT).
# Created DISABLED (var.schedules_enabled = false) until the data migration is verified.

resource "aws_scheduler_schedule_group" "jobs" {
  name = local.name
}

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${local.name}-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

data "aws_iam_policy_document" "scheduler" {
  statement {
    actions = ["ecs:RunTask"]
    resources = [aws_ecs_task_definition.jobs.arn_without_revision,
    "${aws_ecs_task_definition.jobs.arn_without_revision}:*"]
    condition {
      test     = "ArnEquals"
      variable = "ecs:cluster"
      values   = [aws_ecs_cluster.jobs.arn]
    }
  }
  statement {
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.jobs_execution.arn, aws_iam_role.jobs_task.arn]
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "scheduler" {
  name   = "run-jobs-task"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler.json
}

locals {
  # same commands as scripts/run_articles.sh (jobs/run_job.sh)
  schedules = {
    articles = { expression = "cron(5 * * * ? *)", description = "Articles + figures, hourly at :05 UTC" }
    patents  = { expression = "cron(0 5 * * ? *)", description = "WO patents from EPO, daily 05:00 UTC" }
    cleanup  = { expression = "cron(30 5 * * ? *)", description = "Delete articles > 30 days, patents > 90 days, daily 05:30 UTC" }
  }
}

resource "aws_scheduler_schedule" "jobs" {
  for_each                     = local.schedules
  name                         = each.key
  group_name                   = aws_scheduler_schedule_group.jobs.name
  description                  = each.value.description
  schedule_expression          = each.value.expression
  schedule_expression_timezone = "UTC"
  state                        = var.schedules_enabled ? "ENABLED" : "DISABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_ecs_cluster.jobs.arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({ containerOverrides = [{ name = "jobs", command = [each.key] }] })

    ecs_parameters {
      task_definition_arn = aws_ecs_task_definition.jobs.arn_without_revision
      launch_type         = "FARGATE"
      platform_version    = "LATEST"
      task_count          = 1
      network_configuration {
        subnets          = local.subnet_ids
        security_groups  = [aws_security_group.jobs.id]
        assign_public_ip = true
      }
    }

    retry_policy {
      maximum_retry_attempts       = 1
      maximum_event_age_in_seconds = 3600
    }
  }
}
