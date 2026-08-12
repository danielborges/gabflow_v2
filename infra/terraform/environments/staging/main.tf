data "aws_caller_identity" "current" {}

locals {
  environment              = "staging"
  name_prefix              = "gabflow-${local.environment}"
  external_certificate_arn = try(trimspace(var.certificate_arn), "") == "" ? null : trimspace(var.certificate_arn)
  listener_certificate_arn = local.external_certificate_arn != null ? local.external_certificate_arn : (
    var.enable_https ? aws_acm_certificate_validation.staging[0].certificate_arn : null
  )
}

resource "aws_acm_certificate" "staging" {
  count = local.external_certificate_arn == null ? 1 : 0

  domain_name       = var.domain_name
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_acm_certificate_validation" "staging" {
  count = local.external_certificate_arn == null && var.enable_https ? 1 : 0

  certificate_arn         = aws_acm_certificate.staging[0].arn
  validation_record_fqdns = [for option in aws_acm_certificate.staging[0].domain_validation_options : option.resource_record_name]
}

module "network" {
  source = "../../modules/network"

  name_prefix             = local.name_prefix
  vpc_cidr                = var.vpc_cidr
  availability_zone_count = 2
  single_nat_gateway      = true
  flow_log_retention_days = 30
}

module "security" {
  source = "../../modules/security"

  name_prefix                 = local.name_prefix
  environment                 = local.environment
  kms_deletion_window_days    = 30
  secret_recovery_window_days = 30
}

module "messaging" {
  source = "../../modules/messaging"

  name_prefix                = local.name_prefix
  environment                = local.environment
  aws_region                 = var.aws_region
  kms_key_arn                = module.security.kms_key_arn
  api_task_role_name         = module.security.api_task_role_name
  worker_task_role_name      = module.security.worker_task_role_name
  max_receive_count          = 5
  visibility_timeout_seconds = 120
}

module "runtime" {
  source = "../../modules/runtime"

  name_prefix              = local.name_prefix
  environment              = local.environment
  aws_region               = var.aws_region
  vpc_id                   = module.network.vpc_id
  public_subnet_ids        = module.network.public_subnet_ids
  private_subnet_ids       = module.network.private_subnet_ids
  kms_key_arn              = module.security.kms_key_arn
  application_secret_arn   = module.security.application_secret_arn
  ecs_execution_role_arn   = module.security.ecs_execution_role_arn
  ecs_execution_role_name  = module.security.ecs_execution_role_name
  api_task_role_arn        = module.security.api_task_role_arn
  api_task_role_name       = module.security.api_task_role_name
  worker_task_role_arn     = module.security.worker_task_role_arn
  worker_task_role_name    = module.security.worker_task_role_name
  migration_task_role_arn  = module.security.migration_task_role_arn
  migration_task_role_name = module.security.migration_task_role_name
  whatsapp_queue_url       = module.messaging.whatsapp_inbound_queue_url
  whatsapp_secret_prefix   = module.security.whatsapp_secret_prefix
  image_tag                = var.image_tag
  enable_services          = var.enable_services
  certificate_arn          = local.listener_certificate_arn
  db_instance_class        = var.db_instance_class
}
