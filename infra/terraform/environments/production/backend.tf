terraform {
  backend "s3" {
    key          = "production/foundation.tfstate"
    encrypt      = true
    use_lockfile = true
  }
}
