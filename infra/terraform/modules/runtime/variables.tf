variable "name_prefix" { type = string }
variable "environment" { type = string }
variable "rag_embedding_provider" {
  type        = string
  description = "Provider de embeddings usado pela indexacao RAG."
  default     = "ollama"

  validation {
    condition     = contains(["local", "ollama"], var.rag_embedding_provider)
    error_message = "O provider de embeddings deve ser local ou ollama."
  }
}
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
variable "enable_ollama_sidecar" {
  type        = bool
  description = "Executa um Ollama CPU como sidecar da API sem criar uma tarefa adicional."
  default     = false
}
variable "ollama_model" {
  type        = string
  description = "Modelo leve carregado pelo sidecar Ollama."
  default     = "qwen2.5:0.5b"
}
variable "ollama_embedding_model" {
  type        = string
  description = "Modelo de embeddings carregado pelo sidecar Ollama."
  default     = "nomic-embed-text"
}
variable "ollama_image" {
  type        = string
  description = "Imagem Ollama fixada por digest para execução reproduzível."
  default     = "ollama/ollama:0.11.4@sha256:1514372d3cef7387b6202b253e761d820e00e44b28f268aad5029389d0479e99"
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
