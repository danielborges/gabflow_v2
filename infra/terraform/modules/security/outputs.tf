output "kms_key_arn" {
  value = aws_kms_key.application.arn
}

output "kms_alias" {
  value = aws_kms_alias.application.name
}

output "application_secret_arn" {
  value = aws_secretsmanager_secret.application.arn
}

output "whatsapp_secret_prefix" {
  value = local.whatsapp_secret_prefix
}

output "whatsapp_runtime_configuration" {
  value = {
    backend       = "aws-secrets-manager"
    backend_ready = true
    region        = data.aws_region.current.region
    secret_prefix = local.whatsapp_secret_prefix
    kms_key_id    = aws_kms_key.application.arn
    recovery_days = var.secret_recovery_window_days
  }
}

output "ecs_execution_role_arn" {
  value = aws_iam_role.ecs_execution.arn
}

output "ecs_execution_role_name" {
  value = aws_iam_role.ecs_execution.name
}

output "api_task_role_arn" {
  value = aws_iam_role.api_task.arn
}

output "api_task_role_name" {
  value = aws_iam_role.api_task.name
}

output "worker_task_role_arn" {
  value = aws_iam_role.worker_task.arn
}

output "worker_task_role_name" {
  value = aws_iam_role.worker_task.name
}

output "migration_task_role_arn" {
  value = aws_iam_role.migration_task.arn
}

output "migration_task_role_name" {
  value = aws_iam_role.migration_task.name
}
