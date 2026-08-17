variable "name_prefix" { type = string }
variable "environment" { type = string }
variable "rag_prompt_injection_classifier_provider" {
  type        = string
  description = "Provider do classificador de prompt injection usado pelo RAG."
  default     = "ollama"

  validation {
    condition     = contains(["local", "ollama", "http"], var.rag_prompt_injection_classifier_provider)
    error_message = "O provider do classificador deve ser local, ollama ou http."
  }
}
variable "rag_prompt_injection_classifier_model" {
  type        = string
  description = "Identificador do modelo ou conjunto de regras do classificador de prompt injection."
  default     = "qwen2.5:1.5b"
}
variable "aws_region" { type = string }
variable "vpc_id" { type = string }
variable "public_subnet_ids" { type = list(string) }
variable "private_subnet_ids" { type = list(string) }
variable "kms_key_arn" { type = string }
variable "application_secret_arn" { type = string }
variable "ecs_execution_role_arn" { type = string }
variable "ecs_execution_role_name" { type = string }
variable "api_task_role_arn" { type = string }
variable "api_task_role_name" { type = string }
variable "worker_task_role_arn" { type = string }
variable "worker_task_role_name" { type = string }
variable "migration_task_role_arn" { type = string }
variable "migration_task_role_name" { type = string }
variable "whatsapp_queue_url" { type = string }
variable "whatsapp_secret_prefix" { type = string }
variable "image_tag" {
  type        = string
  description = "Tag imutavel publicada pelo pipeline, normalmente o commit SHA."
  default     = "bootstrap"
}
variable "enable_services" {
  type        = bool
  description = "Ativa os services somente depois que a tag existe no ECR e o secret foi preenchido."
  default     = false
}
variable "certificate_arn" {
  type        = string
  description = "Certificado ACM regional. Sem ele o staging sobe apenas em HTTP e nao pode receber a Meta."
  default     = null
  nullable    = true
}
variable "desired_app_count" {
  type    = number
  default = 1
}
variable "desired_worker_count" {
  type    = number
  default = 1
}
variable "db_instance_class" {
  type    = string
  default = "db.t4g.medium"
}
variable "db_allocated_storage" {
  type    = number
  default = 30
}
variable "log_retention_days" {
  type    = number
  default = 30
}
