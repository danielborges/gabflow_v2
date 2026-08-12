output "organization_id" {
  description = "ID da organização AWS."
  value       = aws_organizations_organization.gabflow.id
}

output "staging_account_id" {
  description = "ID da conta de staging criada, ou null."
  value       = try(aws_organizations_account.staging[0].id, null)
}

output "production_account_id" {
  description = "ID da conta de produção criada, ou null."
  value       = try(aws_organizations_account.production[0].id, null)
}
