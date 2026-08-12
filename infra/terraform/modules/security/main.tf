data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
data "aws_region" "current" {}

locals {
  application_secret_name = "gabflow/${var.environment}/application/config"
  whatsapp_secret_prefix  = "gabflow/${var.environment}/whatsapp"
  whatsapp_secret_arn     = "arn:${data.aws_partition.current.partition}:secretsmanager:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:secret:${local.whatsapp_secret_prefix}/*"
}

resource "aws_kms_key" "application" {
  description             = "GabFlow ${var.environment} application data and secrets"
  deletion_window_in_days = var.kms_deletion_window_days
  enable_key_rotation     = true
}

resource "aws_kms_alias" "application" {
  name          = "alias/${var.name_prefix}-application"
  target_key_id = aws_kms_key.application.key_id
}

resource "aws_secretsmanager_secret" "application" {
  name                    = local.application_secret_name
  description             = "Metadados de configuracao do GabFlow ${var.environment}; valor gerenciado fora do Terraform"
  kms_key_id              = aws_kms_key.application.arn
  recovery_window_in_days = var.secret_recovery_window_days

  tags = {
    purpose = "application-config"
  }
}

data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ecs_execution" {
  name               = "${var.name_prefix}-ecs-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role_policy_attachment" "ecs_execution" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "api_task" {
  name               = "${var.name_prefix}-api-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role" "worker_task" {
  name               = "${var.name_prefix}-worker-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role" "migration_task" {
  name               = "${var.name_prefix}-migration-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

data "aws_iam_policy_document" "api_secrets" {
  statement {
    sid       = "CreateWhatsappIntegrationSecrets"
    actions   = ["secretsmanager:CreateSecret"]
    resources = [local.whatsapp_secret_arn]

    condition {
      test     = "StringEquals"
      variable = "aws:RequestTag/application"
      values   = ["gabflow"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:RequestTag/environment"
      values   = [var.environment]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:RequestTag/purpose"
      values   = ["whatsapp-integration"]
    }

    condition {
      test     = "StringEquals"
      variable = "secretsmanager:KmsKeyArn"
      values   = [aws_kms_key.application.arn]
    }
  }

  statement {
    sid       = "ScheduleWhatsappIntegrationSecretDeletion"
    actions   = ["secretsmanager:DeleteSecret"]
    resources = [local.whatsapp_secret_arn]

    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/application"
      values   = ["gabflow"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/environment"
      values   = [var.environment]
    }

    condition {
      test     = "NumericGreaterThanEquals"
      variable = "secretsmanager:RecoveryWindowInDays"
      values   = ["7"]
    }
  }

  statement {
    sid       = "DenyImmediateWhatsappSecretDeletion"
    effect    = "Deny"
    actions   = ["secretsmanager:DeleteSecret"]
    resources = [local.whatsapp_secret_arn]

    condition {
      test     = "Bool"
      variable = "secretsmanager:ForceDeleteWithoutRecovery"
      values   = ["true"]
    }
  }

  statement {
    sid = "ReadApplicationConfig"
    actions = [
      "secretsmanager:DescribeSecret",
      "secretsmanager:GetSecretValue",
    ]
    resources = [aws_secretsmanager_secret.application.arn]
  }

  statement {
    sid = "UseApplicationKey"
    actions = [
      "kms:Decrypt",
      "kms:DescribeKey",
      "kms:Encrypt",
      "kms:GenerateDataKey",
    ]
    resources = [aws_kms_key.application.arn]
  }
}

resource "aws_iam_role_policy" "api_secrets" {
  name   = "${var.name_prefix}-api-secrets"
  role   = aws_iam_role.api_task.id
  policy = data.aws_iam_policy_document.api_secrets.json
}

data "aws_iam_policy_document" "worker_secrets" {
  statement {
    sid = "ReadRuntimeSecrets"
    actions = [
      "secretsmanager:DescribeSecret",
      "secretsmanager:GetSecretValue",
    ]
    resources = [
      aws_secretsmanager_secret.application.arn,
      local.whatsapp_secret_arn,
    ]
  }

  statement {
    sid = "DecryptRuntimeSecrets"
    actions = [
      "kms:Decrypt",
      "kms:DescribeKey",
    ]
    resources = [aws_kms_key.application.arn]
  }
}

resource "aws_iam_role_policy" "worker_secrets" {
  name   = "${var.name_prefix}-worker-secrets"
  role   = aws_iam_role.worker_task.id
  policy = data.aws_iam_policy_document.worker_secrets.json
}
