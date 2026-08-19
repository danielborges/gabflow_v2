data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

locals {
  certificate_arn = try(trimspace(var.certificate_arn), "") == "" ? null : trimspace(var.certificate_arn)
  repositories    = toset(["backend", "web"])
  backend_image   = "${aws_ecr_repository.this["backend"].repository_url}:${var.image_tag}"
  web_image       = "${aws_ecr_repository.this["web"].repository_url}:${var.image_tag}"
  secret_key = {
    api_database       = "${var.application_secret_arn}:database_url_api::"
    worker_database    = "${var.application_secret_arn}:database_url_worker::"
    migration_database = "${var.application_secret_arn}:database_url_migration::"
    backup_database    = "${var.application_secret_arn}:database_url_backup::"
    secret_key         = "${var.application_secret_arn}:secret_key::"
    jwt_secret_key     = "${var.application_secret_arn}:jwt_secret_key::"
    storage_key        = "${var.application_secret_arn}:storage_encryption_master_key::"
    metrics_token      = "${var.application_secret_arn}:metrics_bearer_token::"
  }
  common_environment = [
    { name = "APP_ENV", value = var.environment },
    { name = "APP_RELEASE", value = var.image_tag },
    { name = "AWS_REGION", value = var.aws_region },
    { name = "RAG_EMBEDDING_PROVIDER", value = var.rag_embedding_provider },
    { name = "AI_EMBEDDING_MODEL", value = var.ollama_embedding_model },
    { name = "RAG_PROMPT_INJECTION_CLASSIFIER_PROVIDER", value = var.rag_prompt_injection_classifier_provider },
    { name = "RAG_PROMPT_INJECTION_CLASSIFIER_MODEL", value = var.rag_prompt_injection_classifier_model },
    { name = "DB_ENFORCE_RUNTIME_ROLE", value = "true" },
    { name = "ATTACHMENT_STORAGE_PATH", value = "/app/data/attachments" },
    { name = "RAG_STORAGE_PATH", value = "/app/data/rag" },
    { name = "ELECTORAL_STORAGE_PATH", value = "/app/data/electoral" },
    { name = "DOCUMENT_PARSER_SOCKET_PATH", value = "/run/gabflow-parser/parser.sock" },
    { name = "MALWARE_SCANNER_ENABLED", value = "true" },
    { name = "MALWARE_SCANNER_REQUIRED", value = "true" },
    { name = "MALWARE_SCANNER_HOST", value = "127.0.0.1" },
    { name = "WHATSAPP_PLATFORM_ENABLED", value = "false" },
    { name = "WHATSAPP_EMBEDDED_SIGNUP_ENABLED", value = "false" },
    { name = "WHATSAPP_ROLLOUT_STAGE", value = "disabled" },
    { name = "WHATSAPP_SECRET_BACKEND", value = "aws-secrets-manager" },
    { name = "WHATSAPP_SECRET_BACKEND_READY", value = "true" },
    { name = "WHATSAPP_AWS_SECRET_PREFIX", value = var.whatsapp_secret_prefix },
    { name = "WHATSAPP_AWS_KMS_KEY_ID", value = var.kms_key_arn },
    { name = "WHATSAPP_INBOUND_QUEUE_BACKEND", value = "aws-sqs" },
    { name = "WHATSAPP_AWS_SQS_QUEUE_URL", value = var.whatsapp_queue_url },
    { name = "AI_TRIAGE_FALLBACK_ENABLED", value = "true" },
    { name = "AI_ASSISTANCE_FALLBACK_ENABLED", value = "true" },
    { name = "AI_LEGISLATIVE_FALLBACK_ENABLED", value = "true" },
    { name = "ELECTORAL_AI_FALLBACK_ENABLED", value = "true" },
    { name = "ELECTORAL_WEB_RESEARCH_ENABLED", value = "false" },
    { name = "OLLAMA_BASE_URL", value = "http://127.0.0.1:9" },
    { name = "LOG_FORMAT", value = "json" },
  ]
  app_environment = concat(
    [for item in local.common_environment : item if item.name != "OLLAMA_BASE_URL"],
    [
      { name = "OLLAMA_BASE_URL", value = var.enable_ollama_sidecar ? "http://127.0.0.1:11434" : "http://127.0.0.1:9" },
      { name = "ELECTORAL_AI_ENABLED", value = tostring(var.enable_ollama_sidecar) },
      { name = "ELECTORAL_AI_PROVIDER", value = "ollama" },
      { name = "ELECTORAL_AI_MODEL", value = var.ollama_model },
      { name = "ELECTORAL_AI_PROMPT_VERSION", value = "electoral-strategic-advisor-v2" },
      { name = "ELECTORAL_AI_MAX_TOKENS", value = "1536" },
      { name = "ELECTORAL_AI_MAX_EVIDENCE_CHARS", value = "16000" },
      { name = "RAG_STRUCTURED_INTERPRETATION_ENABLED", value = tostring(var.enable_ollama_sidecar) },
      { name = "RAG_STRUCTURED_INTERPRETATION_PROVIDER", value = "ollama" },
      { name = "RAG_STRUCTURED_INTERPRETATION_MODEL", value = var.ollama_model },
      { name = "RAG_STRUCTURED_INTERPRETATION_TIMEOUT_SECONDS", value = "45" },
      { name = "RAG_STRUCTURED_INTERPRETATION_MAX_TOKENS", value = "128" },
      { name = "RAG_ANSWER_MODEL", value = var.ollama_model },
      { name = "RAG_ANSWER_TIMEOUT_SECONDS", value = "60" },
      { name = "RAG_ANSWER_MAX_TOKENS", value = "128" },
      { name = "RAG_ANSWER_MAX_CLAIMS", value = "3" },
      { name = "RAG_ANSWER_SOURCE_CHARS", value = "500" },
      { name = "RAG_NEURAL_RERANK_ENABLED", value = "false" },
      { name = "RAG_ENTAILMENT_ENABLED", value = "false" },
      { name = "RAG_NLI_ENABLED", value = "false" },
      { name = "RAG_QUERY_LATENCY_BUDGET_MS", value = "120000" },
    ],
  )
  runtime_secrets = [
    { name = "SECRET_KEY", valueFrom = local.secret_key.secret_key },
    { name = "JWT_SECRET_KEY", valueFrom = local.secret_key.jwt_secret_key },
    { name = "STORAGE_ENCRYPTION_MASTER_KEY", valueFrom = local.secret_key.storage_key },
  ]
  efs_volumes = [
    for name, access_point in aws_efs_access_point.this : {
      name = name
      efsVolumeConfiguration = {
        fileSystemId        = aws_efs_file_system.this.id
        transitEncryption   = "ENABLED"
        authorizationConfig = { accessPointId = access_point.id, iam = "ENABLED" }
      }
    }
  ]
  data_mounts = [
    { sourceVolume = "attachments", containerPath = "/app/data/attachments", readOnly = false },
    { sourceVolume = "rag", containerPath = "/app/data/rag", readOnly = false },
    { sourceVolume = "electoral", containerPath = "/app/data/electoral", readOnly = false },
  ]
  parser_mounts = concat(local.data_mounts, [{ sourceVolume = "parser-socket", containerPath = "/run/gabflow-parser", readOnly = false }])
  log_options = {
    awslogs-region        = var.aws_region
    awslogs-stream-prefix = "ecs"
  }
  ollama_container = {
    name       = "ollama"
    image      = var.ollama_image
    essential  = false
    entryPoint = ["/bin/sh", "-ec"]
    command = [
      "ollama serve & server_pid=$!; until ollama list >/dev/null 2>&1; do sleep 2; done; until ollama pull '${var.ollama_model}'; do sleep 30; done; until ollama pull '${var.ollama_embedding_model}'; do sleep 30; done; wait $server_pid"
    ]
    cpu    = 768
    memory = 1536
    environment = [
      { name = "OLLAMA_HOST", value = "127.0.0.1:11434" },
      { name = "OLLAMA_MODELS", value = "/root/.ollama/models" },
      { name = "OLLAMA_CONTEXT_LENGTH", value = "8192" },
      { name = "OLLAMA_NUM_PARALLEL", value = "1" },
      { name = "OLLAMA_MAX_LOADED_MODELS", value = "1" },
      { name = "OLLAMA_KEEP_ALIVE", value = "5m" },
      { name = "OLLAMA_FLASH_ATTENTION", value = "true" },
      { name = "OLLAMA_KV_CACHE_TYPE", value = "q8_0" },
      { name = "OLLAMA_NOHISTORY", value = "true" },
    ]
    mountPoints = [
      { sourceVolume = "ollama-data", containerPath = "/root/.ollama", readOnly = false },
    ]
    healthCheck = {
      command     = ["CMD-SHELL", "ollama show '${var.ollama_model}' >/dev/null 2>&1 && ollama show '${var.ollama_embedding_model}' >/dev/null 2>&1 || exit 1"]
      interval    = 30
      timeout     = 10
      retries     = 5
      startPeriod = 300
    }
    stopTimeout = 120
    restartPolicy = {
      enabled              = true
      ignoredExitCodes     = []
      restartAttemptPeriod = 60
    }
    logConfiguration = {
      logDriver = "awslogs"
      options   = merge(local.log_options, { awslogs-group = aws_cloudwatch_log_group.this["app"].name })
    }
    readonlyRootFilesystem = false
    linuxParameters        = { initProcessEnabled = true }
  }
  local_ai_worker_container = {
    name       = "local-ai-worker"
    image      = local.backend_image
    essential  = true
    entryPoint = ["/app/worker-entrypoint.sh"]
    cpu        = 512
    memory     = 512
    dependsOn = [
      { containerName = "ollama", condition = "HEALTHY" },
    ]
    environment = concat(local.app_environment, [
      { name = "WORKER_QUEUE", value = "local-ai" },
      { name = "WORKER_RUN_SCHEDULER", value = "false" },
    ])
    secrets = concat(local.runtime_secrets, [
      { name = "DATABASE_URL", valueFrom = local.secret_key.worker_database },
    ])
    mountPoints = local.data_mounts
    stopTimeout = 120
    logConfiguration = {
      logDriver = "awslogs"
      options   = merge(local.log_options, { awslogs-group = aws_cloudwatch_log_group.this["app"].name })
    }
    linuxParameters = { initProcessEnabled = true }
  }
}

