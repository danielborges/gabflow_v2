output "account_id" {
  description = "Conta AWS que hospeda o backend de gerenciamento."
  value       = data.aws_caller_identity.current.account_id
}

output "state_bucket_name" {
  description = "Bucket S3 do backend de gerenciamento."
  value       = aws_s3_bucket.terraform_state.id
}

output "state_kms_key_arn" {
  description = "ARN da chave KMS usada pelo backend de gerenciamento."
  value       = aws_kms_key.terraform_state.arn
}
