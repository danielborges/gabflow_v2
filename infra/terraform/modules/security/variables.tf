variable "name_prefix" {
  description = "Prefixo estável dos recursos."
  type        = string
}

variable "environment" {
  description = "Nome do ambiente."
  type        = string
}

variable "kms_deletion_window_days" {
  description = "Janela de recuperação da chave KMS."
  type        = number
  default     = 30
}

variable "secret_recovery_window_days" {
  description = "Janela de recuperação do secret de configuração."
  type        = number
  default     = 30
}