resource "aws_ecr_repository" "this" {
  for_each             = local.repositories
  name                 = "${var.name_prefix}/${each.key}"
  image_tag_mutability = "IMMUTABLE"
  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = var.kms_key_arn
  }
  image_scanning_configuration { scan_on_push = true }
}

resource "aws_ecr_lifecycle_policy" "this" {
  for_each   = aws_ecr_repository.this
  repository = each.value.name
  policy = jsonencode({ rules = [
    { rulePriority = 1, description = "Expire untagged images", selection = { tagStatus = "untagged", countType = "sinceImagePushed", countUnit = "days", countNumber = 7 }, action = { type = "expire" } },
    { rulePriority = 2, description = "Keep the latest 30 immutable releases", selection = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 30 }, action = { type = "expire" } },
  ] })
}

resource "aws_security_group" "alb" {
  name        = "${var.name_prefix}-alb"
  description = "Public ingress to the GabFlow staging load balancer"
  vpc_id      = var.vpc_id
  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "tasks" {
  name        = "${var.name_prefix}-ecs-tasks"
  description = "Ingress from ALB and controlled task egress"
  vpc_id      = var.vpc_id
  ingress {
    description     = "Web from ALB"
    from_port       = 80
    to_port         = 80
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "database" {
  name        = "${var.name_prefix}-database"
  description = "PostgreSQL only from GabFlow tasks"
  vpc_id      = var.vpc_id
  ingress {
    description     = "PostgreSQL from ECS"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.tasks.id]
  }
}

resource "aws_security_group" "efs" {
  name        = "${var.name_prefix}-efs"
  description = "NFS only from GabFlow tasks"
  vpc_id      = var.vpc_id
  ingress {
    description     = "NFS from ECS"
    from_port       = 2049
    to_port         = 2049
    protocol        = "tcp"
    security_groups = [aws_security_group.tasks.id]
  }
}

resource "aws_db_subnet_group" "this" {
  name       = var.name_prefix
  subnet_ids = var.private_subnet_ids
}
resource "aws_db_parameter_group" "this" {
  name   = "${var.name_prefix}-postgres17"
  family = "postgres17"
  parameter {
    name         = "rds.force_ssl"
    value        = "1"
    apply_method = "pending-reboot"
  }
}
resource "aws_db_instance" "this" {
  identifier                    = "${var.name_prefix}-postgres"
  engine                        = "postgres"
  engine_version                = "17"
  instance_class                = var.db_instance_class
  allocated_storage             = var.db_allocated_storage
  max_allocated_storage         = 100
  storage_type                  = "gp3"
  storage_encrypted             = true
  kms_key_id                    = var.kms_key_arn
  db_name                       = "gabflow"
  username                      = "gabflow_admin"
  manage_master_user_password   = true
  master_user_secret_kms_key_id = var.kms_key_arn
  db_subnet_group_name          = aws_db_subnet_group.this.name
  parameter_group_name          = aws_db_parameter_group.this.name
  vpc_security_group_ids        = [aws_security_group.database.id]
  publicly_accessible           = false
  multi_az                      = false
  backup_retention_period       = 7
  backup_window                 = "03:00-04:00"
  maintenance_window            = "sun:04:00-sun:05:00"
  performance_insights_enabled  = true
  deletion_protection           = true
  skip_final_snapshot           = true
  auto_minor_version_upgrade    = true
  copy_tags_to_snapshot         = true
}

resource "aws_efs_file_system" "this" {
  encrypted        = true
  kms_key_id       = var.kms_key_arn
  performance_mode = "generalPurpose"
  throughput_mode  = "elastic"
  lifecycle_policy { transition_to_ia = "AFTER_30_DAYS" }
  tags = { Name = "${var.name_prefix}-shared-data" }
}
resource "aws_efs_backup_policy" "this" {
  file_system_id = aws_efs_file_system.this.id
  backup_policy { status = "ENABLED" }
}
resource "aws_efs_mount_target" "this" {
  for_each        = { for index, subnet_id in var.private_subnet_ids : tostring(index) => subnet_id }
  file_system_id  = aws_efs_file_system.this.id
  subnet_id       = each.value
  security_groups = [aws_security_group.efs.id]
}
resource "aws_efs_access_point" "this" {
  for_each       = toset(["attachments", "rag", "electoral"])
  file_system_id = aws_efs_file_system.this.id
  posix_user {
    uid = 999
    gid = 999
  }
  root_directory {
    path = "/${each.key}"
    creation_info {
      owner_uid   = 999
      owner_gid   = 999
      permissions = "0750"
    }
  }
}

resource "aws_iam_role_policy" "execution_secrets" {
  name = "${var.name_prefix}-execution-runtime-config"
  role = var.ecs_execution_role_name
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = [var.application_secret_arn] },
    { Effect = "Allow", Action = ["kms:Decrypt"], Resource = [var.kms_key_arn] },
  ] })
}
resource "aws_iam_role_policy" "efs" {
  for_each = { api = var.api_task_role_name, worker = var.worker_task_role_name }
  name     = "${var.name_prefix}-${each.key}-efs"
  role     = each.value
  policy   = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = ["elasticfilesystem:ClientMount", "elasticfilesystem:ClientWrite"], Resource = [aws_efs_file_system.this.arn] }] })
}

