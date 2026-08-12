terraform {
  backend "s3" {
    key          = "management/organization.tfstate"
    encrypt      = true
    use_lockfile = true
  }
}
