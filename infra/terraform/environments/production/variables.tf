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
  default = "10.50.0.0/16"
}

variable "owner" {
  type    = string
  default = "gabflow-platform"
}

variable "cost_center" {
  type    = string
  default = "gabflow"
}