resource "aws_ecs_cluster" "this" {
  name = var.name_prefix
  setting {
    name  = "containerInsights"
    value = "enhanced"
  }
}
resource "aws_cloudwatch_log_group" "this" {
  for_each          = toset(["app", "worker", "migration"])
  name              = "/ecs/${var.name_prefix}/${each.key}"
  retention_in_days = var.log_retention_days
}

resource "aws_lb" "this" {
  name                       = substr("${var.name_prefix}-alb", 0, 32)
  internal                   = false
  load_balancer_type         = "application"
  security_groups            = [aws_security_group.alb.id]
  subnets                    = var.public_subnet_ids
  drop_invalid_header_fields = true
  enable_deletion_protection = true
}
resource "aws_lb_target_group" "app" {
  name                 = substr("${var.name_prefix}-app", 0, 32)
  port                 = 80
  protocol             = "HTTP"
  target_type          = "ip"
  vpc_id               = var.vpc_id
  deregistration_delay = 30
  health_check {
    enabled             = true
    path                = "/api/v1/ready"
    matcher             = "200"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"
  dynamic "default_action" {
    for_each = local.certificate_arn == null ? [1] : []
    content {
      type             = "forward"
      target_group_arn = aws_lb_target_group.app.arn
    }
  }
  dynamic "default_action" {
    for_each = local.certificate_arn == null ? [] : [1]
    content {
      type = "redirect"
      redirect {
        port        = "443"
        protocol    = "HTTPS"
        status_code = "HTTP_301"
      }
    }
  }
}
resource "aws_lb_listener" "https" {
  count             = local.certificate_arn == null ? 0 : 1
  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = local.certificate_arn
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
}

resource "aws_ecs_task_definition" "app" {
  family                   = "${var.name_prefix}-app"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 4096
  memory                   = 8192
  execution_role_arn       = var.ecs_execution_role_arn
  task_role_arn            = var.api_task_role_arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }
  ephemeral_storage { size_in_gib = 40 }
  volume { name = "parser-socket" }
  dynamic "volume" {
    for_each = var.enable_ollama_sidecar ? [1] : []
    content { name = "ollama-data" }
  }
  dynamic "volume" {
    for_each = { for item in local.efs_volumes : item.name => item }
    content {
      name = volume.value.name
      efs_volume_configuration {
        file_system_id     = volume.value.efsVolumeConfiguration.fileSystemId
        transit_encryption = "ENABLED"
        authorization_config {
          access_point_id = volume.value.efsVolumeConfiguration.authorizationConfig.accessPointId
          iam             = "ENABLED"
        }
      }
    }
  }
  container_definitions = jsonencode(concat([
    { name = "parser", image = local.backend_image, essential = true, entryPoint = ["/app/parser-entrypoint.sh"], cpu = 512, memory = 1024, environment = [{ name = "PARSER_ALLOWED_ROOTS", value = "/app/data/attachments:/app/data/rag" }, { name = "DOCUMENT_PARSER_SOCKET_PATH", value = "/run/gabflow-parser/parser.sock" }], mountPoints = local.parser_mounts, healthCheck = { command = ["CMD-SHELL", "test -S /run/gabflow-parser/parser.sock"], interval = 10, timeout = 5, retries = 5, startPeriod = 30 }, logConfiguration = { logDriver = "awslogs", options = merge(local.log_options, { awslogs-group = aws_cloudwatch_log_group.this["app"].name }) }, readonlyRootFilesystem = false, linuxParameters = { initProcessEnabled = true } },
    { name = "clamav", image = "clamav/clamav:1.4", essential = true, cpu = 1024, memory = 2048, healthCheck = { command = ["CMD-SHELL", "clamdscan --ping 1 || exit 1"], interval = 30, timeout = 10, retries = 5, startPeriod = 120 }, logConfiguration = { logDriver = "awslogs", options = merge(local.log_options, { awslogs-group = aws_cloudwatch_log_group.this["app"].name }) } },
    { name = "api", image = local.backend_image, essential = true, cpu = var.enable_ollama_sidecar ? 1024 : 1536, memory = var.enable_ollama_sidecar ? 2560 : 3584, portMappings = [{ containerPort = 5000, protocol = "tcp" }], dependsOn = [{ containerName = "parser", condition = "HEALTHY" }, { containerName = "clamav", condition = "HEALTHY" }], environment = concat(local.app_environment, [{ name = "COOKIE_SECURE", value = tostring(local.certificate_arn != null) }, { name = "RUN_MIGRATIONS_ON_START", value = "false" }, { name = "RUN_SEEDS_ON_START", value = "false" }]), secrets = concat(local.runtime_secrets, [{ name = "DATABASE_URL", valueFrom = local.secret_key.api_database }, { name = "METRICS_BEARER_TOKEN", valueFrom = local.secret_key.metrics_token }]), mountPoints = concat(local.data_mounts, [{ sourceVolume = "parser-socket", containerPath = "/run/gabflow-parser", readOnly = false }]), healthCheck = { command = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/api/v1/ready')\""], interval = 15, timeout = 5, retries = 5, startPeriod = 60 }, stopTimeout = 60, logConfiguration = { logDriver = "awslogs", options = merge(local.log_options, { awslogs-group = aws_cloudwatch_log_group.this["app"].name }) }, readonlyRootFilesystem = false, linuxParameters = { initProcessEnabled = true } },
    { name = "web", image = local.web_image, essential = true, cpu = 256, memory = 512, portMappings = [{ containerPort = 80, protocol = "tcp" }], dependsOn = [{ containerName = "api", condition = "HEALTHY" }], healthCheck = { command = ["CMD-SHELL", "wget -q --spider http://127.0.0.1/api/v1/ready"], interval = 15, timeout = 5, retries = 5, startPeriod = 30 }, logConfiguration = { logDriver = "awslogs", options = merge(local.log_options, { awslogs-group = aws_cloudwatch_log_group.this["app"].name }) }, readonlyRootFilesystem = false },
  ], [
    for container in [local.ollama_container, local.local_ai_worker_container] : container
    if var.enable_ollama_sidecar
  ]))
}

resource "aws_ecs_task_definition" "worker" {
  family                   = "${var.name_prefix}-worker"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 4096
  memory                   = 8192
  execution_role_arn       = var.ecs_execution_role_arn
  task_role_arn            = var.worker_task_role_arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }
  ephemeral_storage { size_in_gib = 60 }
  volume { name = "parser-socket" }
  dynamic "volume" {
    for_each = { for item in local.efs_volumes : item.name => item }
    content {
      name = volume.value.name
      efs_volume_configuration {
        file_system_id     = volume.value.efsVolumeConfiguration.fileSystemId
        transit_encryption = "ENABLED"
        authorization_config {
          access_point_id = volume.value.efsVolumeConfiguration.authorizationConfig.accessPointId
          iam             = "ENABLED"
        }
      }
    }
  }
  container_definitions = jsonencode([
    { name = "parser", image = local.backend_image, essential = true, entryPoint = ["/app/parser-entrypoint.sh"], cpu = 512, memory = 1024, environment = [{ name = "PARSER_ALLOWED_ROOTS", value = "/app/data/attachments:/app/data/rag" }, { name = "DOCUMENT_PARSER_SOCKET_PATH", value = "/run/gabflow-parser/parser.sock" }], mountPoints = local.parser_mounts, healthCheck = { command = ["CMD-SHELL", "test -S /run/gabflow-parser/parser.sock"], interval = 10, timeout = 5, retries = 5, startPeriod = 30 }, logConfiguration = { logDriver = "awslogs", options = merge(local.log_options, { awslogs-group = aws_cloudwatch_log_group.this["worker"].name }) } },
    { name = "clamav", image = "clamav/clamav:1.4", essential = true, cpu = 1024, memory = 2048, healthCheck = { command = ["CMD-SHELL", "clamdscan --ping 1 || exit 1"], interval = 30, timeout = 10, retries = 5, startPeriod = 120 }, logConfiguration = { logDriver = "awslogs", options = merge(local.log_options, { awslogs-group = aws_cloudwatch_log_group.this["worker"].name }) } },
    { name = "worker", image = local.backend_image, essential = true, entryPoint = ["/app/worker-entrypoint.sh"], cpu = 1280, memory = 2304, dependsOn = [{ containerName = "parser", condition = "HEALTHY" }, { containerName = "clamav", condition = "HEALTHY" }], environment = concat(local.common_environment, [{ name = "WORKER_QUEUE", value = "default" }]), secrets = concat(local.runtime_secrets, [{ name = "DATABASE_URL", valueFrom = local.secret_key.worker_database }]), mountPoints = concat(local.data_mounts, [{ sourceVolume = "parser-socket", containerPath = "/run/gabflow-parser", readOnly = false }]), stopTimeout = 120, logConfiguration = { logDriver = "awslogs", options = merge(local.log_options, { awslogs-group = aws_cloudwatch_log_group.this["worker"].name }) }, linuxParameters = { initProcessEnabled = true } },
    { name = "worker-rag", image = local.backend_image, essential = true, entryPoint = ["/app/worker-entrypoint.sh"], cpu = 1280, memory = 2304, dependsOn = [{ containerName = "parser", condition = "HEALTHY" }, { containerName = "clamav", condition = "HEALTHY" }], environment = concat(local.common_environment, [{ name = "WORKER_QUEUE", value = "rag" }]), secrets = concat(local.runtime_secrets, [{ name = "DATABASE_URL", valueFrom = local.secret_key.worker_database }]), mountPoints = concat(local.data_mounts, [{ sourceVolume = "parser-socket", containerPath = "/run/gabflow-parser", readOnly = false }]), stopTimeout = 120, logConfiguration = { logDriver = "awslogs", options = merge(local.log_options, { awslogs-group = aws_cloudwatch_log_group.this["worker"].name }) }, linuxParameters = { initProcessEnabled = true } },
  ])
}

resource "aws_ecs_task_definition" "migration" {
  family                   = "${var.name_prefix}-migration"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 1024
  memory                   = 2048
  execution_role_arn       = var.ecs_execution_role_arn
  task_role_arn            = var.migration_task_role_arn
  container_definitions    = jsonencode([{ name = "migration", image = local.backend_image, essential = true, command = ["true"], environment = concat(local.common_environment, [{ name = "RUN_MIGRATIONS_ON_START", value = "true" }, { name = "RUN_SEEDS_ON_START", value = "false" }]), secrets = concat(local.runtime_secrets, [{ name = "DATABASE_URL", valueFrom = local.secret_key.migration_database }]), logConfiguration = { logDriver = "awslogs", options = merge(local.log_options, { awslogs-group = aws_cloudwatch_log_group.this["migration"].name }) } }])
}

resource "aws_ecs_task_definition" "database_bootstrap" {
  family                   = "${var.name_prefix}-database-bootstrap"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = var.ecs_execution_role_arn
  task_role_arn            = var.migration_task_role_arn
  container_definitions = jsonencode([{
    name       = "database-bootstrap"
    image      = local.backend_image
    essential  = true
    entryPoint = ["python", "/app/db-bootstrap-roles.py"]
    environment = [
      { name = "POSTGRES_DB", value = "gabflow" },
      { name = "APP_DB_USER", value = "gabflow_app" },
      { name = "WORKER_DB_USER", value = "gabflow_worker" },
      { name = "BACKUP_DB_USER", value = "gabflow_backup" },
    ]
    secrets = [
      { name = "DATABASE_URL", valueFrom = local.secret_key.migration_database },
      { name = "APP_DATABASE_URL", valueFrom = local.secret_key.api_database },
      { name = "WORKER_DATABASE_URL", valueFrom = local.secret_key.worker_database },
      { name = "BACKUP_DATABASE_URL", valueFrom = local.secret_key.backup_database },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options   = merge(local.log_options, { awslogs-group = aws_cloudwatch_log_group.this["migration"].name })
    }
  }])
}

resource "aws_ecs_service" "app" {
  count                  = var.enable_services ? 1 : 0
  name                   = "${var.name_prefix}-app"
  cluster                = aws_ecs_cluster.this.id
  task_definition        = aws_ecs_task_definition.app.arn
  desired_count          = var.desired_app_count
  launch_type            = "FARGATE"
  platform_version       = "1.4.0"
  enable_execute_command = true
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  health_check_grace_period_seconds  = 240
  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = false
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.app.arn
    container_name   = "web"
    container_port   = 80
  }
  depends_on = [aws_lb_listener.http, aws_lb_listener.https, aws_efs_mount_target.this]
}
resource "aws_ecs_service" "worker" {
  count                  = var.enable_services ? 1 : 0
  name                   = "${var.name_prefix}-worker"
  cluster                = aws_ecs_cluster.this.id
  task_definition        = aws_ecs_task_definition.worker.arn
  desired_count          = var.desired_worker_count
  launch_type            = "FARGATE"
  platform_version       = "1.4.0"
  enable_execute_command = true
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = false
  }
  depends_on = [aws_efs_mount_target.this]
}

