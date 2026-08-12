terraform {
  backend "s3" {
    key          = "management/backend-bootstrap.tfstate"
    encrypt      = true
    use_lockfile = true
  }
}
