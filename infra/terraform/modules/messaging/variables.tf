variable "name_prefix" {
  description = "Prefixo estavel dos recursos."
  type        = string
}

variable "environment" {
  description = "Nome do ambiente."
  type        = string
}

variable "aws_region" {
  description = "Regiao AWS usada pelos widgets do dashboard."
  type        = string
}

variable "kms_key_arn" {
  description = "ARN da chave KMS usada na fila."
  type        = string
}

variable "api_task_role_name" {
  description = "Nome da task role da API."
  type        = string
}

variable "worker_task_role_name" {
  description = "Nome da task role do worker."
  type        = string
}

variable "max_receive_count" {
  description = "Tentativas antes do envio para a DLQ."
  type        = number
  default     = 5
}

variable "visibility_timeout_seconds" {
  description = "Tempo de invisibilidade durante o processamento."
  type        = number
  default     = 120
}
