resource "aws_organizations_organization" "gabflow" {
  feature_set = "ALL"

  aws_service_access_principals = [
    "account.amazonaws.com",
    "cloudtrail.amazonaws.com",
    "sso.amazonaws.com",
  ]
}

resource "aws_organizations_organizational_unit" "nonproduction" {
  name      = "NonProduction"
  parent_id = aws_organizations_organization.gabflow.roots[0].id
}

resource "aws_organizations_organizational_unit" "production" {
  name      = "Production"
  parent_id = aws_organizations_organization.gabflow.roots[0].id
}

resource "aws_organizations_account" "staging" {
  count = var.create_accounts ? 1 : 0

  name      = "GabFlow Staging"
  email     = var.staging_account_email
  parent_id = aws_organizations_organizational_unit.nonproduction.id
  role_name = "OrganizationAccountAccessRole"

  close_on_deletion = false

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_organizations_account" "production" {
  count = var.create_accounts ? 1 : 0

  name      = "GabFlow Production"
  email     = var.production_account_email
  parent_id = aws_organizations_organizational_unit.production.id
  role_name = "OrganizationAccountAccessRole"

  close_on_deletion = false

  lifecycle {
    prevent_destroy = true
  }
}
