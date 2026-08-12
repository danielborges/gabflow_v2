output "ecr_repository_urls" { value = { for name, repository in aws_ecr_repository.this : name => repository.repository_url } }
output "ecs_cluster_name" { value = aws_ecs_cluster.this.name }
output "app_task_definition_arn" { value = aws_ecs_task_definition.app.arn }
output "worker_task_definition_arn" { value = aws_ecs_task_definition.worker.arn }
output "migration_task_definition_arn" { value = aws_ecs_task_definition.migration.arn }
output "database_bootstrap_task_definition_arn" { value = aws_ecs_task_definition.database_bootstrap.arn }
output "task_security_group_id" { value = aws_security_group.tasks.id }
output "private_subnet_ids" { value = var.private_subnet_ids }
output "load_balancer_dns_name" { value = aws_lb.this.dns_name }
output "database_endpoint" { value = aws_db_instance.this.endpoint }
output "database_master_secret_arn" {
  value     = try(aws_db_instance.this.master_user_secret[0].secret_arn, null)
  sensitive = true
}
output "application_url" { value = local.certificate_arn == null ? "http://${aws_lb.this.dns_name}" : "https://${aws_lb.this.dns_name}" }
output "dashboard_name" { value = aws_cloudwatch_dashboard.this.dashboard_name }
