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
