# Non-secret values for deploy commands (no passwords or keys are ever outputs).

output "site_url" {
  value = "https://${var.domain_name != "" ? var.domain_name : aws_cloudfront_distribution.site.domain_name}"
}

output "cloudfront_distribution_id" {
  value = aws_cloudfront_distribution.site.id
}

output "site_bucket" {
  value = aws_s3_bucket.site.bucket
}

output "artifacts_bucket" {
  value = aws_s3_bucket.artifacts.bucket
}

output "ecr_repository_url" {
  value = aws_ecr_repository.jobs.repository_url
}

output "ecs_cluster" {
  value = aws_ecs_cluster.jobs.name
}

output "jobs_task_definition" {
  value = aws_ecs_task_definition.jobs.family
}

output "admin_task_definition" {
  value = aws_ecs_task_definition.admin.family
}

output "task_subnet_ids" {
  value = local.subnet_ids
}

output "jobs_security_group_id" {
  value = aws_security_group.jobs.id
}

output "api_function_name" {
  value = aws_lambda_function.api.function_name
}

output "db_endpoint" {
  value = aws_db_instance.db.address
}

output "db_master_secret_arn" {
  description = "ARN only - the password itself stays in Secrets Manager"
  value       = local.master_secret_arn
}
