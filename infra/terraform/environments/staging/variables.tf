variable "aws_region" {
  type    = string
  default = "sa-east-1"
}

variable "expected_account_id" {
  description = "Guard contra apply na conta errada."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.expected_account_id))
    error_message = "expected_account_id deve conter 12 dígitos."
  }
}

variable "vpc_cidr" {
  type    = string
  default = "10.40.0.0/16"
}

variable "owner" {
  type    = string
  default = "gabflow-platform"
}

variable "cost_center" {
  type    = string
  default = "gabflow"
}

variable "image_tag" {
  description = "Tag imutavel das imagens backend e web no ECR."
  type        = string
  default     = "bootstrap"
}

variable "enable_services" {
  description = "Ativa API e workers somente depois do bootstrap de banco e configuracao."
  type        = bool
  default     = false
}

variable "certificate_arn" {
  description = "ARN opcional de certificado ACM para HTTPS."
  type        = string
  default     = null
  nullable    = true
}

variable "domain_name" {
  description = "Dominio publico do ambiente de staging."
  type        = string
  default     = "staging.gabflow.app"

  validation {
    condition     = can(regex("^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$", var.domain_name))
    error_message = "domain_name deve ser um nome DNS publico valido em minusculas."
  }
}

variable "enable_https" {
  description = "Ativa a validacao ACM e o listener HTTPS depois da publicacao dos registros DNS."
  type        = bool
  default     = false
}

variable "db_instance_class" {
  description = "Classe do RDS PostgreSQL de staging."
  type        = string
  default     = "db.t4g.medium"
}
