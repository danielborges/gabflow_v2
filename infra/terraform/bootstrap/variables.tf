variable "aws_region" {
  description = "Região primária do ambiente."
  type        = string
  default     = "sa-east-1"
}

variable "environment" {
  description = "Ambiente isolado que receberá o bootstrap."
  type        = string

  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "environment deve ser staging ou production."
  }
}

variable "state_bucket_name" {
  description = "Nome globalmente único do bucket de state."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.state_bucket_name))
    error_message = "Use um nome de bucket S3 válido, em minúsculas."
  }
}

variable "github_repository" {
  description = "Repositório autorizado, no formato owner/repository."
  type        = string
  default     = "danielborges/gabflow_v2"

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "github_repository deve usar o formato owner/repository."
  }
}

variable "github_apply_branches" {
  description = "Branches autorizadas a assumir a role de apply."
  type        = set(string)
  default     = ["main"]
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
