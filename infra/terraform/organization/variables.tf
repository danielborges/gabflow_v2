variable "aws_region" {
  description = "Região usada pelas chamadas globais e metadados."
  type        = string
  default     = "sa-east-1"
}

variable "owner" {
  description = "Responsável pelos recursos."
  type        = string
  default     = "gabflow-platform"
}

variable "cost_center" {
  description = "Centro de custo usado nas tags."
  type        = string
  default     = "gabflow"
}

variable "create_accounts" {
  description = "Gate explícito para criar as contas AWS."
  type        = bool
  default     = false
}

variable "staging_account_email" {
  description = "E-mail exclusivo da conta de staging."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = !var.create_accounts || (var.staging_account_email != null && can(regex("^[^@]+@[^@]+\\.[^@]+$", var.staging_account_email)))
    error_message = "Informe staging_account_email válido quando create_accounts=true."
  }
}

variable "production_account_email" {
  description = "E-mail exclusivo da conta de produção."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = !var.create_accounts || (var.production_account_email != null && can(regex("^[^@]+@[^@]+\\.[^@]+$", var.production_account_email)))
    error_message = "Informe production_account_email válido quando create_accounts=true."
  }
}
