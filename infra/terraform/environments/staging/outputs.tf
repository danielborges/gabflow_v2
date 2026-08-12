output "account_id" {
  value = data.aws_caller_identity.current.account_id
}

output "vpc_id" {
  value = module.network.vpc_id
}

output "public_subnet_ids" {
  value = module.network.public_subnet_ids
}

output "private_subnet_ids" {
  value = module.network.private_subnet_ids
}

output "application_kms_key_arn" {
  value = module.security.kms_key_arn
}

output "application_secret_arn" {
  value = module.security.application_secret_arn
}

output "whatsapp_secret_prefix" {
  value = module.security.whatsapp_secret_prefix
}

output "whatsapp_runtime_configuration" {
  value = merge(module.security.whatsapp_runtime_configuration, {
    inbound_queue_backend = "aws-sqs"
    inbound_queue_url     = module.messaging.whatsapp_inbound_queue_url
  })
}

output "whatsapp_inbound_queue_arn" {
  value = module.messaging.whatsapp_inbound_queue_arn
}

output "whatsapp_inbound_dlq_arn" {
  value = module.messaging.whatsapp_dlq_arn
}

output "whatsapp_operations_dashboard_name" {
  value = module.messaging.whatsapp_operations_dashboard_name
}

output "ecs_roles" {
  value = {
    execution = module.security.ecs_execution_role_arn
    api       = module.security.api_task_role_arn
    worker    = module.security.worker_task_role_arn
    migration = module.security.migration_task_role_arn
  }
}

output "ecr_repository_urls" {
  value = module.runtime.ecr_repository_urls
}

output "ecs_cluster_name" {
  value = module.runtime.ecs_cluster_name
}

output "migration_task_definition_arn" {
  value = module.runtime.migration_task_definition_arn
}

output "database_bootstrap_task_definition_arn" {
  value = module.runtime.database_bootstrap_task_definition_arn
}

output "task_security_group_id" {
  value = module.runtime.task_security_group_id
}

output "runtime_private_subnet_ids" {
  value = module.runtime.private_subnet_ids
}

output "staging_url" {
  value = var.enable_https ? "https://${var.domain_name}" : module.runtime.application_url
}

output "load_balancer_dns_name" {
  value = module.runtime.load_balancer_dns_name
}

output "managed_certificate_arn" {
  value = local.external_certificate_arn == null ? aws_acm_certificate.staging[0].arn : local.external_certificate_arn
}

output "certificate_dns_validation_records" {
  value = local.external_certificate_arn == null ? [
    for option in aws_acm_certificate.staging[0].domain_validation_options : {
      name  = option.resource_record_name
      type  = option.resource_record_type
      value = option.resource_record_value
    }
  ] : []
}

output "database_endpoint" {
  value = module.runtime.database_endpoint
}

output "database_master_secret_arn" {
  value     = module.runtime.database_master_secret_arn
  sensitive = true
}

output "runtime_dashboard_name" {
  value = module.runtime.dashboard_name
}
