data "aws_caller_identity" "current" {}

locals {
  environment = "production"
  name_prefix = "gabflow-${local.environment}"
}

module "network" {
  source = "../../modules/network"

  name_prefix             = local.name_prefix
  vpc_cidr                = var.vpc_cidr
  availability_zone_count = 2
  single_nat_gateway      = false
  flow_log_retention_days = 90
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
