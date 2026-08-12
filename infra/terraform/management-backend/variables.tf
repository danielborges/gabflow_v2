variable "aws_region" {
  description = "Regiao da infraestrutura de state da conta de gerenciamento."
  type        = string
  default     = "sa-east-1"
}

variable "state_bucket_name" {
  description = "Nome globalmente unico do bucket de state da conta de gerenciamento."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.state_bucket_name))
    error_message = "Use um nome de bucket S3 valido, em minusculas."
  }
}

variable "owner" {
  description = "Responsavel pelos recursos."
  type        = string
  default     = "gabflow-platform"
}

variable "cost_center" {
  description = "Centro de custo usado nas tags."
  type        = string
  default     = "gabflow"
}
