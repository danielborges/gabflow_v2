terraform {
  required_version = ">= 1.10, < 2.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region              = var.aws_region
  allowed_account_ids = [var.expected_account_id]

  default_tags {
    tags = {
      environment = "production"
      managed-by  = "terraform"
      owner       = var.owner
      cost-center = var.cost_center
      service     = "platform-foundation"
    }
  }
}
