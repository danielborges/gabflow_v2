variable "name_prefix" {
  description = "Prefixo estável dos recursos."
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR IPv4 da VPC."
  type        = string
}

variable "availability_zone_count" {
  description = "Quantidade de zonas usadas."
  type        = number
  default     = 2

  validation {
    condition     = var.availability_zone_count >= 2 && var.availability_zone_count <= 3
    error_message = "Use entre duas e três zonas de disponibilidade."
  }
}

variable "single_nat_gateway" {
  description = "Usa um NAT para todas as AZs; reduz custo, mas também a resiliência."
  type        = bool
  default     = true
}

variable "interface_endpoint_services" {
  description = "Serviços com interface endpoint privado."
  type        = set(string)
  default     = ["ecr.api", "ecr.dkr", "logs", "kms", "secretsmanager", "sqs", "sts"]
}

variable "flow_log_retention_days" {
  description = "Retenção dos VPC Flow Logs."
  type        = number
  default     = 30
}
