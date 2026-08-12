output "account_id" {
  description = "Conta AWS em que o bootstrap foi aplicado."
  value       = data.aws_caller_identity.current.account_id
}

output "state_bucket_name" {
  description = "Bucket do backend S3."
  value       = aws_s3_bucket.terraform_state.id
}

output "state_kms_key_arn" {
  description = "KMS key do state."
  value       = aws_kms_key.terraform_state.arn
}

output "github_plan_role_arn" {
  description = "Role OIDC usada em pull requests."
  value       = aws_iam_role.github_plan.arn
}

output "github_apply_role_arn" {
  description = "Role OIDC usada pelo ambiente protegido para apply."
  value       = aws_iam_role.github_apply.arn
}