resource "aws_appautoscaling_target" "app" {
  count              = var.enable_services ? 1 : 0
  max_capacity       = 4
  min_capacity       = 1
  resource_id        = "service/${aws_ecs_cluster.this.name}/${aws_ecs_service.app[0].name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}
resource "aws_appautoscaling_policy" "app_cpu" {
  count              = var.enable_services ? 1 : 0
  name               = "${var.name_prefix}-app-cpu"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.app[0].resource_id
  scalable_dimension = aws_appautoscaling_target.app[0].scalable_dimension
  service_namespace  = aws_appautoscaling_target.app[0].service_namespace
  target_tracking_scaling_policy_configuration {
    target_value       = 60
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "alb_5xx" {
  alarm_name          = "${var.name_prefix}-alb-5xx"
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HTTPCode_Target_5XX_Count"
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 3
  datapoints_to_alarm = 2
  threshold           = 5
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  dimensions          = { LoadBalancer = aws_lb.this.arn_suffix }
}
resource "aws_cloudwatch_metric_alarm" "db_storage" {
  alarm_name          = "${var.name_prefix}-db-low-storage"
  namespace           = "AWS/RDS"
  metric_name         = "FreeStorageSpace"
  statistic           = "Minimum"
  period              = 300
  evaluation_periods  = 3
  datapoints_to_alarm = 2
  threshold           = 5368709120
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "breaching"
  dimensions          = { DBInstanceIdentifier = aws_db_instance.this.identifier }
}

resource "aws_cloudwatch_dashboard" "this" {
  dashboard_name = "${var.name_prefix}-runtime"
  dashboard_body = jsonencode({
    widgets = [
      {
        type = "metric", x = 0, y = 0, width = 12, height = 6,
        properties = {
          title = "ALB requests and target errors", region = var.aws_region, view = "timeSeries",
          metrics = [
            ["AWS/ApplicationELB", "RequestCount", "LoadBalancer", aws_lb.this.arn_suffix, { stat = "Sum" }],
            [".", "HTTPCode_Target_5XX_Count", ".", ".", { stat = "Sum" }],
          ]
        }
      },
      {
        type = "metric", x = 12, y = 0, width = 12, height = 6,
        properties = {
          title = "RDS health", region = var.aws_region, view = "timeSeries",
          metrics = [
            ["AWS/RDS", "CPUUtilization", "DBInstanceIdentifier", aws_db_instance.this.identifier],
            [".", "DatabaseConnections", ".", "."],
            [".", "FreeStorageSpace", ".", "."],
          ]
        }
      },
      {
        type = "alarm", x = 0, y = 6, width = 24, height = 4,
        properties = {
          title  = "Runtime alarms"
          alarms = [aws_cloudwatch_metric_alarm.alb_5xx.arn, aws_cloudwatch_metric_alarm.db_storage.arn]
        }
      }
    ]
  })
}

resource "aws_wafv2_web_acl" "this" {
  name  = "${var.name_prefix}-web"
  scope = "REGIONAL"
  default_action {
    allow {}
  }
  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${replace(var.name_prefix, "-", "")}-web"
    sampled_requests_enabled   = true
  }
  rule {
    name     = "AWSManagedRulesCommonRuleSet"
    priority = 10
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
        rule_action_override {
          name = "SizeRestrictions_BODY"
          action_to_use {
            count {}
          }
        }
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "CommonRules"
      sampled_requests_enabled   = true
    }
  }
  rule {
    name     = "AWSManagedRulesKnownBadInputsRuleSet"
    priority = 20
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
        vendor_name = "AWS"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "KnownBadInputs"
      sampled_requests_enabled   = true
    }
  }
  rule {
    name     = "RateLimit"
    priority = 30
    action {
      block {}
    }
    statement {
      rate_based_statement {
        aggregate_key_type = "IP"
        limit              = 2000
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "RateLimit"
      sampled_requests_enabled   = true
    }
  }
}
resource "aws_wafv2_web_acl_association" "this" {
  resource_arn = aws_lb.this.arn
  web_acl_arn  = aws_wafv2_web_acl.this.arn
}
