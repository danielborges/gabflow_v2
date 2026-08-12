terraform {
  backend "s3" {
    key          = "staging/foundation.tfstate"
    encrypt      = true
    use_lockfile = true
  }
}
